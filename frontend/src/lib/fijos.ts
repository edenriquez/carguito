/**
 * The Fijos store: which series the user treats as committed, and how far
 * they plan. Not a panel config — those are primitives — and not session
 * checkboxes. A pin that dies when the next charge lands is not a pin.
 * `noiseOn` is leftover from a switch; the rest of recurrences is always
 * simulated now. Kept so old localStorage still parses.
 *
 * Persistence hides behind `FijosStore`, async on purpose even though
 * localStorage is sync — when this becomes a backend endpoint, no caller
 * changes. No React in this file.
 */

import type { RecurringItem, Transaction } from "./api";
import { matchMerchant, merchantBySlug } from "./merchants";
import { parsePeriodKey } from "./metrics";

export const FIJOS_VERSION = 1;
export const FIJOS_STORAGE_KEY = "carguito.fijos";

export const HORIZONS = [6, 12] as const;
export type Horizon = (typeof HORIZONS)[number];

export type Frequency = RecurringItem["frequency"];

/** A charge detection missed, added by hand. */
export type ManualFijo = {
    key: string;
    label: string;
    amount: number;
    frequency: Frequency;
    lastDate: string;
    categoryId: string | null;
};

/** A merchant you go to often, without a date to project. Smear, not a calendar. */
export type RestMark = {
    key: string;
    label: string;
    /** Curated merchant slug, or null for a free-text cluster. */
    merchant: string | null;
    needle: string;
};

export type FijosState = {
    version: typeof FIJOS_VERSION;
    pinnedKeys: string[];
    noiseOn: boolean;
    horizon: Horizon;
    manuals: ManualFijo[];
    restMarks: RestMark[];
};

export const DEFAULT_FIJOS: FijosState = {
    version: FIJOS_VERSION,
    pinnedKeys: [],
    noiseOn: false,
    horizon: 6,
    manuals: [],
    restMarks: [],
};

function isRecord(v: unknown): v is Record<string, unknown> {
    return typeof v === "object" && v !== null && !Array.isArray(v);
}

const FREQUENCIES: Frequency[] = ["weekly", "biweekly", "monthly", "bimonthly", "semiannual", "yearly"];

function isFrequency(v: unknown): v is Frequency {
    return typeof v === "string" && (FREQUENCIES as string[]).includes(v);
}

function isHorizon(v: unknown): v is Horizon {
    return v === 6 || v === 12;
}

function parseManual(raw: unknown): ManualFijo | null {
    if (!isRecord(raw)) return null;
    if (typeof raw.key !== "string" || !raw.key) return null;
    if (typeof raw.label !== "string" || !raw.label) return null;
    if (typeof raw.amount !== "number" || !Number.isFinite(raw.amount) || raw.amount <= 0) {
        return null;
    }
    if (!isFrequency(raw.frequency)) return null;
    if (typeof raw.lastDate !== "string") return null;
    return {
        key: raw.key,
        label: raw.label,
        amount: raw.amount,
        frequency: raw.frequency,
        lastDate: raw.lastDate,
        categoryId: typeof raw.categoryId === "string" ? raw.categoryId : null,
    };
}

function parseRestMark(raw: unknown): RestMark | null {
    if (!isRecord(raw)) return null;
    if (typeof raw.key !== "string" || !raw.key) return null;
    if (typeof raw.label !== "string" || !raw.label) return null;
    if (typeof raw.needle !== "string" || !raw.needle) return null;
    return {
        key: raw.key,
        label: raw.label,
        merchant: typeof raw.merchant === "string" && raw.merchant ? raw.merchant : null,
        needle: raw.needle,
    };
}

/**
 * Tolerant parse: garbage collapses to defaults. A corrupted localStorage
 * entry must not brick the planning number.
 */
export function parseFijos(raw: unknown): FijosState {
    if (!isRecord(raw) || raw.version !== FIJOS_VERSION) return DEFAULT_FIJOS;
    const pinnedKeys = Array.isArray(raw.pinnedKeys)
        ? raw.pinnedKeys.filter((k): k is string => typeof k === "string" && k.length > 0)
        : [];
    const unique = Array.from(new Set(pinnedKeys));
    const manuals = Array.isArray(raw.manuals)
        ? raw.manuals.map(parseManual).filter((m): m is ManualFijo => m !== null)
        : [];
    const restMarks = Array.isArray(raw.restMarks)
        ? raw.restMarks.map(parseRestMark).filter((m): m is RestMark => m !== null)
        : [];
    // A rest mark can be pinned (`pinRest`, or "Fijar" on a loose one), so
    // its key stays in `pinnedKeys`. Stripping rest keys here is what made
    // a pinned "resto" un-pin itself on every reload and face switch.
    return {
        version: FIJOS_VERSION,
        pinnedKeys: unique,
        noiseOn: raw.noiseOn === true,
        horizon: isHorizon(raw.horizon) ? raw.horizon : DEFAULT_FIJOS.horizon,
        manuals,
        restMarks,
    };
}

