/**
 * The Por categoría reading: the same dated+filtered set, grouped.
 *
 * Transfers and rows left out of stats stay in the modal; they do not take
 * a slice of the bar. Percents are of this set's cargos, never of "all time".
 */

import type { Transaction } from "./api";
import {
    categoryColor,
    categoryName,
    isUncategorizedId,
    isUncategorizedName,
    rootCategoryId,
    type CategoryInfo,
    UNCATEGORIZED_COLOR,
} from "./categories";
import { chart, colors } from "@/design/tokens";
import { UNCATEGORIZED } from "./movimientosQuery";

/** The bag for cargos sitting on the root itself, with no subcategory. */
export const DIRECT = "__directo__";

/**
 * One subcategory inside a category — or, under `DIRECT`, the cargos filed on
 * the root and nowhere deeper.
 */
export type SubGroup = {
    key: string;
    name: string;
    amount: number;
    count: number;
    /** Share of the *parent category's* cargos, 0–1 — "% del grupo". */
    share: number;
    /** Every cargo in the group, newest first. Nothing is capped: the whole
     *  point of opening a category is reading what is inside it. */
    charges: Transaction[];
};

export type CategorySlice = {
    key: string;
    name: string;
    amount: number;
    count: number;
    /** Share of the set's cargos, 0–1. */
    share: number;
    uncategorized: boolean;
    /** Subcategories, biggest first, `DIRECT` last when present. */
    groups: SubGroup[];
};

export type Composition = {
    slices: CategorySlice[];
    /** Slices in bar order: biggest first, uncategorized last. */
    bar: CategorySlice[];
    spend: number;
    income: number;
    spendCount: number;
    incomeCount: number;
    movementCount: number;
    /** What came in, newest first. Not a slice of the bar — the bar answers
     *  "where did the money go", and an abono is not a destination. */
    abonos: Transaction[];
    /** Money that moved between the user's own accounts, plus anything the
     *  user excluded from stats: in the ledger, out of every percentage. */
    aparte: Transaction[];
    aparteTotal: number;
};

const spendable = (t: Transaction) =>
    t.type === "expense" && !t.is_transfer && !t.excluded_from_stats;

const incoming = (t: Transaction) =>
    t.type === "income" && !t.is_transfer && !t.excluded_from_stats;

export function composeCategories(
    items: Transaction[],
    categories: Map<string, CategoryInfo> | null
): Composition {
    const spendTx = items.filter(spendable);
    const incomeTx = items.filter(incoming);
    const asideTx = items.filter((t) => t.is_transfer || t.excluded_from_stats);
    const spend = spendTx.reduce((s, t) => s + t.amount, 0);
    const income = incomeTx.reduce((s, t) => s + t.amount, 0);

    const bags = new Map<string, Transaction[]>();
    for (const t of spendTx) {
        const root = rootCategoryId(categories, t.category_id);
        const key =
            !t.category_id || isUncategorizedId(categories, root)
                ? UNCATEGORIZED
                : (root ?? t.category_id);
        const bag = bags.get(key);
        if (bag) bag.push(t);
        else bags.set(key, [t]);
    }

    const slices: CategorySlice[] = Array.from(bags.entries()).map(([key, txs]) => {
        const amount = txs.reduce((s, t) => s + t.amount, 0);
        const named = categoryName(categories, key === UNCATEGORIZED ? null : key);
        const uncategorized = isUncategorized(key, named);
        return {
            key,
            name: uncategorized ? "Sin categoría" : named,
            amount,
            count: txs.length,
            share: spend > 0 ? amount / spend : 0,
            uncategorized,
            groups: groupBySub(txs, key, amount, categories),
        };
    });

    const ranked = slices
        .filter((s) => !s.uncategorized)
        .sort((a, b) => b.amount - a.amount || a.name.localeCompare(b.name, "es-MX"));
    const none = slices.filter((s) => s.uncategorized);
    const accordion = [...none, ...ranked];
    const bar = [...ranked, ...none];

    return {
        slices: accordion,
        bar,
        spend,
        income,
        spendCount: spendTx.length,
        incomeCount: incomeTx.length,
        movementCount: items.length,
        abonos: byDateDesc(incomeTx),
        aparte: byDateDesc(asideTx),
        aparteTotal: asideTx.reduce((s, t) => s + t.amount, 0),
    };
}

