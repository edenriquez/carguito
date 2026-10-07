/**
 * The Lectura readings that hold the statement against a published table:
 * the ENIGH's grandes rubros, the canasta alimentaria, and the INPC. Pure,
 * like `lecturaEstado.ts`; the tables live in `enighRubros.ts`, `canasta.ts`
 * and `inpc.ts` with their sources.
 */

import { canastaAt, type CanastaMonth } from "./canasta";
import { categoryName, foldCategoryName, rootCategoryId, type CategoryInfo } from "./categories";
import { ENIGH_RUBRO_MONTHLY, RUBRO_ORDER, rubroShare, type Rubro } from "./enighRubros";
import { INPC_MONTHLY, inpcChange } from "./inpc";
import type { Leaf } from "./lecturaEstado";
import type { Receipt, ReferenceTerm } from "./prices";

/* ----------------------------------------------------------------- Rubros */

/**
 * Which ENIGH rubro a category falls in, by name, with the root as fallback
 * — the same shape as the necesidad table. A category with no row here stays
 * out of the comparison and is named in the card, never guessed into a rubro.
 * Note: internet, TV and phone credit are communications, which the ENIGH
 * files under transporte y comunicaciones, not vivienda.
 */
const RUBRO_BY_NAME: Record<string, Rubro> = {
    "comida & supermercados": "alimentos",
    supermercado: "alimentos",
    conveniencia: "alimentos",
    restaurantes: "alimentos",
    ropa: "vestido",
    "vivienda & servicios": "vivienda",
    luz: "vivienda",
    agua: "vivienda",
    renta: "vivienda",
    gas: "vivienda",
    salud: "salud",
    farmacia: "salud",
    transporte: "transporte",
    gasolina: "transporte",
    apps: "transporte",
    pasajes: "transporte",
    caseta: "transporte",
    "internet y tv": "transporte",
    "saldo celular": "transporte",
    prepago: "transporte",
    entretenimiento: "educacion",
    streaming: "educacion",
    cine: "educacion",
    colegiatura: "educacion",
    gym: "educacion",
    "envios a terceros": "transferencias",
};

/** Food bought to eat at home is what the canasta alimentaria prices; a
 *  restaurant or an OXXO is not that. */
const EATING_OUT = new Set(["restaurantes", "conveniencia"]);

export function rubroOf(categories: Map<string, CategoryInfo> | null, categoryId: string | null): Rubro | null {
    if (!categoryId) return null;
    const own = RUBRO_BY_NAME[foldCategoryName(categoryName(categories, categoryId))];
    if (own) return own;
    const root = rootCategoryId(categories, categoryId);
    if (root && root !== categoryId) {
        const up = RUBRO_BY_NAME[foldCategoryName(categoryName(categories, root))];
        if (up) return up;
    }
    return null;
}

export type RubroRow = { rubro: Rubro; amount: number; share: number; decileShare: number };

export type RubrosReading = {
    rows: RubroRow[];
    /** The rubro where the statement strays furthest from the decile. */
    top: RubroRow | null;
    /** Pesos that fell in some rubro — the denominator of every share. */
    mapped: number;
    /** Pesos in categories no rubro claims, and which categories they were. */
    unmapped: { amount: number; names: string[] };
};

export function readRubros(leaves: Leaf[], categories: Map<string, CategoryInfo> | null, decile: number): RubrosReading {
    const amounts = new Map<Rubro, number>(RUBRO_ORDER.map((r) => [r, 0]));
    const unmapped = { amount: 0, names: [] as string[] };
    for (const leaf of leaves) {
        const rubro = rubroOf(categories, leaf.categoryId);
        if (rubro) amounts.set(rubro, amounts.get(rubro)! + leaf.amount);
        else {
            unmapped.amount += leaf.amount;
            unmapped.names.push(leaf.name);
        }
    }
    const mapped = Array.from(amounts.values()).reduce((s, v) => s + v, 0);
    const rows = RUBRO_ORDER.map((rubro) => {
        const amount = amounts.get(rubro)!;
        return { rubro, amount, share: mapped > 0 ? amount / mapped : 0, decileShare: rubroShare(rubro, decile) };
    });
    const top = mapped > 0
        ? rows.reduce((b, r) => (Math.abs(r.share - r.decileShare) > Math.abs(b.share - b.decileShare) ? r : b), rows[0]!)
        : null;
    return { rows, top, mapped, unmapped };
}

/** The decile's own monthly pesos on a rubro, for a tooltip. */
export function rubroPesos(rubro: Rubro, decile: number): number {
    return ENIGH_RUBRO_MONTHLY[rubro][decile]!;
}

/* ---------------------------------------------------------------- Canasta */

export type CanastaReading = {
    /** The month the line was read at: the latest INEGI has, at or before the statement's last month. */
    key: string;
    line: CanastaMonth;
    /** What the statement spends a month on food at home. */
    food: number;
    /** How many people that food would feed at the urban canasta alimentaria. */
    foodPersons: number;
    /** How many people the whole month would keep above the urban línea de pobreza. */
    totalPersons: number;
};