export interface FijosStore {
    load(): Promise<FijosState | null>;
    save(state: FijosState): Promise<void>;
}

export const localFijosStore: FijosStore = {
    async load() {
        if (typeof window === "undefined") return null;
        const raw = window.localStorage.getItem(FIJOS_STORAGE_KEY);
        if (raw === null) return null;
        try {
            return parseFijos(JSON.parse(raw));
        } catch {
            return DEFAULT_FIJOS;
        }
    },
    async save(state) {
        if (typeof window === "undefined") return;
        window.localStorage.setItem(FIJOS_STORAGE_KEY, JSON.stringify(state));
    },
};

const MONTHS = (
    "enero|febrero|marzo|abril|mayo|junio|julio|agosto" +
    "|septiembre|setiembre|octubre|noviembre|diciembre" +
    "|ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic"
);

/** Same date shapes RecurrenceService strips before grouping. */
const DATE_SHAPES = new RegExp(
    String.raw`\b\d{1,2}[-/. ]?(?:${MONTHS})[a-z]*[-/. ]?\d{2,4}\b` +
        String.raw`|\b(?:${MONTHS})[-/. ]?\d{1,2}[-/. ]?\d{2,4}\b` +
        String.raw`|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b` +
        String.raw`|\b\d{4}-\d{2}-\d{2}\b`,
    "gi"
);

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
 * Frontend twin of `series_key` in recurrence.py. A manual fijo stored under
 * this key merges into a later-detected series instead of living beside it.
 */
export function seriesKeyFromDescription(description: string): string {
    const withoutDates = description.replace(DATE_SHAPES, " ");
    const words = [];
    for (const token of normalize(withoutDates).split(" ")) {
        const digits = (token.match(/\d/g) ?? []).length;
        if (token.length >= 2 && digits <= token.length / 2) words.push(token);
    }
    return words.join(" ");
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

/** Turn a hand-added charge into something `buildTimeline` can project. */
export function itemFromManual(manual: ManualFijo): RecurringItem {
    const last = parsePeriodKey(manual.lastDate);
    const next = last ? stepForward(last, manual.frequency) : new Date();
    const days = CADENCE_DAYS[manual.frequency];
    return {
        key: manual.key,
        label: manual.label,
        occurrences: 1,
        frequency: manual.frequency,
        typical_amount: manual.amount,
        monthly_equivalent: (manual.amount * 30) / days,
        amount_stable: true,
        last_date: manual.lastDate,
        next_expected: isoDate(next),
        category_id: manual.categoryId,
        charges: [{ date: manual.lastDate, amount: manual.amount }],
    };
}

export function isRestKey(key: string): boolean {
    return key.startsWith("rest:");
}

export function restMarkFromTransaction(t: Transaction): RestMark {
    const raw = t.raw_description || t.description;
    const slug = matchMerchant(t.description) || matchMerchant(raw);
    if (slug) {
        return {
            key: `rest:merchant:${slug}`,
            label: merchantBySlug(slug)?.name ?? slug,
            merchant: slug,
            needle: slug,
        };
    }
    const needle = seriesKeyFromDescription(raw) || t.id;
    return {
        key: `rest:text:${needle}`,
        label: t.description,
        merchant: null,
        needle,
    };
}

export function transactionMatchesRest(t: Transaction, mark: RestMark): boolean {
    if (t.type !== "expense" || t.is_transfer || t.excluded_from_stats) return false;
    const raw = t.raw_description || t.description;
    if (mark.merchant) {
        return matchMerchant(t.description) === mark.merchant || matchMerchant(raw) === mark.merchant;
    }
    return (
        seriesKeyFromDescription(raw) === mark.needle ||
        seriesKeyFromDescription(t.description) === mark.needle
    );
}

function median(values: number[]): number {
    if (values.length === 0) return 0;
    const s = values.slice().sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
}

/** Typical monthly spend of a taught rest cluster — median of months, not a cadence. */
/**
 * What a taught merchant costs, as a rate and as a typical charge.
 *
 * `monthly` is total spend over **elapsed** months, not the median of the
 * months that happen to contain a charge. That distinction is the whole
 * function: the old median silently dropped the empty months in between, so
 * anything that does not land every month was counted at the rate of the
 * months it did land in. A bimonthly CFE bill came out at 2× its real cost, a
 * quarterly one at 3× — and because Plan smears this figure across every
 * future month, the error went straight into "esto se va fijo cada mes" and
 * into the yearly total.
 *
 * The span is inclusive and counted in calendar months, which is the unit the
 * answer is expressed in. One charge spans one month, and one charge is all we
 * can say from one charge.
 *
 * `typical` stays the median charge: the rate answers "how much does this cost
 * me a month", the typical answers "how big is one of these", and a utility
 * with a hot-summer spike wants the median for the second question.
 */
export function restMonthlyFromTransactions(txs: Transaction[]): {
    charges: { date: string; amount: number }[];
    typical: number;
    monthly: number;
} {
    const charges = txs.map((t) => ({ date: t.date, amount: Math.abs(t.amount) }));
    const amounts = charges.map((c) => c.amount);
    const total = amounts.reduce((sum, a) => sum + a, 0);
    return {
        charges,
        typical: median(amounts),
        monthly: charges.length === 0 ? 0 : total / spanInMonths(charges),
    };
}

/** Calendar months from the first charge to the last, inclusive — empty months
 *  included, which is exactly what the old per-month median left out. */
function spanInMonths(charges: { date: string }[]): number {
    let first = charges[0]!.date;
    let last = first;
    for (const c of charges) {
        if (c.date < first) first = c.date;
        if (c.date > last) last = c.date;
    }
    const months = (iso: string) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7));
    return Math.max(1, months(last) - months(first) + 1);
}

