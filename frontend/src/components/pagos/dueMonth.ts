/**
 * One month of recurring charges: what already landed, what still has to be
 * paid, and what comes after. The grid and the list read from this so they
 * cannot disagree.
 */

import type { RecurringItem } from "@/lib/api";
import { matchMerchant } from "@/lib/merchants";
import { parsePeriodKey } from "@/lib/metrics";
import { futureCharges, isStale, ledgerEnd, monthKeyOf, today } from "@/components/recurrentes/projection";

const DAY = 86_400_000;

export type Urgency = "urgent" | "soon" | "later";

export type DueLine = {
    key: string;
    label: string;
    amount: number;
    date: Date;
    iso: string;
    urgency: Urgency | null;
    status: "registered" | "due";
    /** The series' rhythm, for the row's meta. Absent on a card payment. */
    frequency?: RecurringItem["frequency"];
    /** False when the series recurs but the amount moves (a utility bill):
     *  the projected figure is then an estimate and is written as one. */
    stable?: boolean;
};

/**
 * The payment a card statement asks for: one dated line that is not a
 * series. Read off the statement itself, so it lands on the calendar with
 * the same standing as a projected charge but none of its guesswork.
 */
export type CardPayment = {
    key: string;
    label: string;
    amount: number;
    date: Date;
    iso: string;
};

export type DuePair = {
    currentMonth: Date;
    nextMonth: Date;
    currentCells: DayCell[];
    nextCells: DayCell[];
    /** Landed or still due inside the current month. */
    thisMonth: DueLine[];
    /** Projected landings in the following month. */
    upcoming: DueLine[];
};

export type DayCell = {
    date: Date;
    iso: string;
    /** Outside the selected month — drawn, but mute. */
    outside: boolean;
    weekend: boolean;
    today: boolean;
    /** Measured charges that already landed. */
    registered: number;
    /** Simulated landings still ahead. */
    due: number;
    dueLabels: string[];
    registeredLabels: string[];
    urgency: Urgency | null;
};

export type DueMonth = {
    month: Date;
    cells: DayCell[][];
    /** Remaining this month — the "tienes que pagar" list. */
    dueThisMonth: DueLine[];
    /** First landing after this month. */
    upcoming: DueLine[];
    /** Already landed in this month. */
    registered: DueLine[];
    dueTotal: number;
    upcomingTotal: number;
    canGoForward: boolean;
    canGoBack: boolean;
};

