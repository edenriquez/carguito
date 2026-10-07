/**
 * What a series' charge dates say about *when* it hits.
 *
 * The detector already asserts a cadence ("monthly"); this answers the sharper
 * question the calendar makes askable — which weekday, which day of the month.
 * Both are claims about the user's money, so both have a floor: below it the
 * honest answer is "no fixed day", not a weekday that happened to win 3-to-2.
 */

import type { RecurringCharge } from "@/lib/api";
import { parsePeriodKey } from "@/lib/metrics";

/** Monday-first, matching the calendar grid. */
const WEEKDAY_NAMES = [
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábados",
    "domingos",
];

/** A pattern needs to hold in most of the charges to be worth stating. */
const DOMINANT = 0.6;

function mode<T>(values: T[]): { value: T; share: number } | null {
    if (!values.length) return null;
    const counts = new Map<T, number>();
    for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
    let best: T = values[0];
    let bestCount = 0;
    counts.forEach((n, v) => {
        if (n > bestCount) {
            best = v;
            bestCount = n;
        }
    });
    return { value: best, share: bestCount / values.length };
}

function median(values: number[]): number {
    const s = [...values].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
}

/**
 * One sentence for the expanded row, e.g. "Casi siempre los martes, alrededor
 * del día 5." Returns null when the dates show no pattern worth claiming.
 */
export function rhythmCopy(
    charges: RecurringCharge[],
    frequency: string
): string | null {
    const dates = charges
        .map((c) => parsePeriodKey(c.date))
        .filter((d): d is Date => d !== null);
    if (dates.length < 3) return null;

    const parts: string[] = [];

    // Weekday: the fact that matters for a weekly or biweekly rhythm.
    const weekday = mode(dates.map((d) => (d.getDay() + 6) % 7));
    if (weekday && weekday.share >= DOMINANT) {
        const name = WEEKDAY_NAMES[weekday.value];
        parts.push(`${weekday.share >= 0.85 ? "Siempre" : "Casi siempre"} los ${name}`);
    }

    // Day of month: the fact that matters for a monthly or yearly rhythm.
    if (frequency === "monthly" || frequency === "bimonthly" || frequency === "semiannual" || frequency === "yearly") {
        const days = dates.map((d) => d.getDate());
        const typical = median(days);
        const near = days.filter((d) => Math.abs(d - typical) <= 3).length / days.length;
        if (near >= DOMINANT) {
            const exact = days.every((d) => d === typical);
            parts.push(
                parts.length
                    ? `${exact ? "el" : "alrededor del"} día ${typical}`
                    : `${exact ? "Siempre el" : "Alrededor del"} día ${typical}`
            );
        }
    }

    if (!parts.length) return null;
    return `${parts.join(", ")}.`;
}

/** Day of month the series usually lands, or null when the dates wander. */
export function typicalDayOfMonth(charges: RecurringCharge[]): number | null {
    const days = charges
        .map((c) => parsePeriodKey(c.date))
        .filter((d): d is Date => d !== null)
        .map((d) => d.getDate());
    if (days.length === 0) return null;
    if (days.length === 1) return days[0]!;
    const typical = median(days);
    const near = days.filter((d) => Math.abs(d - typical) <= 3).length / days.length;
    return near >= DOMINANT ? typical : null;
}
