/**
 * The one set of fake-but-plausible numbers the landing quotes. They belong to
 * an example user, not to anyone real, and the page says so ("cifras de
 * ejemplo"). Everything is in pesos and plain: the opinion lives in the
 * headlines, never in a figure (docs/voice-and-type.md).
 */
export const FIGURES = {
    /**
     * The hero number: what the sub-headline promises ("señala los cobros que
     * se repiten") shown as a figure: the recurring charges one statement
     * surfaced. The same figure the Plan card details below.
     */
    heroAmount: "$487.00",
    heroAmountUnit: "/mes",
    heroCaption: "en 3 cobros que se repiten y no recordabas, encontrados en un solo estado de cuenta",

    movements: 214,
    /** Attention readings on that statement: unusual charges, duplicates, new merchants. */
    attentionCount: 3,

    categoriesTop: "Súper",
    categoriesTopShare: "31%",

    fixedCount: 3,
    fixedMonthly: "$487.00",
    fixedCaption: "que no recordabas",

    forecastNeed: "$9,140",

    ticketStore: "SORIANA",
    ticketTotal: "$1,412.60",
    ticketItem: "Leche 1L",
    ticketDelta: "+19%",
    /** A card title, so no full stop. */
    ticketLine: "La leche te subió 19%",
} as const;

/** Scatter dots for the story and the Movimientos mock, in a 0–100 × 0–80 box. */
export const SCATTER: ReadonlyArray<readonly [number, number, number]> = [
    [8, 62, 3], [16, 70, 3], [22, 55, 3.5], [30, 66, 3], [36, 48, 3],
    [44, 60, 3.5], [52, 68, 3], [58, 52, 3], [66, 63, 3], [74, 58, 3.5],
    [82, 66, 3], [90, 50, 3], [40, 30, 3], [70, 36, 3],
];

/** The outlier: the reason the scatter exists. */
export const OUTLIER: readonly [number, number, number] = [62, 12, 4.5];

/** Month stacks [dark, mid, signal] for the Categorías mock. */
export const STACKS: ReadonlyArray<readonly [number, number, number]> = [
    [26, 14, 8], [18, 20, 10], [30, 10, 12], [22, 16, 8], [34, 12, 10],
];

/** Calendar cells with a charge (0–41, 14 columns × 3 rows). */
export const CHARGED = new Set([2, 9, 16, 23, 30, 37]);

/**
 * What the backend can read today, by how well it reads it. Mirrors
 * `backend/src/carguito/adapters/outbound/extraction/classifier.py` and
 * `parsing/factory.py`: two banks have a parser written for their layout;
 * the rest are recognised by name and read with the generic parser; the SAT
 * XML has its own reader. Keep this list honest — it is the one place the
 * landing makes a checkable claim.
 */
export const BANKS = {
    dedicated: ["Banamex", "Banco Azteca"],
    generic: ["Nu", "BBVA", "Santander", "Banorte", "HSBC"],
    sat: "XML del SAT (CFDI)",
} as const;