export function isoOf(d: Date): string {
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${m}-${day}`;
}

export function startOfWeek(d: Date): Date {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
    return x;
}

export function startOfMonth(d: Date): Date {
    return new Date(d.getFullYear(), d.getMonth(), 1);
}

export function endOfMonth(d: Date): Date {
    return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

export function shiftMonth(d: Date, delta: number): Date {
    return new Date(d.getFullYear(), d.getMonth() + delta, 1);
}

/** How soon a future day is. Today and tomorrow are urgent. */
export function urgencyOf(date: Date, asOf: Date = today()): Urgency | null {
    const a = new Date(asOf.getFullYear(), asOf.getMonth(), asOf.getDate());
    const b = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const days = Math.round((b.getTime() - a.getTime()) / DAY);
    if (days < 0) return null;
    if (days <= 2) return "urgent";
    if (days <= 7) return "soon";
    return "later";
}

const BACK_MONTHS = 12;

/**
 * Places you walk into. The ticket changes every visit, and a handful of
 * them can still land inside a bimonthly window — that is not a bill.
 * Same slugs as the merchant list.
 */
const STORE_SLUGS = new Set([
    "oxxo",
    "seven-eleven",
    "bodega-aurrera",
    "walmart",
    "soriana",
    "chedraui",
    "costco",
    "heb",
]);

function isStoreVisit(item: RecurringItem): boolean {
    const slug = matchMerchant(item.label) ?? matchMerchant(item.key);
    return slug !== null && STORE_SLUGS.has(slug);
}

/**
 * A payment to anticipate, not a store the user happens to visit.
 *
 * `amount_stable` is the rule: a subscription barely moves charge to charge.
 * A bill can still move — CFE, a semestral policy — when the cadence itself
 * is the bill (bimonthly, semiannual). A store (OXXO, Walmart, Bodega) is
 * neither, even when a few visits happen to sit on that cadence.
 */
export function isScheduledPayment(item: RecurringItem): boolean {
    if (isStoreVisit(item)) return false;
    if (item.amount_stable) return true;
    return item.frequency === "bimonthly" || item.frequency === "semiannual";
}

export function buildDueMonth(
    items: RecurringItem[],
    month: Date,
    asOf: Date = today()
): DueMonth {
    const now = today();
    const monthStart = startOfMonth(month);
    const monthEnd = endOfMonth(month);
    const current = startOfMonth(now);
    const earliest = shiftMonth(current, -(BACK_MONTHS - 1));
    const ledgerAsOf = items.length ? ledgerEnd(items) : asOf;

    const active = items.filter((i) => isScheduledPayment(i) && !isStale(i, ledgerAsOf));

    const registeredByIso = new Map<string, DueLine[]>();
    const dueByIso = new Map<string, DueLine[]>();

    for (const item of active) {
        for (const c of item.charges ?? []) {
            const d = parsePeriodKey(c.date);
            if (!d) continue;
            if (d < monthStart || d > monthEnd) continue;
            const iso = isoOf(d);
            const line: DueLine = {
                key: `${item.key}:${iso}:r`,
                label: item.label,
                amount: Math.abs(c.amount),
                date: d,
                iso,
                urgency: null,
                status: "registered",
                frequency: item.frequency,
                stable: item.amount_stable,
            };
            registeredByIso.set(iso, [...(registeredByIso.get(iso) ?? []), line]);
        }

        // Project from today through the end of next month so "próximos" has
        // somewhere to land when this month is almost over.
        const horizon = endOfMonth(shiftMonth(monthStart, 1));
        for (const landing of futureCharges(item, horizon, now, ledgerAsOf)) {
            const iso = isoOf(landing.date);
            const line: DueLine = {
                key: `${item.key}:${iso}:d`,
                label: item.label,
                amount: Math.abs(landing.amount),
                date: landing.date,
                iso,
                urgency: urgencyOf(landing.date, now),
                status: "due",
                frequency: item.frequency,
                stable: item.amount_stable,
            };
            dueByIso.set(iso, [...(dueByIso.get(iso) ?? []), line]);
        }
    }

    const dueThisMonth: DueLine[] = [];
    const upcoming: DueLine[] = [];
    const registered: DueLine[] = [];

    for (const lines of registeredByIso.values()) registered.push(...lines);
    for (const lines of dueByIso.values()) {
        for (const line of lines) {
            if (line.date >= monthStart && line.date <= monthEnd) dueThisMonth.push(line);
            else if (line.date > monthEnd) upcoming.push(line);
        }
    }

    dueThisMonth.sort((a, b) => a.date.getTime() - b.date.getTime());
    upcoming.sort((a, b) => a.date.getTime() - b.date.getTime());
    registered.sort((a, b) => a.date.getTime() - b.date.getTime());

    // One row per series in "próximos": the soonest landing after this month.
    const soonestUpcoming = new Map<string, DueLine>();
    for (const line of upcoming) {
        const id = line.key.split(":")[0] ?? line.key;
        if (!soonestUpcoming.has(id)) soonestUpcoming.set(id, line);
    }
    const upcomingUnique = Array.from(soonestUpcoming.values()).sort(
        (a, b) => a.date.getTime() - b.date.getTime()
    );

    const gridStart = startOfWeek(monthStart);
    const gridEnd = startOfWeek(monthEnd);
    gridEnd.setDate(gridEnd.getDate() + 6);

    const weeks: DayCell[][] = [];
    const cursor = new Date(gridStart);
    const todayIso = isoOf(now);
    while (cursor <= gridEnd) {
        const week: DayCell[] = [];
        for (let i = 0; i < 7; i++) {
            const date = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate());
            const iso = isoOf(date);
            const regs = registeredByIso.get(iso) ?? [];
            const dues = dueByIso.get(iso) ?? [];
            const inMonth = date >= monthStart && date <= monthEnd;
            week.push({
                date,
                iso,
                outside: !inMonth,
                weekend: i >= 5,
                today: iso === todayIso,
                registered: regs.reduce((s, l) => s + l.amount, 0),
                due: dues.reduce((s, l) => s + l.amount, 0),
                dueLabels: dues.map((l) => l.label),
                registeredLabels: regs.map((l) => l.label),
                urgency: dues[0]?.urgency ?? null,
            });
            cursor.setDate(cursor.getDate() + 1);
        }
        weeks.push(week);
    }

    return {
        month: monthStart,
        cells: weeks,
        dueThisMonth,
        upcoming: upcomingUnique,
        registered,
        dueTotal: dueThisMonth.reduce((s, l) => s + l.amount, 0),
        upcomingTotal: upcomingUnique.reduce((s, l) => s + l.amount, 0),
        canGoForward: monthKeyOf(monthStart) < monthKeyOf(current),
        canGoBack: monthKeyOf(monthStart) > monthKeyOf(earliest),
    };
}

/**
 * The same month with the card payment on it, when there is one to place.
 *
 * Only a payment still ahead is drawn: a due date that already passed is
 * either paid (and then it is a movement, read where movements are) or
 * missed, and a calendar of projections is not where that gets said. Beyond
 * the month after this one it is out of frame, like every other landing.
 */
export function withCardPayment(
    month: DueMonth,
    card: CardPayment | null,
    asOf: Date = today()
): DueMonth {
    if (!card) return month;
    const now = new Date(asOf.getFullYear(), asOf.getMonth(), asOf.getDate());
    if (card.date < now) return month;
    const monthEnd = endOfMonth(month.month);
    const horizon = endOfMonth(shiftMonth(month.month, 1));
    if (card.date > horizon) return month;

    const line: DueLine = {
        key: card.key,
        label: card.label,
        amount: card.amount,
        date: card.date,
        iso: card.iso,
        urgency: urgencyOf(card.date, now),
        status: "due",
        stable: true,
    };
    const byDate = (a: DueLine, b: DueLine) => a.date.getTime() - b.date.getTime();

    if (card.date > monthEnd) {
        const upcoming = [...month.upcoming, line].sort(byDate);
        return {
            ...month,
            upcoming,
            upcomingTotal: month.upcomingTotal + line.amount,
        };
    }

    const cells = month.cells.map((week) =>
        week.map((cell) =>
            cell.iso === card.iso
                ? {
                      ...cell,
                      due: cell.due + line.amount,
                      dueLabels: [...cell.dueLabels, line.label],
                      urgency: cell.urgency ?? line.urgency,
                  }
                : cell
        )
    );
    return {
        ...month,
        cells,
        dueThisMonth: [...month.dueThisMonth, line].sort(byDate),
        dueTotal: month.dueTotal + line.amount,
    };
}

/**
 * Current month + the next one. The calendar always shows this pair; the
 * tables read the same lines so a selected day cannot disagree with a row.
 */
export function buildDuePair(items: RecurringItem[], asOf: Date = today()): DuePair {
    const currentMonth = startOfMonth(asOf);
    const nextMonth = shiftMonth(currentMonth, 1);
    const current = buildDueMonth(items, currentMonth, asOf);
    const next = buildDueMonth(items, nextMonth, asOf);

    const registeredByIso = groupByIso([...current.registered, ...next.registered]);
    const dueByIso = groupByIso([...current.dueThisMonth, ...next.dueThisMonth]);

    const thisMonth = [...current.registered, ...current.dueThisMonth].sort(
        (a, b) => a.date.getTime() - b.date.getTime() || a.label.localeCompare(b.label, "es-MX")
    );
    const upcoming = next.dueThisMonth.slice();

    return {
        currentMonth,
        nextMonth,
        currentCells: sundayGrid(currentMonth, registeredByIso, dueByIso, asOf),
        nextCells: sundayGrid(nextMonth, registeredByIso, dueByIso, asOf),
        thisMonth,
        upcoming,
    };
}

function groupByIso(lines: DueLine[]): Map<string, DueLine[]> {
    const map = new Map<string, DueLine[]>();
    for (const line of lines) {
        map.set(line.iso, [...(map.get(line.iso) ?? []), line]);
    }
    return map;
}

/**
 * Sunday-first month grid for the Pagos calendar.
 *
 * It used to say "same skeleton as FechaMiniCalendario"; that file is gone —
 * the date criterion now uses `react-day-picker`. This grid still starts on
 * Sunday, which is wrong for a Mexican product the same way that one was, and
 * is a separate change: the name `sundayGrid` is load-bearing for its callers.
 */
export function sundayGrid(
    month: Date,
    registeredByIso: Map<string, DueLine[]>,
    dueByIso: Map<string, DueLine[]>,
    asOf: Date = today()
): DayCell[] {
    const year = month.getFullYear();
    const mo = month.getMonth();
    const startPad = new Date(year, mo, 1).getDay();
    const days = new Date(year, mo + 1, 0).getDate();
    const todayIso = isoOf(asOf);
    const cells: DayCell[] = [];

    const cellOf = (date: Date, outside: boolean): DayCell => {
        const iso = isoOf(date);
        const regs = registeredByIso.get(iso) ?? [];
        const dues = dueByIso.get(iso) ?? [];
        return {
            date,
            iso,
            outside,
            weekend: date.getDay() === 0 || date.getDay() === 6,
            today: iso === todayIso && !outside,
            registered: regs.reduce((s, l) => s + l.amount, 0),
            due: dues.reduce((s, l) => s + l.amount, 0),
            dueLabels: dues.map((l) => l.label),
            registeredLabels: regs.map((l) => l.label),
            urgency: dues[0]?.urgency ?? null,
        };
    };

    for (let i = startPad - 1; i >= 0; i--) {
        cells.push(cellOf(new Date(year, mo, -i), true));
    }
    for (let day = 1; day <= days; day++) {
        cells.push(cellOf(new Date(year, mo, day), false));
    }
    while (cells.length % 7 !== 0) {
        const last = cells[cells.length - 1]!;
        const next = new Date(last.date);
        next.setDate(next.getDate() + 1);
        cells.push(cellOf(next, true));
    }
    return cells;
}