export function readCanasta(
    leaves: Leaf[],
    categories: Map<string, CategoryInfo> | null,
    average: number,
    months: number,
    monthKey: string
): CanastaReading | null {
    const at = canastaAt(monthKey);
    if (!at || months === 0) return null;
    const food = leaves
        .filter((l) => rubroOf(categories, l.categoryId) === "alimentos" && !EATING_OUT.has(foldCategoryName(l.name)))
        .reduce((s, l) => s + l.amount, 0) / months;
    return {
        key: at.key,
        line: at.value,
        food,
        foodPersons: food / at.value.alimentariaUrbana,
        totalPersons: average / at.value.completaUrbana,
    };
}

/* ------------------------------------------------------------------- INPC */

export type PriceDriftRow = {
    key: string;
    name: string;
    ratio: number;
    from: string;
    to: string;
    basis: "unit" | "each";
    /** The INPC de alimentos over the same two months, or null outside the table. */
    inpc: number | null;
};

export type PriceDrift = {
    /** Products bought in at least two different months with a comparable price. */
    products: number;
    /** The median product's last price over its first, as a ratio. */
    median: number;
    /** The median of the INPC de alimentos over each product's own two months
     *  — the like-for-like figure the sentence compares against. Null when no
     *  product's months are in the table. */
    inpcMedian: number | null;
    /** Earliest and latest months among those products. */
    from: string;
    to: string;
    /** Biggest movers first. */
    rows: PriceDriftRow[];
};

const receiptMonth = (r: Receipt) => (r.purchased_at ?? r.captured_at ?? "").slice(0, 7);

/**
 * How the user's own prices moved, from the tickets. Per product, the mean
 * comparable price in its first month against its last; per litre/kilo when
 * the ticket gave a size, per piece otherwise, never mixing the two. Each
 * product is held against the INPC of its own two months, so the comparison
 * is like for like even when the products were bought over different spans.
 * Null until two purchases of one product fall in different months.
 */
export function readPriceDrift(receipts: Receipt[], terms: Record<string, ReferenceTerm>): PriceDrift | null {
    type Point = { month: string; value: number };
    const byProduct = new Map<string, { name: string; unit: Point[]; each: Point[] }>();
    for (const r of receipts) {
        const month = receiptMonth(r);
        if (month.length !== 7) continue;
        for (const item of r.items) {
            const entry = byProduct.get(item.product_key) ?? { name: terms[item.product_key]?.term ?? item.description, unit: [], each: [] };
            if (item.per_base_unit && item.per_base_unit > 0) entry.unit.push({ month, value: item.per_base_unit });
            else if (item.each && item.each > 0) entry.each.push({ month, value: item.each });
            else if (item.unit_price && item.unit_price > 0) entry.each.push({ month, value: item.unit_price });
            byProduct.set(item.product_key, entry);
        }
    }

    const rows: PriceDriftRow[] = [];
    for (const [key, p] of byProduct) {
        for (const basis of ["unit", "each"] as const) {
            const pts = p[basis];
            const months = Array.from(new Set(pts.map((x) => x.month))).sort();
            if (months.length < 2) continue;
            const from = months[0]!, to = months[months.length - 1]!;
            const mean = (m: string) => {
                const own = pts.filter((x) => x.month === m);
                return own.reduce((s, x) => s + x.value, 0) / own.length;
            };
            rows.push({ key, name: p.name, ratio: mean(to) / mean(from), from, to, basis, inpc: inpcChange(from, to)?.alimentos ?? null });
            break;
        }
    }
    if (rows.length === 0) return null;
    const median = (xs: number[]) => {
        const sorted = [...xs].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
    };
    const withInpc = rows.filter((r): r is PriceDriftRow & { inpc: number } => r.inpc !== null);
    rows.sort((a, b) => Math.abs(b.ratio - 1) - Math.abs(a.ratio - 1));
    return {
        products: rows.length,
        median: median(rows.map((r) => r.ratio)),
        inpcMedian: withInpc.length ? median(withInpc.map((r) => r.inpc)) : null,
        from: rows.reduce((m, r) => (r.from < m ? r.from : m), rows[0]!.from),
        to: rows.reduce((m, r) => (r.to > m ? r.to : m), rows[0]!.to),
        rows,
    };
}

export type InpcPoint = { key: string; general: number; alimentos: number };

/**
 * The INPC over a run of months, each index rebased to 100 at the first month
 * the table has. Months the table lacks are left out, so a statement newer
 * than the last INPC simply ends where the INPC ends.
 */
export function inpcIndexed(keys: string[]): InpcPoint[] {
    const have = keys.filter((k) => INPC_MONTHLY[k]);
    const base = have[0] ? INPC_MONTHLY[have[0]]! : null;
    if (!base) return [];
    return have.map((key) => {
        const v = INPC_MONTHLY[key]!;
        return { key, general: (100 * v.general) / base.general, alimentos: (100 * v.alimentos) / base.alimentos };
    });
}

export { inpcChange };
