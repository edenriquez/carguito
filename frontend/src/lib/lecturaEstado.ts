/**
 * The Lectura face: the last months of cargos read the way an analyst would —
 * against the country (ENIGH), against the user's income, against the
 * calendar, and by how necessary each peso was.
 *
 * Pure: no React, no fetching. The face hands in the same span Por mes reads
 * (six calendar months ending on the newest movement) and gets back every
 * number its eight cards draw. What a card *says* is decided here too, so the
 * sentence and the chart can never disagree.
 *
 * Not to be confused with `lib/lectura.ts`, which is the saved-rule workstation.
 */

import type { RecurringItem, Transaction } from "./api";
import {
    categoryName,
    isUncategorizedId,
    rootCategoryId,
    type CategoryInfo,
} from "./categories";
import { seriesKeyFromDescription } from "./fijos";
import { matchMerchant, merchantBySlug } from "./merchants";
import { monthKeyOf, monthKeyToDate, type MonthKey } from "./porMes";

export type Tier = "primera" | "segunda" | "tercera" | "deuda" | "sin";

export const TIER_ORDER: Tier[] = ["primera", "segunda", "tercera", "deuda", "sin"];

export const TIER_LABELS: Record<Tier, string> = {
    primera: "Primera necesidad",
    segunda: "Segunda necesidad",
    tercera: "Tercera necesidad",
    deuda: "Costo de deuda",
    sin: "Sin clasificar",
};

/**
 * The default level of each category, by name. A name the table does not know
 * falls back to its root's level, and then to "sin clasificar" — Carguito does
 * not guess whether a category it has never seen is necessary.
 */
const TIER_BY_NAME: Record<string, Tier> = {
    "vivienda & servicios": "primera",
    luz: "primera",
    agua: "primera",
    renta: "primera",
    "internet y tv": "primera",
    gas: "primera",
    "comida & supermercados": "primera",
    supermercado: "primera",
    transporte: "primera",
    gasolina: "primera",
    pasajes: "primera",
    "saldo celular": "primera",
    prepago: "primera",
    colegiatura: "primera",
    seguro: "primera",
    impuestos: "primera",
    salud: "primera",
    farmacia: "primera",
    "mercado libre": "segunda",
    ropa: "segunda",
    gym: "segunda",
    conveniencia: "segunda",
    caseta: "segunda",
    restaurantes: "segunda",
    apps: "segunda",
    entretenimiento: "tercera",
    streaming: "tercera",
    cine: "tercera",
    "comisiones e intereses": "deuda",
};

function norm(name: string): string {
    return name.normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();
}

export function tierOf(categories: Map<string, CategoryInfo> | null, categoryId: string | null): Tier {
    if (isUncategorizedId(categories, categoryId)) return "sin";
    const own = TIER_BY_NAME[norm(categoryName(categories, categoryId))];
    if (own) return own;
    const root = rootCategoryId(categories, categoryId);
    if (root && root !== categoryId) {
        const up = TIER_BY_NAME[norm(categoryName(categories, root))];
        if (up) return up;
    }
    return "sin";
}

/** Hours in a working month: ~44 h a week × 4.33 weeks. */
export const HOURS_PER_MONTH = 190.5;

export type Leaf = { name: string; amount: number; count: number; tier: Tier; categoryId: string | null };

export type TierSlice = {
    tier: Tier;
    amount: number;
    count: number;
    share: number;
    leaves: Leaf[];
};

/** One place the money went: a known merchant, or a description folded the
 *  way recurrence folds it. Cash withdrawals are not a merchant. */
export type MerchantSlice = { key: string; name: string; amount: number; count: number; share: number };

/** Cargos by size. `upTo` is the bucket's inclusive ceiling. */
export type AmountBucket = { label: string; upTo: number; amount: number; count: number };

/** A cargo this size or smaller is gasto hormiga. */
export const HORMIGA_MAX = 200;

const BUCKET_EDGES: { label: string; upTo: number }[] = [
    { label: "hasta $200", upTo: HORMIGA_MAX },
    { label: "$200 a $500", upTo: 500 },
    { label: "$500 a $1,000", upTo: 1000 },
    { label: "$1,000 a $5,000", upTo: 5000 },
    { label: "más de $5,000", upTo: Infinity },
];

