"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { mxn2 } from "@/lib/format";
import {
    basisLabel,
    pricesApi,
    type PricePoint,
    type ProductPrices,
    type ReferenceTerm,
} from "@/lib/prices";
import { Skeleton } from "@/components/ui";
import { track } from "@/lib/telemetry";
import { PriceTracker, pointDateLabel } from "./PriceTracker";

/**
 * The price book: one row per product, every purchase of it behind the row.
 *
 * This is the reading the tickets exist for. A ticket says what one trip
 * cost; the book says what *detergente* has cost you, per litre, across every
 * trip that printed it — and whether the last time was dearer than usual. The
 * backend decides the basis (per litre/kilo or per piece) and ships every
 * figure already in it; the row says which, because two prices in different
 * bases do not compare.
 *
 * Same rows as the month and category lists: chevron, name, meta, figure.
 * The name is the reference term when there is one, because that is the word
 * the user chose; what the printer had room for follows it in grey.
 *
 * An open row is the price tracker: the line of what this product cost on
 * each date (`PriceTracker`), then every purchase behind it as a list, which
 * is the same data as a table for anyone the line does not serve.
 */
export function ProductosList({
    terms,
    dataVersion,
    onVerTicket,
}: {
    terms: Record<string, ReferenceTerm>;
    dataVersion: number;
    onVerTicket: (receiptId: string) => void;
}) {
    const [book, setBook] = useState<ProductPrices[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [openKey, setOpenKey] = useState<string | null>(null);
    // Every purchase behind a product, fetched when its row opens and kept:
    // reopening is not a new question.
    const [detail, setDetail] = useState<Record<string, PricePoint[]>>({});

    useEffect(() => {
        let stale = false;
        pricesApi
            .book()
            .then((res) => {
                if (stale) return;
                setBook(res.items);
                setError(null);
            })
            .catch((e) => !stale && setError((e as Error).message));
        return () => {
            stale = true;
        };
    }, [dataVersion]);

    useEffect(() => {
        if (!openKey || detail[openKey]) return;
        let stale = false;
        pricesApi
            .product(openKey)
            .then((p) => {
                if (stale || !p.points) return;
                setDetail((cur) => ({ ...cur, [openKey]: p.points! }));
            })
            // The row already shows the summary; a detail that did not arrive
            // leaves the row as it was rather than putting an error under it.
            .catch(() => undefined);
        return () => {
            stale = true;
        };
    }, [openKey, detail]);

    const stores = useMemo(
        () => new Set((book ?? []).flatMap((p) => p.stores.map((s) => s.toLowerCase()))).size,
        [book]
    );

    function toggle(key: string) {
        track("precios.product_expand", { open: openKey !== key });
        setOpenKey((cur) => (cur === key ? null : key));
    }

    if (error) return null;

    return (
        <section className="min-w-0 overflow-hidden rounded-card border border-mist bg-paper shadow-card">
            <header className="flex items-center justify-between gap-3 border-b border-mist px-5 py-4 sm:px-6">
                <h2 className="flex items-baseline gap-2 text-title-sm font-normal text-ink">
                    Productos
                    {book && (
                        <span className="tabular font-sans text-body-sm text-graphite">
                            {book.length.toLocaleString("es-MX")}
                        </span>
                    )}
                </h2>
                {book && book.length > 0 && (
                    <span className="tabular shrink-0 text-body-sm text-graphite">
                        {stores} tienda{stores === 1 ? "" : "s"}
                    </span>
                )}
            </header>

            {book === null ? (
                <div className="space-y-2 px-5 py-4 sm:px-6">
                    {[0, 1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-11" />
                    ))}
                </div>
            ) : book.length === 0 ? (
                <p className="px-5 py-6 text-body text-graphite sm:px-6">
                    Ningún producto leído todavía.
                </p>
            ) : (
                <ul className="divide-y divide-mist">
                    {book.map((p) => {
                        const open = openKey === p.product_key;
                        const term = terms[p.product_key];
                        const points = detail[p.product_key];
                        return (
                            <li key={p.product_key} className={cn(open && "bg-fog/60")}>
                                <div
                                    className={cn(
                                        "flex min-h-12 items-center gap-3 px-5 py-2.5 transition-colors duration-100 sm:px-6",
                                        open ? "border-b border-muted/70 bg-fog" : "hover:bg-fog/50"
                                    )}
                                >
                                    <button
                                        type="button"
                                        aria-expanded={open}
                                        onClick={() => toggle(p.product_key)}
                                        className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                                    >
                                        <ChevronRight
                                            size={16}
                                            aria-hidden
                                            className={cn(
                                                "shrink-0 transition-transform duration-150",
                                                open ? "rotate-90 text-graphite" : "text-ash"
                                            )}
                                        />
                                        <Name product={p} term={term} />
                                        <span className="tabular shrink-0 whitespace-nowrap text-label text-ash">
                                            · {p.times_bought.toLocaleString("es-MX")}{" "}
                                            {p.times_bought === 1 ? "vez" : "veces"}
                                            {p.spread !== null && ` · ${p.spread}% de variación`}
                                        </span>
                                    </button>
                                    <div className="flex shrink-0 items-center gap-3 sm:gap-4">
                                        <span className="hidden w-20 text-right text-body-sm text-graphite sm:inline">
                                            {basisLabel(p)}
                                        </span>
                                        <span className="tabular w-24 text-right text-body font-medium text-ink sm:w-28">
                                            {figure(p)}
                                        </span>
                                    </div>
                                </div>

                                {open && (
                                    <>
                                        {points ? (
                                            <PriceTracker
                                                product={p}
                                                points={points}
                                                className="border-b border-muted/50 py-3 pl-7 pr-5 sm:pl-12 sm:pr-6"
                                            />
                                        ) : (
                                            <div className="border-b border-muted/50 py-3 pl-7 pr-5 sm:pl-12 sm:pr-6">
                                                <Skeleton className="mb-2 h-3 w-2/3" />
                                                <Skeleton className="h-[180px]" />
                                            </div>
                                        )}
                                        <Purchases
                                            product={p}
                                            points={points}
                                            onVerTicket={onVerTicket}
                                        />
                                        {p.latest && (
                                            <div className="flex justify-end border-t border-muted/70 px-5 py-2 sm:px-6">
                                                <button
                                                    type="button"
                                                    onClick={() => onVerTicket(p.latest!.receipt_id)}
                                                    className="rounded-control px-2 py-1 text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                                                >
                                                    Ver el ticket
                                                </button>
                                            </div>
                                        )}
                                    </>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </section>
    );
}

/** The user's word first, the printer's after it. A proposed term wears the
 *  same dashed edge it wears on the ticket line. */
function Name({ product, term }: { product: ProductPrices; term?: ReferenceTerm }) {
    if (!term) {
        return (
            <span className="min-w-0 truncate text-body font-medium text-ink">{product.name}</span>
        );
    }
    return (
        <>
            {term.source === "auto" ? (
                <span className="shrink-0 rounded-tag border border-dashed border-signal px-2 py-0.5 text-label text-ink">
                    ~ {term.term}
                </span>
            ) : (
                <span className="min-w-0 truncate text-body font-medium text-ink">{term.term}</span>
            )}
            <span className="hidden min-w-0 truncate text-label text-ash sm:inline">· {product.name}</span>
        </>
    );
}

/** The figure a row is compared by: the typical price once there are two or
 *  more, the one price there is until then. */
function figure(p: ProductPrices): string {
    const value = p.priced >= 2 ? p.median : p.latest?.value ?? null;
    if (value !== null && value !== undefined) return mxn2(value);
    return p.latest ? mxn2(p.latest.amount) : "—";
}

/** Every purchase, newest first: when, where, how much for how much. */
function Purchases({
    product,
    points,
    onVerTicket,
}: {
    product: ProductPrices;
    points: PricePoint[] | undefined;
    onVerTicket: (receiptId: string) => void;
}) {
    if (!points) {
        return (
            <div className="space-y-2 py-3 pl-7 pr-5 sm:pl-12 sm:pr-6">
                <Skeleton className="h-6" />
            </div>
        );
    }
    const ordered = [...points].sort((a, b) =>
        (b.purchased_at ?? "").localeCompare(a.purchased_at ?? "")
    );
    const basis = basisLabel(product);
    return (
        <div className="py-3 pl-7 pr-5 sm:pl-12 sm:pr-6">
            {ordered.map((pt, i) => (
                <button
                    key={`${pt.receipt_id}-${i}`}
                    type="button"
                    onClick={() => onVerTicket(pt.receipt_id)}
                    className="flex w-full items-center justify-between gap-3 border-t border-muted/50 py-1.5 text-left transition-colors duration-100 first:border-t-0 hover:text-ink"
                >
                    <span className="flex min-w-0 items-baseline gap-1.5">
                        <span className="truncate text-body-sm text-graphite">
                            {pointDateLabel(pt)} · {pt.store ?? "tienda ilegible"}
                        </span>
                        <span className="tabular whitespace-nowrap text-label text-ash">
                            {pt.size !== null && pt.size_unit && `· ${pt.size} ${pt.size_unit} `}
                            {pt.quantity !== null && pt.quantity !== 1 && `· × ${pt.quantity} `}
                            · {mxn2(pt.amount)}
                        </span>
                    </span>
                    <span className="tabular shrink-0 text-body-sm text-ink">
                        {pt.value !== null ? `${mxn2(pt.value)} ${basis}` : "sin precio comparable"}
                    </span>
                </button>
            ))}
        </div>
    );
}