/** Newest first, id as the tiebreak so the order is stable across renders. */
function byDateDesc(rows: Transaction[]): Transaction[] {
    return [...rows].sort(
        (a, b) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id)
    );
}

/**
 * Split one category's cargos by subcategory.
 *
 * The share is of the parent, not of the whole set: inside Transporte, what
 * the user is asking is "how much of *this* is gasolina", and a percentage of
 * total spend would answer a question nobody asked at that depth.
 */
function groupBySub(
    txs: Transaction[],
    rootKey: string,
    rootAmount: number,
    categories: Map<string, CategoryInfo> | null
): SubGroup[] {
    const bags = new Map<string, Transaction[]>();
    for (const t of txs) {
        const leaf = t.category_id && t.category_id !== rootKey ? t.category_id : DIRECT;
        const bag = bags.get(leaf);
        if (bag) bag.push(t);
        else bags.set(leaf, [t]);
    }

    const groups = Array.from(bags.entries()).map<SubGroup>(([key, rows]) => {
        const amount = rows.reduce((s, t) => s + t.amount, 0);
        return {
            key,
            name: key === DIRECT ? "Sin subcategoría" : categoryName(categories, key),
            amount,
            count: rows.length,
            share: rootAmount > 0 ? amount / rootAmount : 0,
            charges: [...rows].sort(
                (a, b) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id)
            ),
        };
    });

    // Biggest first, like the categories above them; the unfiled bag sinks to
    // the bottom whatever it weighs — it is a gap, not a group.
    return groups.sort((a, b) => {
        if ((a.key === DIRECT) !== (b.key === DIRECT)) return a.key === DIRECT ? 1 : -1;
        return b.amount - a.amount || a.name.localeCompare(b.name, "es-MX");
    });
}

function isUncategorized(key: string, name: string): boolean {
    if (key === UNCATEGORIZED) return true;
    return isUncategorizedName(name);
}

/** Stone ramp by rank. Hue is not the category channel — Signal marks the
 *  selected slice only. Leftover is the lightest step. */
export function barFill(rank: number, uncategorized: boolean, selected = false): string {
    if (selected) return colors.signal;
    if (uncategorized) return chart.neutral[chart.neutral.length - 1]!;
    return chart.neutral[Math.min(rank, chart.neutral.length - 1)]!;
}

/** v2: a category slice wears its taxonomy color, the same swatch it has in
 *  every other view; a focus fades the rest rather than recoloring anything.
 *  The gap is Ash, like an uncategorized row anywhere else. */
export function sliceColor(
    slice: CategorySlice,
    categories: Map<string, CategoryInfo> | null
): string {
    return slice.uncategorized ? UNCATEGORIZED_COLOR : categoryColor(categories, slice.key);
}

export function pct(share: number): number {
    return Math.round(share * 100);
}

/**
 * The charges whose merchant shows up three times or more *in this reading*.
 *
 * Deliberately not the fijos detector: that one answers "is this a series with
 * a rhythm" over twelve months of ledger, and it is the right answer for Plan.
 * Here the question is smaller and local — "have I seen this name already on
 * this screen" — so the claim the ↻ makes is only about the period on screen,
 * and it costs one pass over rows that are already in memory.
 *
 * Digits are dropped before comparing: a folio or a terminal number is the
 * one part of a bank string guaranteed to differ between two charges at the
 * same merchant.
 */
export function repeatedCharges(items: Transaction[]): Set<string> {
    const byMerchant = new Map<string, string[]>();
    for (const t of items) {
        const key = merchantKey(t.description);
        if (!key) continue;
        const bag = byMerchant.get(key);
        if (bag) bag.push(t.id);
        else byMerchant.set(key, [t.id]);
    }
    const out = new Set<string>();
    for (const ids of byMerchant.values()) {
        if (ids.length < 3) continue;
        for (const id of ids) out.add(id);
    }
    return out;
}

function merchantKey(description: string): string {
    return description
        .toLowerCase()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/[^a-z]+/g, " ")
        .trim();
}