/**
 * A month's cargos split by whether the place had already been paid in an
 * earlier month of the span. The first month that holds cargos is the base:
 * everything in it is "known" by definition, so it is marked and left out of
 * the share. Cash withdrawals are in neither figure.
 */
export type HabitMonth = { key: MonthKey; known: number; fresh: number; freshMerchants: number; base: boolean };

export type EstadoMonth = { key: MonthKey; amount: number; count: number; segunda: number; cash: number };

export type EstadoReading = {
    /** Every month of the span, oldest first. */
    months: EstadoMonth[];
    total: number;
    count: number;
    /** Mean over the months that hold cargos — an empty month is missing data. */
    average: number;
    /** Index 0 is day 1. */
    byDay: number[];
    /** Monday first. */
    byWeekday: { amount: number; count: number }[];
    /** ISO day → cargos that day. Only days with at least one cargo. */
    byDate: Map<string, number>;
    tiers: TierSlice[];
    /** Every named category, biggest first. */
    leaves: Leaf[];
    /** Every place the money went, biggest first, cash withdrawals aside. */
    merchants: MerchantSlice[];
    /** Withdrawals at a cajero: money that left the statement and went dark. */
    cash: { amount: number; count: number; share: number };
    buckets: AmountBucket[];
    habit: { months: HabitMonth[]; knownShare: number; freshAmount: number; freshMerchants: number };
};

const spendable = (t: Transaction) =>
    t.type === "expense" && !t.is_transfer && !t.excluded_from_stats;

function merchantOf(t: Transaction): { key: string; name: string } {
    const slug = matchMerchant(t.description);
    if (slug) return { key: `m:${slug}`, name: merchantBySlug(slug)?.name ?? t.description };
    const folded = seriesKeyFromDescription(t.description) || t.description.trim().toLowerCase();
    return { key: `d:${folded}`, name: t.description };
}

