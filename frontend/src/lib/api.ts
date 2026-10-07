/**
 * Thin client for the Tomin backend API.
 *
 * The backend serves aggregates from the DuckDB cube; the web app is purely a
 * display layer. When Supabase auth is enabled, attach the access token here.
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Transaction = {
    id: string;
    statement_id?: string | null;
    date: string;
    description: string;
    /** Untouched bank text, before normalisation. Useful as a title attribute. */
    raw_description?: string | null;
    amount: number;
    currency: string;
    type: "income" | "expense";
    status: "completed" | "pending";
    category_id: string | null;
    /** "auto" when the classifier assigned it, "manual" once a human did. */
    category_source?: string | null;
    merchant_id?: string | null;
    /** Free text the user wrote. Never derived from the statement. */
    notes?: string | null;
    /** Kept in the ledger, left out of every metric. For the transfer between
     *  your own accounts that would otherwise show up as both income and spend. */
    excluded_from_stats?: boolean;
    /** Derived at ingest: self-transfer wording ("pago tarjeta", "cajita",
     *  "su abono"). The Flujo aggregate honors it like the cube does. */
    is_transfer?: boolean;
    /** "auto" while the machine decided; "user" once a human answered.
     *  Automatic passes never overturn a "user" row. */
    transfer_source?: string;
    is_cash_withdrawal?: boolean;
    /** Ids only — resolve names against the tag list (see `lib/tags.ts`). */
    tag_ids?: string[];
};

/** The editable surface of a transaction. Everything else on it is bank data
 *  and stays read-only: a description the user can rewrite is a label, the
 *  original text survives in `raw_description`. */
export type TransactionPatch = {
    category_id?: string | null;
    description?: string;
    notes?: string | null;
    excluded_from_stats?: boolean;
    /** The user settling "is this my own money moving?" — in either direction.
     *  Locks the row against every automatic re-flagging pass. */
    is_transfer?: boolean;
};

export type TransactionPage = {
    items: Transaction[];
    total: number;
    limit: number;
    offset: number;
};




/** The user-declarable account kinds. Mirrors the backend `AccountKind` enum. */
export const ACCOUNT_KINDS = ["debit", "credit", "savings", "investment", "payroll"] as const;
export type AccountKind = (typeof ACCOUNT_KINDS)[number];

/** Display names for the account kinds — one copy, both pickers. */
export const KIND_LABELS: Record<AccountKind, string> = {
    debit: "Débito",
    credit: "Crédito",
    savings: "Ahorro",
    investment: "Inversión",
    payroll: "Nómina",
};

/** Display names for statement sources — one copy, one wording. */
export const SOURCE_LABELS: Record<string, string> = {
    bank_pdf: "Estado de cuenta",
    sat_xml: "Factura SAT",
};

export type Statement = {
    id: string;
    source_type: string;
    bank: string | null;
    period_start: string | null;
    period_end: string | null;
    status: string;
    /** User-declared; null until they label the document. */
    account_kind: AccountKind | null;
    /**
     * What a card statement asks to be paid, read off its text at ingest.
     * Null on every debit statement, on a card statement whose figures the
     * reader could not find, and on rows ingested before the fields existed.
     * Optional because older backends do not send them at all.
     */
    credit_no_interest_payment?: number | null;
    credit_minimum_payment?: number | null;
    credit_due_date?: string | null;
    uploaded_at: string | null;
    /**
     * Where the reading happened: "web" (the file was uploaded here and
     * discarded) or "device" (the phone extracted the text and only the text
     * travelled — the custody promise). Optional and widened to `string`
     * deliberately: every statement ingested before the column existed answers
     * without it, so the UI must treat "absent" as "unknown", never as "web".
     */
    source?: "web" | "device" | string;
};

/** A row of the global category taxonomy. */
export type Category = {
    id: string;
    name: string;
    /** Hex, from the seed data. May be null; charts fall back to Ash. */
    color: string | null;
    icon: string | null;
    /** Null = root. A transaction still points at one id — usually the leaf. */
    parent_id?: string | null;
};

/** The user-editable surface of a statement. Omitted key = leave alone. */
export type StatementPatch = {
    account_kind?: AccountKind | null;
    bank?: string | null;
};

/** What POST /api/statements answers: the parse outcome plus the statement
 *  itself, so the onboarding review can show what the OCR understood. */
export type UploadResult = {
    statement_id: string;
    template: string;
    transactions_created: number;
    /** Movements the file held that an earlier upload of the same account
     *  already stored (a partial month re-uploaded once closed). Not stored
     *  twice; only `transactions_created` landed. */
    transactions_skipped: number;
    statement: Statement;
};

