/**
 * The Por mes reading: the same cargos as Por categoría, cut by calendar
 * month instead of by category, with each month's own composition inside it.
 *
 * The span is not the app's time window. "The last months" is a fixed shape —
 * six calendar months ending on the month of the newest movement on record —
 * because a rolling "30 días" has exactly one month in it and answers nothing
 * about the run. The eyebrow on the face says so.
 */

import type { Transaction } from "./api";
import type { CategoryInfo } from "./categories";
import { composeCategories, type Composition } from "./categoryComposition";
import type { WindowBounds } from "./window";

/** "2026-07". */
export type MonthKey = string;

export type MonthSlice = {
    key: MonthKey;
    amount: number;
    count: number;
    /** Share of the span's cargos, 0–1. */
    share: number;
    /** Biggest first: the rank the stone ramp is read by. */
    rank: number;
    /** The month read the way Por categoría reads a period. */
    composition: Composition;
};

export type MonthsReading = {
    /** Every month of the span, oldest first, including the ones with no
     *  cargos — the chart keeps their slot so the axis stays a calendar. */
    months: MonthSlice[];
    /** Only the months that hold cargos, newest first: the list. */
    listed: MonthSlice[];
    total: number;
    count: number;
    /** Mean over the months that hold cargos. A month with nothing on record
     *  is not a month of zero spending, so it does not pull the mean down. */
    average: number;
};

export const SPAN_MONTHS = 6;

function pad(n: number): string {
    return String(n).padStart(2, "0");
}

function iso(d: Date): string {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Local midnight for a local-date ISO; `new Date("2026-08-26")` would be UTC. */
export function fromIso(day: string): Date {
    const [y, m, d] = day.split("-").map(Number);
    return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function monthKeyOf(day: string): MonthKey {
    return day.slice(0, 7);
}

export function monthKeyToDate(key: MonthKey): Date {
    const [y, m] = key.split("-").map(Number);
    return new Date(y, (m ?? 1) - 1, 1);
}

/** The `SPAN_MONTHS` calendar months ending on the anchor's month, oldest first. */
export function spanMonthKeys(anchor: string, span = SPAN_MONTHS): MonthKey[] {
    const at = fromIso(anchor);
    const keys: MonthKey[] = [];
    for (let i = span - 1; i >= 0; i--) {
        const d = new Date(at.getFullYear(), at.getMonth() - i, 1);
        keys.push(`${d.getFullYear()}-${pad(d.getMonth() + 1)}`);
    }
    return keys;
}

/** First day of the span's first month through the anchor, inclusive. */
export function spanBounds(anchor: string, span = SPAN_MONTHS): WindowBounds {
    const first = spanMonthKeys(anchor, span)[0]!;
    return { start: iso(monthKeyToDate(first)), end: anchor };
}

/** A month's first and last day, inclusive local-date ISO. */
export function monthBounds(key: MonthKey): { start: string; end: string } {
    const [y, m] = key.split("-").map(Number);
    return { start: iso(new Date(y, (m ?? 1) - 1, 1)), end: iso(new Date(y, m ?? 1, 0)) };
}

export function composeMonths(
    items: Transaction[],
    categories: Map<string, CategoryInfo> | null,
    keys: MonthKey[]
): MonthsReading {
    const bags = new Map<MonthKey, Transaction[]>(keys.map((k) => [k, []]));
    for (const t of items) {
        const bag = bags.get(monthKeyOf(t.date));
        if (bag) bag.push(t);
    }

    const composed = keys.map((key) => ({
        key,
        composition: composeCategories(bags.get(key) ?? [], categories),
    }));
    const total = composed.reduce((s, m) => s + m.composition.spend, 0);
    const count = composed.reduce((s, m) => s + m.composition.spendCount, 0);

    const byAmount = [...composed].sort(
        (a, b) => b.composition.spend - a.composition.spend || a.key.localeCompare(b.key)
    );
    const rankOf = new Map(byAmount.map((m, i) => [m.key, i]));

    const months: MonthSlice[] = composed.map(({ key, composition }) => ({
        key,
        amount: composition.spend,
        count: composition.spendCount,
        share: total > 0 ? composition.spend / total : 0,
        rank: rankOf.get(key) ?? 0,
        composition,
    }));

    const held = months.filter((m) => m.count > 0);
    return {
        months,
        listed: [...held].reverse(),
        total,
        count,
        average: held.length > 0 ? total / held.length : 0,
    };
}

const MONTH_LONG = new Intl.DateTimeFormat("es-MX", { month: "long" });
const MONTH_LONG_YEAR = new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric" });

/** "julio", or "julio de 2025" when the span crosses a year boundary. */
export function monthName(key: MonthKey, withYear: boolean): string {
    const d = monthKeyToDate(key);
    return (withYear ? MONTH_LONG_YEAR : MONTH_LONG).format(d);
}

/** Whether the keys touch more than one calendar year. */
export function spansYears(keys: MonthKey[]): boolean {
    return new Set(keys.map((k) => k.slice(0, 4))).size > 1;
}

/* -------------------------------------------------------------------------- */
/* Gráficas v2                                                                 */
/* -------------------------------------------------------------------------- */

/** The anchor's month when the record stops before its last day: "al 6". */
export type PartialMonth = { key: MonthKey; day: number };

/**
 * v2: the span ends on the newest movement, so its last month is usually
 * still running. Counting it as a month of spending pulls the mean down by
 * however many days are missing — the chart marks it and the mean skips it.
 */
export function partialMonthOf(anchor: string): PartialMonth | null {
    const key = monthKeyOf(anchor);
    if (anchor >= monthBounds(key).end) return null;
    return { key, day: fromIso(anchor).getDate() };
}

/** v2: the mean over the months that hold cargos, the running one left out.
 *  Falls back to every held month when the running one is all there is. */
export function completeAverage(months: MonthSlice[], partial: MonthKey | null): number {
    const held = months.filter((m) => m.count > 0);
    const complete = held.filter((m) => m.key !== partial);
    const pool = complete.length > 0 ? complete : held;
    return pool.length > 0 ? pool.reduce((s, m) => s + m.amount, 0) / pool.length : 0;
}

/** v2: the month the title names — the biggest complete one, with how far it
 *  sits above the mean. Null when there is no run to compare against. */
export function peakMonth(
    months: MonthSlice[],
    average: number,
    partial: MonthKey | null
): { month: MonthSlice; over: number; lastComplete: boolean } | null {
    const complete = months.filter((m) => m.count > 0 && m.key !== partial);
    if (complete.length < 2 || average <= 0) return null;
    const month = complete.reduce((a, b) => (b.amount > a.amount ? b : a));
    if (month.amount <= average) return null;
    return {
        month,
        over: (month.amount - average) / average,
        // Against the window's last finished month, not its last month with
        // cargos: a quiet month after the peak still makes the peak not-last.
        lastComplete: month.key === months.filter((m) => m.key !== partial).at(-1)?.key,
    };
}
