"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Trash2 } from "lucide-react";
import { cn } from "@/lib/cn";
import { dayLabel, mxn2 } from "@/lib/format";
import { fromIso } from "@/lib/porMes";
import type { Receipt, ReceiptItem, ReferenceTerm } from "@/lib/prices";
import { Button } from "@/components/ui";
import { track } from "@/lib/telemetry";
import { fold } from "./basket";

/**
 * Your purchases, grouped the way they were made: one ticket at a time.
 *
 * A basket is a decision made once, and the lines in it explain each other —
 * the $936 at Bodega Aurrerá is 16 choices, and the one that moved the total
 * is visible only next to the other 15. So the ticket is the unit: collapsed
 * by default, opened one at a time when a trip is worth looking at.
 *
 * Several can be open at once, deliberately. The comparison people actually
 * make here is between two trips to the same store, and an accordion that
 * closes one when you open the next makes exactly that comparison impossible.
 *
 * The rows are the category accordion's rows — chevron, mark, name, meta,
 * amount — so Precios reads as the same list the other faces draw, one level
 * further down. The data is the face's, not this list's: the basket bar above
 * and the product book below read the same tickets, so the tickets are handed
 * in rather than fetched here.
 */
export function ReceiptGroups({
    receipts,
    terms,
    onAssociate,
    onDelete,
    onVerCargo,
    focus,
}: {
    receipts: Receipt[];
    terms: Record<string, ReferenceTerm>;
    onAssociate: (productKey: string, term: string) => Promise<void>;
    onDelete: (id: string) => Promise<void>;
    /** The charge this ticket was matched to, in the movimientos modal. */
    onVerCargo: (receipt: Receipt) => void;
    /** A ticket another card asked to see: opened and scrolled to. `gen`
     *  bumps so the same ticket can be asked for twice. */
    focus: { id: string; gen: number } | null;
}) {
    const [open, setOpen] = useState<Set<string>>(new Set());

    useEffect(() => {
        if (!focus) return;
        setOpen((current) => new Set(current).add(focus.id));
        // After the row has rendered open, so the scroll lands on its top.
        const t = window.setTimeout(() => {
            document
                .getElementById(ticketDomId(focus.id))
                ?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 60);
        return () => window.clearTimeout(t);
    }, [focus]);

    const shown = useMemo(() => [...receipts].sort(byNewest), [receipts]);

    function toggle(id: string) {
        if (!open.has(id)) track("precios.ticket_open", { open_before: open.size });
        setOpen((current) => {
            const next = new Set(current);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }

    async function remove(id: string) {
        await onDelete(id);
        setOpen((current) => {
            const next = new Set(current);
            next.delete(id);
            return next;
        });
    }

    // What the baskets on screen add up to. The lines' own sum, not the printed
    // total: a ticket whose OCR dropped a line would otherwise inflate a figure
    // the rows underneath cannot account for.
    const basket = shown.reduce((sum, r) => sum + r.items_total, 0);

    return (
        <section className="min-w-0 overflow-hidden rounded-card border border-mist bg-paper shadow-card">
            <header className="flex items-center justify-between gap-3 border-b border-mist px-5 py-4 sm:px-6">
                <h2 className="flex items-baseline gap-2 text-title-sm font-normal text-ink">
                    Tickets
                    <span className="tabular font-sans text-body-sm text-graphite">
                        {shown.length.toLocaleString("es-MX")}
                    </span>
                </h2>
                <div className="flex shrink-0 items-center gap-4">
                    {open.size > 0 && (
                        <button
                            type="button"
                            onClick={() => setOpen(new Set())}
                            className="text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                        >
                            Colapsar todo
                        </button>
                    )}
                    <span className="tabular text-body-sm text-graphite">
                        {mxn2(basket)} en canasta
                    </span>
                </div>
            </header>

            {shown.length === 0 ? (
                <p className="px-5 py-6 text-body text-graphite sm:px-6">
                    Ningún ticket coincide. Busca por tienda o por algo que hayas comprado.
                </p>
            ) : (
                <ul className="divide-y divide-mist">
                    {shown.map((receipt) => (
                        <li
                            key={receipt.id}
                            id={ticketDomId(receipt.id)}
                            className={cn(open.has(receipt.id) && "bg-fog/60")}
                        >
                            <ReceiptGroup
                                receipt={receipt}
                                open={open.has(receipt.id)}
                                onToggle={() => toggle(receipt.id)}
                                onDelete={() => remove(receipt.id)}
                                terms={terms}
                                onAssociate={onAssociate}
                                onVerCargo={() => onVerCargo(receipt)}
                            />
                        </li>
                    ))}
                </ul>
            )}
        </section>
    );
}

export function ticketDomId(id: string): string {
    return `ticket-${id}`;
}

function ReceiptGroup({
    receipt,
    open,
    onToggle,
    onDelete,
    terms,
    onAssociate,
    onVerCargo,
}: {
    receipt: Receipt;
    open: boolean;
    onToggle: () => void;
    onDelete: () => Promise<void>;
    terms: Record<string, ReferenceTerm>;
    onAssociate: (productKey: string, term: string) => Promise<void>;
    onVerCargo: () => void;
}) {
    const count = receipt.items.length;
    const store = receipt.store ?? "tienda ilegible";
    return (
        <>
            {/* A row, not one big button: the delete control lives in it, and a
                button inside a button is neither valid nor operable. */}
            <div
                className={cn(
                    "flex min-h-14 items-center gap-3 px-5 py-2.5 transition-colors duration-100 sm:px-6",
                    open ? "border-b border-muted/70 bg-fog" : "hover:bg-fog/50"
                )}
            >
                <button
                    type="button"
                    aria-expanded={open}
                    onClick={onToggle}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                >
                    <ChevronRight
                        size={16}
                        aria-hidden
                        className={cn(
                            "shrink-0 transition-transform duration-150",
                            open ? "rotate-90 text-graphite" : "text-ash"
                        )}
                    />
                    <StoreMark store={store} />
                    <span className="min-w-0 flex-1">
                        <span className="block truncate text-body font-medium text-ink">
                            {store}
                        </span>
                        <span className="tabular block text-label text-ash">
                            {dateLabel(receipt)} · {count}{" "}
                            {count === 1 ? "producto" : "productos"}
                        </span>
                    </span>
                    {/* Whether this basket found its charge. Stated, not
                        offered: linking one is a choice about which movement it
                        belongs to, and there is nothing on this row that could
                        answer that question. */}
                    <span
                        className={cn(
                            "hidden shrink-0 rounded-tag px-2.5 py-0.5 text-label md:inline",
                            receipt.transaction_id !== null
                                ? "bg-fog text-graphite"
                                : "border border-mist text-ash"
                        )}
                    >
                        {receipt.transaction_id !== null ? "Ligado a un cargo" : "Sin cargo ligado"}
                    </span>
                    <span className="tabular w-24 shrink-0 text-right text-body font-medium text-ink sm:w-28">
                        {receipt.total !== null ? mxn2(receipt.total) : "—"}
                    </span>
                </button>
                <DeleteReceipt receipt={receipt} onDelete={onDelete} />
            </div>

            {open && (
                <>
                    <ReceiptLines
                        receipt={receipt}
                        terms={terms}
                        onAssociate={onAssociate}
                    />
                    {receipt.transaction_id !== null && (
                        <div className="flex justify-end border-t border-muted/70 px-5 py-2 sm:px-6">
                            <button
                                type="button"
                                onClick={onVerCargo}
                                className="rounded-control px-2 py-1 text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                            >
                                Ver el cargo
                            </button>
                        </div>
                    )}
                </>
            )}
        </>
    );
}

/** The store's initial, so a column of totals keeps a left edge. */
function StoreMark({ store }: { store: string }) {
    const letter = (store.match(/\p{L}|\p{N}/u)?.[0] ?? "?").toUpperCase();
    return (
        <span
            aria-hidden
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fog text-label font-medium text-graphite"
        >
            {letter}
        </span>
    );
}

/**
 * Two-tap delete in place of a modal.
 *
 * The row *is* the confirmation prompt — the store, the date and the total are
 * right there — and there is no dialog to mis-tap on a phone. Same shape the
 * document archive uses, on purpose: deleting a thing you own should feel the
 * same everywhere in this app.
 */
function DeleteReceipt({
    receipt,
    onDelete,
}: {
    receipt: Receipt;
    onDelete: () => Promise<void>;
}) {
    const [confirming, setConfirming] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [failed, setFailed] = useState<string | null>(null);

    if (failed) {
        return <span className="shrink-0 text-label text-negative">{failed}</span>;
    }

    if (!confirming) {
        return (
            <Button
                size="sm"
                variant="ghost"
                icon={<Trash2 size={14} />}
                aria-label={`Eliminar el ticket de ${receipt.store ?? "tienda ilegible"}`}
                onClick={() => setConfirming(true)}
            />
        );
    }

    return (
        <span className="flex shrink-0 items-center gap-1">
            <Button
                size="sm"
                variant="danger"
                loading={deleting}
                onClick={async () => {
                    setDeleting(true);
                    try {
                        await onDelete();
                    } catch (e) {
                        // The row survives a failed delete, saying why. A row
                        // that vanishes on an error is a ticket the user thinks
                        // is gone and is not.
                        setFailed((e as Error).message);
                        setDeleting(false);
                        setConfirming(false);
                    }
                }}
            >
                ¿Borrar el ticket?
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                Cancelar
            </Button>
        </span>
    );
}

/** One basket, line by line, and what the lines do and do not account for. */
function ReceiptLines({
    receipt,
    terms,
    onAssociate,
}: {
    receipt: Receipt;
    terms: Record<string, ReferenceTerm>;
    onAssociate: (productKey: string, term: string) => Promise<void>;
}) {
    const gap = receipt.total === null ? null : receipt.total - receipt.items_total;
    // A centavo of rounding is not a missing line. Anything above it is, and
    // OCR drops lines — a silently short basket is worse than a visible gap.
    const short = gap !== null && Math.abs(gap) > 0.5;

    return (
        <div className="px-5 pb-4 pt-3 sm:pl-16 sm:pr-6">
            {/* The reading's own account of itself, above the lines it is about:
                how much of the basket was legible, and — when OCR dropped a
                line — how much of the printed total is unaccounted for. Said
                first because it is the caveat every figure below inherits. */}
            <p className="tabular border-b border-muted/70 pb-2 text-label text-graphite">
                {receipt.items.length}{" "}
                {receipt.items.length === 1 ? "producto leído" : "productos leídos"}
                {short ? (
                    <>
                        {" · "}
                        <span className="text-negative">
                            faltan {mxn2(Math.abs(gap as number))} del total impreso
                        </span>
                    </>
                ) : (
                    receipt.total !== null && <> · cuadran con el total impreso</>
                )}
            </p>

            {receipt.items.length === 0 ? (
                <p className="pt-3 text-body-sm text-graphite">
                    Este ticket no dejó ninguna línea legible.
                </p>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-body-sm">
                        <tbody>
                            {[...receipt.items]
                                .sort((a, b) => a.line_no - b.line_no)
                                .map((item) => (
                                    <Line
                                        key={item.id}
                                        item={item}
                                        term={terms[item.product_key]}
                                        onAssociate={onAssociate}
                                    />
                                ))}
                        </tbody>
                    </table>
                </div>
            )}

            <p className="mt-2 border-t border-mist pt-2 text-label text-ash">
                Las líneas suman{" "}
                <span className="tabular text-graphite">{mxn2(receipt.items_total)}</span>
                {receipt.total !== null && (
                    <>
                        {" · "}el ticket dice{" "}
                        <span className="tabular text-graphite">{mxn2(receipt.total)}</span>
                    </>
                )}
            </p>
        </div>
    );
}

function Line({
    item,
    term,
    onAssociate,
}: {
    item: ReceiptItem;
    term?: ReferenceTerm;
    onAssociate: (productKey: string, term: string) => Promise<void>;
}) {
    // The OCR line is the evidence for everything to the right. When the
    // reading of it is the same text there is nothing to show twice.
    const sameAsRaw = fold(item.raw_text) === fold(item.description);
    return (
        <tr className="border-b border-mist last:border-0">
            <td className="max-w-0 py-2 pr-4">
                <span className="block truncate text-ink">{item.description}</span>
                {!sameAsRaw && (
                    <span className="block truncate text-label text-ash" title={item.raw_text}>
                        {item.raw_text}
                    </span>
                )}
            </td>
            <td className="w-44 py-2 pr-4 align-top">
                <TermTag term={term} onSave={(value) => onAssociate(item.product_key, value)} />
            </td>
            <td className="tabular w-32 py-2 pr-4 text-right align-top text-graphite">
                {item.unit_price !== null ? mxn2(item.unit_price) : "—"}
                {item.quantity !== null && (
                    <span className="ml-1 text-ash">× {trimZeros(item.quantity)}</span>
                )}
                {item.size !== null && item.size_unit && (
                    <span className="block text-label text-ash">
                        {trimZeros(item.size)} {item.size_unit}
                    </span>
                )}
            </td>
            <td className="tabular w-24 py-2 text-right align-top text-ink">
                {mxn2(item.amount)}
            </td>
        </tr>
    );
}

/**
 * What this line is called outside your kitchen.
 *
 * A ticket prints `GV DETE 7L`; a price survey files it under `detergente`.
 * Nothing derives one from the other, so it is shown here as what it is — an
 * association, editable, with the model's proposal marked as a proposal. That
 * mark matters: "~" invites a correction where a bare word would be read as a
 * fact the app already knows.
 */
export function TermTag({
    term,
    onSave,
}: {
    term?: ReferenceTerm;
    onSave: (value: string) => Promise<void>;
}) {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState(term?.term ?? "");
    const [saving, setSaving] = useState(false);
    if (editing) {
        return (
            <form
                className="mt-0.5 flex items-center gap-1.5"
                onSubmit={async (e) => {
                    e.preventDefault();
                    if (!draft.trim() || saving) return;
                    setSaving(true);
                    try {
                        await onSave(draft);
                        setEditing(false);
                    } finally {
                        setSaving(false);
                    }
                }}
            >
                <span className="text-label text-ash">busca como</span>
                <input
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={() => !saving && setEditing(false)}
                    placeholder="detergente"
                    aria-label="Término de búsqueda para este producto"
                    className={cn(
                        "h-6 w-36 rounded-input border border-mist bg-paper px-2",
                        "text-label text-ink outline-none placeholder:text-ash focus:border-ink"
                    )}
                />
            </form>
        );
    }
    return (
        <button
            type="button"
            onClick={() => {
                setDraft(term?.term ?? "");
                setEditing(true);
            }}
            title={
                term?.source === "auto"
                    ? "Propuesto por la lectura — corrígelo si no es eso"
                    : "Cómo se busca este producto fuera de tu cocina"
            }
            className={cn(
                "inline-flex max-w-full items-center gap-1 truncate rounded-tag px-2 py-0.5 text-label transition-colors duration-100",
                term
                    ? term.source === "auto"
                        ? // A proposal wears the accent as a dashed edge: the
                          // dashes are what invite the correction that a solid
                          // chip would read as already settled.
                          "border border-dashed border-signal text-ink hover:bg-wash/30"
                        : "bg-fog text-graphite hover:text-ink"
                    : "border border-mist text-ash hover:text-graphite"
            )}
        >
            {term ? `${term.source === "auto" ? "~ " : ""}${term.term}` : "sin asociar"}
        </button>
    );
}

/** "25 ago · 19:42", the same shape every other row in the app uses for a
 *  date, plus the clock when the ticket printed one. A ticket with no
 *  legible date falls back to the photo's, marked "≈". */
export function dateLabel(receipt: {
    purchased_at: string | null;
    purchased_time?: string | null;
    captured_at: string | null;
}): string {
    if (receipt.purchased_at) {
        const day = dayLabel(fromIso(receipt.purchased_at));
        return receipt.purchased_time ? `${day} · ${receipt.purchased_time}` : day;
    }
    if (!receipt.captured_at) return "fecha ilegible";
    const date = new Date(receipt.captured_at);
    return Number.isNaN(date.getTime()) ? receipt.captured_at : `≈ ${dayLabel(date)}`;
}

/** Newest purchase first; a ticket whose date OCR could not read goes last
 *  rather than to 1970, which would bury it under every real one. */
function byNewest(a: Receipt, b: Receipt): number {
    const left = a.purchased_at ?? a.captured_at;
    const right = b.purchased_at ?? b.captured_at;
    if (!left) return 1;
    if (!right) return -1;
    return right.localeCompare(left);
}

/** "1.00" -> "1", "0.750" -> "0.75". A trailing zero is noise in a quantity. */
function trimZeros(value: number): string {
    return String(Number(value.toFixed(3)));
}