/** One detected recurring series (subscription, fixed bill). */
export type RecurringItem = {
    /** Stable grouping identity — survives a new charge, unlike last_date. */
    key: string;
    label: string;
    occurrences: number;
    frequency: "weekly" | "biweekly" | "monthly" | "bimonthly" | "semiannual" | "yearly";
    /** Median charge. */
    typical_amount: number;
    /** What the series costs per 30 days — the ranking measure. */
    monthly_equivalent: number;
    /** false = recurs on a rhythm but the amount varies (a utility bill). */
    amount_stable: boolean;
    last_date: string;
    next_expected: string;
    category_id: string | null;
    /** Every charge in the series, oldest first — the evidence the rhythm was
     *  inferred from, and what the calendar view is drawn from. */
    charges: RecurringCharge[];
};

/**
 * A charge the Movimientos chart should ring, with the sentence behind it.
 * Computed server-side against the whole ledger (see backend
 * `domain/services/attention.py`); the window only decides which charges
 * are reported.
 */
export type AttentionKind = "unusual_amount" | "possible_duplicate" | "new_merchant";

export type AttentionItem = {
    transaction_id: string;
    kind: AttentionKind;
    /** Spanish, one line, with its numbers: "3.2× lo que sueles gastar ahí (…)". */
    reason: string;
    /** unusual_amount: amount ÷ the merchant's median. Others: null. */
    ratio: number | null;
    /** The earlier leg(s) of a possible duplicate. */
    related_ids: string[];
    severity: "warn" | "info";
};

/** One occurrence of a recurring series. */
export type RecurringCharge = {
    /** ISO date, no time. */
    date: string;
    amount: number;
};



/**
 * The one place a request is made. Exported so `lib/metrics.ts` speaks to the
 * metric endpoints through the same helper instead of growing a second one
 * that drifts on headers, caching or error shape.
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
        res = await fetch(`${API_URL}${path}`, {
            ...init,
            headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
            cache: "no-store",
        });
    } catch (cause) {
        // `fetch` rejects with a bare "Failed to fetch" for every reason the
        // request never completed: nothing listening, DNS, a CORS preflight
        // that 404'd. The browser withholds which on purpose, so the one thing
        // we *can* say — the address we tried — has to come from here. Without
        // it the message is unactionable, and the most common cause is exactly
        // the one it would reveal: the app pointed at the wrong backend.
        throw new Error(
            `No se pudo contactar al backend en ${API_URL} (${path}). ` +
                `Revisa que esté corriendo y que NEXT_PUBLIC_API_URL apunte ahí.`,
            { cause }
        );
    }
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(`API ${res.status}: ${detail}`);
    }
    return res.json() as Promise<T>;
}

/**
 * An upload failure the UI can branch on. `code` is the backend's
 * machine-readable reason (today: `pdf_password_required` /
 * `pdf_password_incorrect`); `message` stays human-readable for the toast.
 */
export class UploadError extends Error {
    code?: string;
    constructor(message: string, code?: string) {
        super(message);
        this.code = code;
    }
}

/** The backend's error body, as an UploadError. Split from the Response so
 *  the XHR path below — which has text, not a Response — parses it the same
 *  way, and a `pdf_password_required` keeps its code on both routes. */
function parseUploadError(text: string): UploadError {
    try {
        const body = JSON.parse(text) as { error?: string; code?: string };
        return new UploadError(body.error ?? text, body.code);
    } catch {
        return new UploadError(text);
    }
}