export function readEstado(
    items: Transaction[],
    categories: Map<string, CategoryInfo> | null,
    keys: MonthKey[]
): EstadoReading {
    const inSpan = new Set(keys);
    const months = new Map<MonthKey, EstadoMonth>(
        keys.map((k) => [k, { key: k, amount: 0, count: 0, segunda: 0, cash: 0 }])
    );
    const byDay = Array.from({ length: 31 }, () => 0);
    const byWeekday = Array.from({ length: 7 }, () => ({ amount: 0, count: 0 }));
    const byDate = new Map<string, number>();
    const leafMap = new Map<string, Leaf>();
    const merchantMap = new Map<string, MerchantSlice>();
    const buckets: AmountBucket[] = BUCKET_EDGES.map((b) => ({ ...b, amount: 0, count: 0 }));
    const cash = { amount: 0, count: 0, share: 0 };
    /** The cargos in the span, for the habit pass. */
    const rows: { key: MonthKey; amount: number; merchant: { key: string; name: string } | null; date: string }[] = [];
    let total = 0;
    let count = 0;

    for (const t of items) {
        if (!spendable(t)) continue;
        const key = monthKeyOf(t.date);
        if (!inSpan.has(key)) continue;
        const amount = Math.abs(t.amount);
        const tier = tierOf(categories, t.category_id);
        const name = tier === "sin" && isUncategorizedId(categories, t.category_id)
            ? "Sin categoría"
            : categoryName(categories, t.category_id);

        total += amount;
        count += 1;
        const m = months.get(key)!;
        m.amount += amount;
        m.count += 1;
        if (tier === "segunda") m.segunda += amount;

        const [y, mo, d] = t.date.split("-").map(Number);
        byDay[(d ?? 1) - 1]! += amount;
        const wd = (new Date(y!, (mo ?? 1) - 1, d ?? 1).getDay() + 6) % 7;
        byWeekday[wd]!.amount += amount;
        byWeekday[wd]!.count += 1;
        byDate.set(t.date, (byDate.get(t.date) ?? 0) + amount);

        const leafKey = `${tier}|${name}`;
        const leaf = leafMap.get(leafKey) ?? { name, amount: 0, count: 0, tier, categoryId: t.category_id };
        leaf.amount += amount;
        leaf.count += 1;
        leafMap.set(leafKey, leaf);

        const bucket = buckets.find((b) => amount <= b.upTo)!;
        bucket.amount += amount;
        bucket.count += 1;

        if (t.is_cash_withdrawal) {
            cash.amount += amount;
            cash.count += 1;
            m.cash += amount;
            rows.push({ key, amount, merchant: null, date: t.date });
            continue;
        }
        const merchant = merchantOf(t);
        const slice = merchantMap.get(merchant.key) ?? { ...merchant, amount: 0, count: 0, share: 0 };
        slice.amount += amount;
        slice.count += 1;
        merchantMap.set(merchant.key, slice);
        rows.push({ key, amount, merchant, date: t.date });
    }

    const leaves = Array.from(leafMap.values()).sort((a, b) => b.amount - a.amount);
    const tiers = TIER_ORDER.map((tier) => {
        const own = leaves.filter((l) => l.tier === tier);
        const amount = own.reduce((s, l) => s + l.amount, 0);
        return {
            tier,
            amount,
            count: own.reduce((s, l) => s + l.count, 0),
            share: total > 0 ? amount / total : 0,
            leaves: own,
        };
    });
    const monthList = keys.map((k) => months.get(k)!);
    const held = monthList.filter((m) => m.count > 0);

    const merchants = Array.from(merchantMap.values())
        .map((s) => ({ ...s, share: total > 0 ? s.amount / total : 0 }))
        .sort((a, b) => b.amount - a.amount);
    cash.share = total > 0 ? cash.amount / total : 0;

    // Habit: month by month, a place is new until the month it first appears
    // is over — its second cargo that same month is still a new place. Cash
    // has no place to be known from and stays out of the split.
    const seen = new Set<string>();
    const habitMonths: HabitMonth[] = held.map((m, i) => {
        const h: HabitMonth = { key: m.key, known: 0, fresh: 0, freshMerchants: 0, base: i === 0 };
        const paid = new Set<string>();
        const fresh = new Set<string>();
        for (const r of rows) {
            if (r.key !== m.key || r.merchant === null) continue;
            paid.add(r.merchant.key);
            if (h.base || seen.has(r.merchant.key)) {
                h.known += r.amount;
            } else {
                h.fresh += r.amount;
                fresh.add(r.merchant.key);
            }
        }
        h.freshMerchants = fresh.size;
        for (const key of paid) seen.add(key);
        return h;
    });
    const after = habitMonths.filter((h) => !h.base);
    const knownAfter = after.reduce((s, h) => s + h.known, 0);
    const freshAmount = after.reduce((s, h) => s + h.fresh, 0);

    return {
        months: monthList,
        total,
        count,
        average: held.length ? total / held.length : 0,
        byDay,
        byWeekday,
        byDate,
        tiers,
        leaves: leaves.filter((l) => l.name !== "Sin categoría"),
        merchants,
        cash,
        buckets,
        habit: {
            months: habitMonths,
            knownShare: knownAfter + freshAmount > 0 ? knownAfter / (knownAfter + freshAmount) : 1,
            freshAmount,
            freshMerchants: after.reduce((s, h) => s + h.freshMerchants, 0),
        },
    };
}

/* ------------------------------------------------------------- Habits */

/** The top places together: how much of every peso the first `n` took. */
export function concentration(merchants: MerchantSlice[], n = 3): { top: MerchantSlice[]; share: number } {
    const top = merchants.slice(0, n);
    return { top, share: top.reduce((s, m) => s + m.share, 0) };
}

/** Gasto hormiga: the small cargos' share of the count against their share of the money. */
export function hormiga(buckets: AmountBucket[]): { countShare: number; amountShare: number; count: number; amount: number } {
    const small = buckets[0]!;
    const count = buckets.reduce((s, b) => s + b.count, 0) || 1;
    const amount = buckets.reduce((s, b) => s + b.amount, 0) || 1;
    return { countShare: small.count / count, amountShare: small.amount / amount, count: small.count, amount: small.amount };
}

