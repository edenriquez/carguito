/**
 * The Ingresos store: which deposit clusters the user named nómina or extra.
 * Nothing is auto-labeled — a $70k préstamo that looks like income is not
 * income until they say so.
 *
 * Persistence hides behind `IngresosStore`, async on purpose even though
 * localStorage is sync — when this becomes a backend endpoint, no caller
 * changes. No React in this file.
 */

import type { RecurringItem, Transaction } from "./api";
import { restMonthlyFromTransactions, seriesKeyFromDescription, type Frequency } from "./fijos";
import { parsePeriodKey } from "./metrics";

export const INGRESOS_VERSION = 1;
export const INGRESOS_STORAGE_KEY = "tomin.ingresos";

export type IncomeKind = "nomina" | "extra";

export type IncomeLabel = {
    key: string;
    kind: IncomeKind;
};

export type IngresosState = {
    version: typeof INGRESOS_VERSION;
    labeled: IncomeLabel[];
};

export const DEFAULT_INGRESOS: IngresosState = {
    version: INGRESOS_VERSION,
    labeled: [],
};

export type IncomeCluster = {
    key: string;
    label: string;
    txs: Transaction[];
};

function isRecord(v: unknown): v is Record<string, unknown> {
    return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isKind(v: unknown): v is IncomeKind {
    return v === "nomina" || v === "extra";
}

function parseLabel(raw: unknown): IncomeLabel | null {
    if (!isRecord(raw)) return null;
    if (typeof raw.key !== "string" || !raw.key) return null;
    if (!isKind(raw.kind)) return null;
    return { key: raw.key, kind: raw.kind };
}

export function parseIngresos(raw: unknown): IngresosState {
    if (!isRecord(raw) || raw.version !== INGRESOS_VERSION) return DEFAULT_INGRESOS;
    const labeled = Array.isArray(raw.labeled)
        ? raw.labeled.map(parseLabel).filter((l): l is IncomeLabel => l !== null)
        : [];
    const seen = new Set<string>();
    const unique: IncomeLabel[] = [];
    for (const l of labeled) {
        if (seen.has(l.key)) continue;
        seen.add(l.key);
        unique.push(l);
    }
    return { version: INGRESOS_VERSION, labeled: unique };
}

export interface IngresosStore {
    load(): Promise<IngresosState | null>;
    save(state: IngresosState): Promise<void>;
}

export const localIngresosStore: IngresosStore = {
    async load() {
        if (typeof window === "undefined") return null;
        const raw = window.localStorage.getItem(INGRESOS_STORAGE_KEY);
        if (raw === null) return null;
        try {
            return parseIngresos(JSON.parse(raw));
        } catch {
            return DEFAULT_INGRESOS;
        }
    },
    async save(state) {
        if (typeof window === "undefined") return;
        window.localStorage.setItem(INGRESOS_STORAGE_KEY, JSON.stringify(state));
    },
};

const STOP = new Set(["de", "del", "la", "el", "en", "sa", "de", "y", "por", "a"]);

function normalize(text: string): string {
    return text
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9 ]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

/**
 * The person or company who sent the money. Mexican bank text is
 * "PAGO RECIBIDO DE {rail} POR ORDEN DE {payer}" — two rails for the same
 * employer must be one cluster.
 */
export function payerFromDescription(description: string): string {
    const n = normalize(description);
    const ordered = n.match(/por orden de (.+)$/) ?? n.match(/orden de (.+)$/);
    const raw = ordered?.[1] ?? n;
    const words = raw.split(" ").filter((w) => w.length >= 2 && !STOP.has(w));
    if (words.length === 0) return seriesKeyFromDescription(description) || n;
    // One distinctive word, or the first two when the first is short (VECH).
    if (words[0]!.length >= 5) return words[0]!;
    return words.slice(0, 2).join(" ");
}

function titleCase(s: string): string {
    return s
        .split(" ")
        .map((w) => (w ? w[0]!.toUpperCase() + w.slice(1) : w))
        .join(" ");
}

export function isIncomeDeposit(t: Transaction): boolean {
    return t.type === "income" && !t.is_transfer && !t.excluded_from_stats;
}

/** Group deposits by payer. Newest-first inside each cluster. */
export function clusterIncome(ledger: Transaction[]): IncomeCluster[] {
    const bags = new Map<string, Transaction[]>();
    for (const t of ledger) {
        if (!isIncomeDeposit(t)) continue;
        const key = payerFromDescription(t.raw_description || t.description);
        if (!key) continue;
        const bag = bags.get(key) ?? [];
        bag.push(t);
        bags.set(key, bag);
    }
    return Array.from(bags.entries())
        .map(([key, txs]) => ({
            key,
            label: titleCase(key),
            txs: txs.slice().sort((a, b) => b.date.localeCompare(a.date)),
        }))
        .sort((a, b) => b.txs.length - a.txs.length || a.label.localeCompare(b.label));
}

function median(values: number[]): number {
    if (values.length === 0) return 0;
    const s = values.slice().sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
}

function inferCadence(txs: Transaction[]): Frequency | null {
    if (txs.length < 3) return null;
    const dates = txs
        .map((t) => parsePeriodKey(t.date))
        .filter((d): d is Date => d !== null)
        .sort((a, b) => a.getTime() - b.getTime());
    if (dates.length < 3) return null;
    const gaps: number[] = [];
    for (let i = 1; i < dates.length; i++) {
        gaps.push(Math.round((dates[i]!.getTime() - dates[i - 1]!.getTime()) / 86_400_000));
    }
    const med = median(gaps);
    if (med >= 6 && med <= 9) return "weekly";
    if (med >= 12 && med <= 18) return "biweekly";
    if (med >= 26 && med <= 35) return "monthly";
    if (med >= 42 && med <= 80) return "bimonthly";
    if (med >= 160 && med <= 200) return "semiannual";
    return null;
}

const CADENCE_DAYS: Record<Frequency, number> = {
    weekly: 7,
    biweekly: 14,
    monthly: 30,
    bimonthly: 60,
    semiannual: 182,
    yearly: 365,
};

function stepForward(d: Date, frequency: Frequency): Date {
    const next = new Date(d);
    switch (frequency) {
        case "weekly":
            next.setDate(next.getDate() + 7);
            break;
        case "biweekly":
            next.setDate(next.getDate() + 14);
            break;
        case "bimonthly":
            next.setMonth(next.getMonth() + 2);
            break;
        case "semiannual":
            next.setMonth(next.getMonth() + 6);
            break;
        case "yearly":
            next.setFullYear(next.getFullYear() + 1);
            break;
        default:
            next.setMonth(next.getMonth() + 1);
    }
    return next;
}

function isoDate(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}

/**
 * A labeled cluster as a series `buildTimeline` can project. Nómina with a
 * recognizable gap lands charge by charge; extra (and nómina without a day)
 * smears the median month.
 */
export function itemFromIncomeCluster(cluster: IncomeCluster, kind: IncomeKind): RecurringItem {
    const { charges, typical, monthly } = restMonthlyFromTransactions(cluster.txs);
    const last = charges.reduce((a, b) => (a.date > b.date ? a : b));
    const cadence = kind === "nomina" ? inferCadence(cluster.txs) : null;
    const cats = new Map<string | null, number>();
    for (const t of cluster.txs) {
        cats.set(t.category_id, (cats.get(t.category_id) ?? 0) + 1);
    }
    const category_id = Array.from(cats.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;

    if (cadence) {
        const lastDate = parsePeriodKey(last.date) ?? new Date();
        const days = CADENCE_DAYS[cadence];
        return {
            key: `ingreso:${cluster.key}`,
            label: cluster.label,
            occurrences: charges.length,
            frequency: cadence,
            typical_amount: typical,
            monthly_equivalent: (typical * 30) / days,
            amount_stable: true,
            last_date: last.date,
            next_expected: isoDate(stepForward(lastDate, cadence)),
            category_id,
            charges,
        };
    }

    return {
        key: `ingreso:smear:${cluster.key}`,
        label: cluster.label,
        occurrences: charges.length,
        frequency: "monthly",
        typical_amount: typical,
        monthly_equivalent: monthly,
        amount_stable: false,
        last_date: last.date,
        next_expected: last.date,
        category_id,
        charges,
    };
}

/** Labeled clusters as series `buildTimeline` can project, split by kind. */
export function labeledIncomeItems(
    state: IngresosState,
    clusters: IncomeCluster[]
): { nomina: RecurringItem[]; extra: RecurringItem[] } {
    const byKey = new Map(clusters.map((c) => [c.key, c]));
    const nomina: RecurringItem[] = [];
    const extra: RecurringItem[] = [];
    for (const l of state.labeled) {
        const cluster = byKey.get(l.key);
        if (!cluster) continue;
        const item = itemFromIncomeCluster(cluster, l.kind);
        if (l.kind === "nomina") nomina.push(item);
        else extra.push(item);
    }
    return { nomina, extra };
}