export function itemFromRestMark(mark: RestMark, ledger: Transaction[]): RecurringItem | null {
    const txs = ledger.filter((t) => transactionMatchesRest(t, mark));
    if (txs.length === 0) return null;
    const { charges, typical, monthly } = restMonthlyFromTransactions(txs);
    const last = charges.reduce((a, b) => (a.date > b.date ? a : b));
    const cats = new Map<string | null, number>();
    for (const t of txs) {
        cats.set(t.category_id, (cats.get(t.category_id) ?? 0) + 1);
    }
    const category_id = [...cats.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
    return {
        key: mark.key,
        label: mark.label,
        occurrences: charges.length,
        // Not a claim about a rhythm — a taught merchant has none, which is why
        // Plan smears it and Pagos leaves it off the calendar entirely. It says
        // only which unit `monthly_equivalent` is expressed in.
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

/**
 * If detection later finds a series a manual was standing in for, pin the
 * detected key and drop the manual so the same money is not counted twice.
 */
export function reconcileFijos(state: FijosState, detected: RecurringItem[]): FijosState {
    const detectedKeys = new Set(detected.map((i) => i.key));
    const kept: ManualFijo[] = [];
    const pinned = new Set(state.pinnedKeys);
    for (const manual of state.manuals) {
        if (detectedKeys.has(manual.key)) {
            pinned.add(manual.key);
        } else {
            kept.push(manual);
        }
    }
    const pinnedKeys = Array.from(pinned);
    const same =
        pinnedKeys.length === state.pinnedKeys.length &&
        pinnedKeys.every((k, i) => k === state.pinnedKeys[i]) &&
        kept.length === state.manuals.length;
    if (same) return state;
    return { ...state, pinnedKeys, manuals: kept };
}

/** The fijos that enter a projection — detected pins, manuals, taught rest. */
export function pinnedItems(
    state: FijosState,
    detected: RecurringItem[],
    ledger: Transaction[]
): RecurringItem[] {
    const manuals = state.manuals.map(itemFromManual);
    const taught = (state.restMarks ?? [])
        .map((m) => itemFromRestMark(m, ledger))
        .filter((i): i is RecurringItem => i !== null);
    const pinnedRest = taught.filter((i) => state.pinnedKeys.includes(i.key));
    const fromDetected = detected.filter((i) => state.pinnedKeys.includes(i.key));
    const detectedKeys = new Set(fromDetected.map((i) => i.key));
    return [
        ...fromDetected,
        ...manuals.filter((m) => !detectedKeys.has(m.key)),
        ...pinnedRest,
    ];
}