export type DaysReading = {
    /** Days with at least one cargo, and the days the span covers, up to `until`. */
    active: number;
    total: number;
    /** One row per held month: a cell per calendar day, null outside `since`–`until`. */
    rows: { key: MonthKey; cells: (number | null)[] }[];
    /** The longest run of days without a cargo, inside the months that hold data. */
    gap: { days: number; from: string; to: string } | null;
};

const isoOf = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/**
 * Which days had a cargo, between the first day the record covers and the
 * last. Only the months that hold cargos count: a month with nothing in the
 * record is missing data, not thirty days of restraint, and a gap never
 * bridges one.
 */
export function readDays(byDate: Map<string, number>, held: MonthKey[], since: string, until: string): DaysReading {
    let active = 0;
    let total = 0;
    let gap: DaysReading["gap"] = null;
    let runDays = 0;
    let runFrom = "";
    let prevKey: MonthKey | null = null;
    const rows: DaysReading["rows"] = [];

    for (const key of held) {
        const first = monthKeyToDate(key);
        const daysIn = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
        const prevMonth = isoOf(new Date(first.getFullYear(), first.getMonth() - 1, 1)).slice(0, 7);
        if (prevKey !== prevMonth) runDays = 0;
        prevKey = key;
        const cells: (number | null)[] = [];
        for (let d = 1; d <= daysIn; d++) {
            const iso = isoOf(new Date(first.getFullYear(), first.getMonth(), d));
            if (iso < since || iso > until) {
                cells.push(null);
                continue;
            }
            const amount = byDate.get(iso) ?? 0;
            cells.push(amount);
            total += 1;
            if (amount > 0) {
                active += 1;
                runDays = 0;
            } else {
                if (runDays === 0) runFrom = iso;
                runDays += 1;
                if (!gap || runDays > gap.days) gap = { days: runDays, from: runFrom, to: iso };
            }
        }
        rows.push({ key, cells });
    }
    return { active, total, rows, gap };
}

/**
 * The held months the record covers whole. A statement that starts on the
 * 20th or ends on the 10th leaves a month with a few days of cargos, and a
 * trend, an extreme or a running total read over it would be about the gap
 * in the record, not about the month.
 */
export function completeMonths(held: EstadoMonth[], coverage: { start: string; end: string }): EstadoMonth[] {
    return held.filter((m) => {
        const first = monthKeyToDate(m.key);
        const from = isoOf(first);
        const to = isoOf(new Date(first.getFullYear(), first.getMonth() + 1, 0));
        return from >= coverage.start && to <= coverage.end;
    });
}

/** Least-squares slope of the held months' cargos, in pesos per month; null with fewer than three. */
export function trendOf(held: { amount: number }[]): number | null {
    const n = held.length;
    if (n < 3) return null;
    const xm = (n - 1) / 2;
    const ym = held.reduce((s, m) => s + m.amount, 0) / n;
    let num = 0, den = 0;
    held.forEach((m, i) => {
        num += (i - xm) * (m.amount - ym);
        den += (i - xm) ** 2;
    });
    return den > 0 ? num / den : 0;
}

/** The dearest and cheapest of the held months, and how many times one is the other. */
export function extremes(held: EstadoMonth[]): { max: EstadoMonth; min: EstadoMonth; ratio: number } | null {
    if (held.length < 2) return null;
    const max = held.reduce((b, m) => (m.amount > b.amount ? m : b), held[0]!);
    const min = held.reduce((b, m) => (m.amount < b.amount ? m : b), held[0]!);
    return { max, min, ratio: min.amount > 0 ? max.amount / min.amount : 0 };
}

/* ------------------------------------------------------------- Income */

export type PaydayReading = {
    /** The average month's running total, index 0 is the end of day 1. */
    curve: number[];
    /** The day the average month's running total reached the income; null when it never did. */
    crossDay: number | null;
    /** What the average month had left at its end; negative when it fell short. */
    leftover: number;
    perMonth: { key: MonthKey; crossDay: number | null; early: boolean }[];
};

