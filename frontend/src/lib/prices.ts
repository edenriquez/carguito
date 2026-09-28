/**
 * Typed client for photographed tickets and the price history built from them.
 *
 * The shape worth noticing is `basis`. The backend decides whether a product
 * compares per litre/kilo or per piece, and ships every figure already in that
 * basis — this client never re-derives it. A second implementation of "which
 * unit are we comparing in" is a second chance to disagree with the first, and
 * disagreeing here means telling someone a 2-litre bottle is dearer than a
 * 600-ml one.
 */

import { request } from "./api";

/** One purchase of one product: the atom of the whole comparison. */
export type PricePoint = {
    receipt_id: string;
    transaction_id: string | null;
    /** The date printed on the ticket, when the reader could find one. */
    purchased_at: string | null;
    /** When the photo was taken. The fallback date when `purchased_at` is
     *  null: a ticket can be photographed days after the trip, so anything
     *  drawn on it says "≈". ISO datetime without offset. */
    captured_at: string | null;
    store: string | null;
    /** As printed on that ticket, which is not always how it reads today. */
    description: string;
    amount: number;
    quantity: number | null;
    each: number | null;
    per_base_unit: number | null;
    size: number | null;
    size_unit: string | null;
    /** The figure this product is compared by, in the product's `basis`. */
    value: number | null;
};

export type ProductPrices = {
    product_key: string;
    name: string;
    /** "unit" = per litre/kilo · "each" = per piece. Always shown to the user:
     *  two prices in different bases do not compare, and saying which one is in
     *  play is the difference between a comparison and a coincidence. */
    basis: "unit" | "each";
    times_bought: number;
    /** How many of those purchases carried a comparable figure. */
    priced: number;
    median: number | null;
    /** Dearest over cheapest, in %. `null` with fewer than two priced buys —
     *  a single price has no spread, and 0% would read as "always the same". */
    spread: number | null;
    /** The last purchase against the typical one, in %. Positive is worse. */
    latest_vs_median: number | null;
    stores: string[];
    cheapest: PricePoint | null;
    dearest: PricePoint | null;
    latest: PricePoint | null;
    /** Only on the detail endpoint; the list ships summaries. */
    points?: PricePoint[];
};

export type ReceiptItem = {
    id: string;
    line_no: number;
    /** The OCR line behind every other field here. The evidence. */
    raw_text: string;
    description: string;
    product_key: string;
    amount: number;
    quantity: number | null;
    unit_price: number | null;
    size: number | null;
    size_unit: string | null;
    each: number | null;
    per_base_unit: number | null;
};

export type Receipt = {
    id: string;
    transaction_id: string | null;
    /** "auto" while the matcher decided; "user" once a person did. */
    match_source: string;
    store: string | null;
    purchased_at: string | null;
    total: number | null;
    currency: string;
    /** Which OCR engine read the photo, and which reader structured the lines. */
    extractor: string;
    reader: string;
    captured_at: string | null;
    created_at: string | null;
    /** What the lines add up to. Compare against `total`: OCR drops lines, and
     *  a silently short basket is worse than a visible gap. */
    items_total: number;
    items: ReceiptItem[];
};

export const pricesApi = {
    /** Summaries, newest-bought first. `q` matches every word. */
    book: (query?: string) =>
        request<{ items: ProductPrices[]; total: number; limit: number; offset: number }>(
            `/api/prices${query ? `?q=${encodeURIComponent(query)}` : ""}`
        ),
    /** One product with every purchase behind it. The key is normalised prose,
     *  spaces and all, so it travels as a query parameter. */
    product: (key: string) =>
        request<ProductPrices>(`/api/prices/product?key=${encodeURIComponent(key)}`),
    /** Whether a model is configured, and who else sees a search term.
     *  `reference` is the external price source, or "" when there is none. */
    chatStatus: () =>
        request<{ available: boolean; model: string; reference: string }>(
            `/api/prices/chat/status`
        ),
};

/**
 * What a ticket's shorthand is called out in the world.
 *
 * `GV DETE 7L` is what the printer had room for; `detergente` is what a price
 * survey files it under. Nothing derives one from the other, so the association
 * is stored per product — `source` says whether a model proposed it (`auto`) or
 * a person decided it (`user`), and a person's answer is never overwritten.
 */
export type ReferenceTerm = {
    product_key: string;
    term: string;
    source: "auto" | "user";
};

export const termsApi = {
    /** Every association this user has, as a list to index by `product_key`. */
    list: () => request<{ items: ReferenceTerm[]; total: number }>(`/api/prices/terms`),
    set: (productKey: string, term: string) =>
        request<ReferenceTerm>(`/api/prices/terms`, {
            method: "PUT",
            body: JSON.stringify({ product_key: productKey, term }),
        }),
};

export const receiptsApi = {
    list: () => request<{ items: Receipt[]; total: number }>(`/api/receipts`),
    /** `receipt` is `null` for almost every movement, which is not an error. */
    forTransaction: (transactionId: string) =>
        request<{ receipt: Receipt | null }>(`/api/receipts/for-transaction/${transactionId}`),
    attach: (receiptId: string, transactionId: string | null) =>
        request<Receipt>(`/api/receipts/${receiptId}`, {
            method: "PATCH",
            body: JSON.stringify({ transaction_id: transactionId }),
        }),
    remove: (receiptId: string) =>
        request<{ receipt_id: string; deleted: boolean }>(`/api/receipts/${receiptId}`, {
            method: "DELETE",
        }),
};

/** What the compared figure means, in words the user reads. */
export function basisLabel(product: ProductPrices): string {
    if (product.basis !== "unit") return "por pieza";
    const unit = product.points?.[0]?.size_unit ?? product.cheapest?.size_unit;
    return unit === "kg" ? "por kilo" : "por litro";
}