export const api = {
    transactions: (query = "") => request<TransactionPage>(`/api/transactions${query}`),
    /** Charges in the window worth a second look. Same query shape as the list. */
    attention: (query = "") =>
        request<{ items: AttentionItem[] }>(`/api/transactions/attention${query}`),
    /** The ledger's first and last transaction dates; the time filter anchors
     *  its rolling presets on `last`, not on the calendar. */
    transactionSpan: (statementIds?: string[] | null) => {
        const params = new URLSearchParams();
        for (const id of statementIds ?? []) params.append("statement_id", id);
        const q = params.toString();
        return request<{ first: string | null; last: string | null }>(
            `/api/transactions/span${q ? `?${q}` : ""}`
        );
    },
    /** The global category taxonomy: names and colors for charts and pickers. */
    categories: () => request<{ items: Category[] }>(`/api/categories`),
    /** Mint a leaf under a root. The same name under the same parent
     *  returns the sibling that already exists. */
    createCategory: (body: { name: string; parent_id: string }) =>
        request<Category>(`/api/categories`, {
            method: "POST",
            body: JSON.stringify(body),
        }),
    /**
     * Apply a category to every similar machine-categorized movement.
     * `dry_run` reports the blast radius without writing; the real run also
     * teaches the label so future uploads categorize themselves.
     */
    recategorize: (body: { category_id: string; label: string; dry_run?: boolean }) =>
        request<{ matched: number; updated: number; label: string }>(
            `/api/transactions/recategorize`,
            { method: "POST", body: JSON.stringify(body) }
        ),
    /**
     * Rename every similar machine-named movement and remember the alias, so
     * ingest renames future uploads too. Hand-typed names are never touched.
     */
    realias: (body: { label: string; alias: string; dry_run?: boolean }) =>
        request<{ matched: number; updated: number; label: string }>(
            `/api/transactions/realias`,
            { method: "POST", body: JSON.stringify(body) }
        ),
    /**
     * Flag every movement whose counterparty is the user themselves, and
     * remember the name so future uploads flag themselves. `dry_run` reports
     * the blast radius without writing.
     */
    markTransfer: (body: { party: string; dry_run?: boolean }) =>
        request<{ matched: number; updated: number; party: string }>(
            `/api/transactions/mark-transfer`,
            { method: "POST", body: JSON.stringify(body) }
        ),
    /**
     * Find and flag mirrored self-transfer legs across statements (same
     * amount, opposite directions, days apart). Runs automatically at every
     * ingest; this exists to backfill history uploaded before the rule.
     */
    pairTransfers: (body: { dry_run?: boolean } = {}) =>
        request<{ pairs: number; updated: number }>(`/api/transactions/pair-transfers`, {
            method: "POST",
            body: JSON.stringify(body),
        }),
    /** Returns the updated transaction, so the caller never has to guess what
     *  the server made of the patch. */
    updateTransaction: (id: string, patch: TransactionPatch) =>
        request<Transaction>(`/api/transactions/${id}`, {
            method: "PATCH",
            body: JSON.stringify(patch),
        }),
    recurring: (query = "") =>
        request<{ items: RecurringItem[] }>(`/api/analytics/recurring${query}`),
    statements: () => request<{ items: Statement[]; total: number }>(`/api/statements`),
    /**
     * The two user-editable statement fields: what kind of account it is and
     * (for statements the parser couldn't identify) which bank. Explicit null
     * clears a field; an omitted key leaves it alone.
     */
    updateStatement: (id: string, patch: StatementPatch) =>
        request<Statement>(`/api/statements/${id}`, {
            method: "PATCH",
            body: JSON.stringify(patch),
        }),
    /**
     * Deletes a statement and every transaction derived from it, in the
     * relational store and in the analytics cube.
     */
    deleteStatement: (id: string) =>
        request<{ statement_id: string; transactions_deleted: number }>(
            `/api/statements/${id}`,
            { method: "DELETE" }
        ),
    /**
     * XHR rather than fetch, for one reason: `fetch` cannot report upload
     * progress. A statement is a few hundred KB and the parse is the slow
     * half, so the fraction this reports covers only the bytes going out —
     * which is exactly what the queue draws as a determinate bar before it
     * switches to "leyendo", where the honest answer is "no idea how long".
     */
    uploadStatement: (
        file: File,
        password?: string,
        onProgress?: (fraction: number) => void
    ): Promise<UploadResult> =>
        new Promise<UploadResult>((resolve, reject) => {
            const form = new FormData();
            form.append("file", file);
            // Only for encrypted PDFs: the backend uses it once to open the
            // file and drops it with the rest of the request.
            if (password) form.append("password", password);

            const xhr = new XMLHttpRequest();
            xhr.open("POST", `${API_URL}/api/statements`);
            if (onProgress) {
                xhr.upload.addEventListener("progress", (e) => {
                    if (e.lengthComputable) onProgress(e.loaded / e.total);
                });
                // A browser that never fires a computable event would leave
                // the bar at zero through the whole send; loadend means the
                // bytes are gone whatever it reported on the way.
                xhr.upload.addEventListener("loadend", () => onProgress(1));
            }
            xhr.addEventListener("load", () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        resolve(JSON.parse(xhr.responseText) as UploadResult);
                    } catch {
                        reject(new UploadError("El servidor respondió algo ilegible."));
                    }
                    return;
                }
                reject(parseUploadError(xhr.responseText));
            });
            xhr.addEventListener("error", () =>
                reject(new UploadError("No se pudo conectar con el servidor."))
            );
            xhr.addEventListener("abort", () =>
                reject(new UploadError("Subida cancelada.", "aborted"))
            );
            xhr.send(form);
        }),
};