/**
 * The day the month's income is spent. Per month, the first day whose running
 * total reaches the income; and over the average month, the curve the chart
 * draws. A month with no cargos on a day just carries the total forward.
 */
export function readPayday(byDate: Map<string, number>, held: MonthKey[], income: number): PaydayReading {
    const curve = Array.from({ length: 31 }, () => 0);
    const perMonth = held.map((key) => {
        const first = monthKeyToDate(key);
        const daysIn = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
        let cum = 0;
        let crossDay: number | null = null;
        for (let d = 1; d <= 31; d++) {
            if (d <= daysIn) cum += byDate.get(isoOf(new Date(first.getFullYear(), first.getMonth(), d))) ?? 0;
            curve[d - 1]! += cum;
            if (crossDay === null && cum >= income) crossDay = d;
        }
        return { key, crossDay, early: crossDay !== null && crossDay < daysIn };
    });
    const n = held.length || 1;
    for (let i = 0; i < 31; i++) curve[i]! /= n;
    const crossDay = curve.findIndex((v) => v >= income);
    return {
        curve,
        crossDay: crossDay === -1 ? null : crossDay + 1,
        leftover: income - curve[30]!,
        perMonth,
    };
}

export type CommittedReading = {
    /** What the pinned fijos cost per month, together. */
    fijos: number;
    /** The average month's cargos beyond the fijos. */
    variable: number;
    /** Income left after the average month; negative when it fell short. */
    margin: number;
    share: number;
    rows: RecurringItem[];
};

/** The month's committed money against what comes in and what the months actually cost. */
export function readCommitted(pinned: RecurringItem[], income: number, average: number): CommittedReading {
    const rows = [...pinned].sort((a, b) => b.monthly_equivalent - a.monthly_equivalent);
    const fijos = rows.reduce((s, i) => s + i.monthly_equivalent, 0);
    return {
        fijos,
        variable: Math.max(0, average - fijos),
        margin: income - Math.max(average, fijos),
        share: income > 0 ? fijos / income : 0,
        rows,
    };
}


/** Días 1–10, 11–20, 21–31: each stretch's share of the span's cargos. */
export function stretches(byDay: number[]): [number, number, number] {
    const sum = (a: number, b: number) => byDay.slice(a, b).reduce((s, v) => s + v, 0);
    const all = sum(0, 31) || 1;
    return [sum(0, 10) / all, sum(10, 20) / all, sum(20, 31) / all];
}

/** Share of the cargos that landed on a Saturday or Sunday. */
export function weekendShare(byWeekday: { amount: number }[]): number {
    const all = byWeekday.reduce((s, d) => s + d.amount, 0) || 1;
    return (byWeekday[5]!.amount + byWeekday[6]!.amount) / all;
}

/**
 * Money out against money in over the months that hold cargos: the factor
 * (pesos out per peso in) and the running gap, positive when it fell short.
 */
export function balanceAgainst(reading: EstadoReading, income: number) {
    const held = reading.months.filter((m) => m.count > 0);
    const gap = held.reduce((s, m) => s + (m.amount - income), 0);
    return {
        factor: income > 0 ? reading.average / income : 0,
        gap,
        over: held.filter((m) => m.amount > income).length,
        months: held.length,
    };
}

/** "el doble", "casi el triple"… — how a ratio sounds said out loud. */
export function ratioWords(ratio: number): string {
    if (ratio >= 2.8) return `${ratio.toFixed(1)} veces lo que ganas`;
    if (ratio >= 2.4) return "casi el triple";
    if (ratio >= 1.8) return "el doble";
    if (ratio >= 1.4) return "la mitad más";
    return "un poco más";
}

/** "se duplicó", "se triplicó" — only for a change worth naming. */
export function growthWords(ratio: number): string | null {
    if (ratio >= 3.5) return `se multiplicó por ${Math.round(ratio)}`;
    if (ratio >= 2.6) return "se triplicó";
    if (ratio >= 1.8) return "se duplicó";
    return null;
}
