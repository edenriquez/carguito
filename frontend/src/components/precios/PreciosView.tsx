"use client";

import { useMemo, useState } from "react";
import { Camera } from "lucide-react";
import { BackendNotice, EmptyState, SearchInput, Skeleton } from "@/components/ui";
import { useAppData } from "@/components/AppChrome";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import { CompositionBar } from "@/components/movimientos/CompositionBar";
import { useMovimientosSearch } from "@/components/movimientos/MovimientosSearchProvider";
import { mxn2 } from "@/lib/format";
import { EMPTY_QUERY } from "@/lib/movimientosQuery";
import { monthBounds } from "@/lib/porMes";
import type { Receipt } from "@/lib/prices";
import { composeBasket } from "./basket";
import { ProductosList } from "./ProductosList";
import { ReceiptGroups } from "./ReceiptGroups";
import { TicketQueue, TicketUploadButton, useTicketUpload } from "./TicketUpload";
import { useReceipts } from "./useReceipts";

/**
 * Precios: your tickets, one basket at a time — the fourth face of Movimientos.
 *
 * A statement can only ever say `BODEGA AURRERA · $936.88`. This face is the
 * other half of that charge — the basket behind it — and the only question it
 * exists to answer is the one a statement structurally cannot: *what did I
 * actually buy, and at what price?* Same money the other faces read, one
 * level further down: categoría → cargo → línea de canasta.
 *
 * Three beats, the same three the other faces draw: the whole as one bar
 * (the baskets by product), the list the bar is made of (tickets, openable to
 * the line), and the reading the tickets exist for (the price book, one row
 * per product).
 *
 * Every figure here is a price the user paid, read off a ticket they
 * photographed. Nothing is fetched from a store, nothing is estimated.
 *
 * Tickets come in two ways and both keep the photo where it was taken: the
 * phone app reads it with the native recognizer, and this page reads it in a
 * worker in the browser (`lib/receipts.ts`). Either way only the text travels.
 *
 * The period does **not** filter anything here, and the eyebrow says so. A
 * price history is about the same product over time, and a window that hid
 * last quarter's cheaper trip would remove exactly the comparison this face
 * is for.
 */
export function PreciosView({
}: {
} = {}) {
    const { dataVersion, refresh } = useAppData();
    const { selectCustom } = useTimeWindow();
    const { openModal } = useMovimientosSearch();
    const { receipts, error, terms, associate, remove } = useReceipts(dataVersion);
    const [query, setQuery] = useState("");
    const [activeSlice, setActiveSlice] = useState<string | null>(null);
    const [focus, setFocus] = useState<{ id: string; gen: number } | null>(null);
    // A ticket read here lands in the same lists the phone's do, and may have
    // attached itself to a movement, so the whole app re-reads.
    const upload = useTicketUpload(refresh);

    const basket = useMemo(
        () => (receipts ? composeBasket(receipts, terms) : null),
        [receipts, terms]
    );

    /** The charge a ticket was matched to, in the modal: the store as the
     *  needle, the window on the month it was bought. */
    function verCargo(receipt: Receipt) {
        if (receipt.purchased_at) {
            const range = monthBounds(receipt.purchased_at.slice(0, 7));
            selectCustom(range.start, range.end, "precios");
        }
        openModal("precios", { ...EMPTY_QUERY, needle: receipt.store ?? "" });
    }

    if (error) {
        return (
            <div className="space-y-4">
                <BackendNotice what="tus tickets" detail={error} />
            </div>
        );
    }

    if (receipts === null || basket === null) {
        return <PreciosSkeleton />;
    }

    if (receipts.length === 0) {
        return (
            <div className="space-y-4">
                <EmptyState
                    icon={Camera}
                    title="Todavía no hay tickets"
                    action={
                        <TicketUploadButton
                            variant="primary"
                            onPick={upload.pick}
                            busy={upload.busy}
                        />
                    }
                >
                    Sube la foto de un ticket del súper. Se lee aquí, en tu navegador, y
                    solo viaja el texto; verás el precio de cada producto.
                </EmptyState>
                <TicketQueue
                    items={upload.queue}
                    onRetry={upload.retry}
                    onDismiss={upload.dismiss}
                    className="mx-auto max-w-xl"
                />
                {upload.input}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <section className="card space-y-5">
                <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
                    <div className="min-w-0">
                        <h2 className="text-title-sm font-normal text-ink">Precios</h2>
                        <p className="mt-1 text-body-sm text-graphite">
                            {receipts.length} ticket{receipts.length === 1 ? "" : "s"} ·{" "}
                            {basket.lines} producto{basket.lines === 1 ? "" : "s"} ·{" "}
                            <span className="tabular text-ink">{mxn2(basket.total)}</span> en
                            canasta
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <SearchInput
                            onSearch={setQuery}
                            placeholder="Buscar tienda o producto"
                            aria-label="Buscar tienda o producto"
                        />
                        <TicketUploadButton onPick={upload.pick} busy={upload.busy} />
                    </div>
                </div>
                <TicketQueue
                    items={upload.queue}
                    onRetry={upload.retry}
                    onDismiss={upload.dismiss}
                />
                <CompositionBar
                    slices={basket.slices}
                    activeKey={activeSlice}
                    onPick={(key) => setActiveSlice((cur) => (cur === key ? null : key))}
                    countLabel={() =>
                        `${basket.lines} línea${basket.lines === 1 ? "" : "s"} leída${basket.lines === 1 ? "" : "s"}`
                    }
                    label="Composición de la canasta por producto"
                />
                <p className="text-label text-ash">Base: líneas leídas de tus tickets.</p>
            </section>

            <ReceiptGroups
                receipts={receipts}
                terms={terms}
                query={query}
                onAssociate={associate}
                onDelete={remove}
                onVerCargo={verCargo}
                focus={focus}
            />

            <ProductosList
                query={query}
                terms={terms}
                dataVersion={dataVersion}
                onVerTicket={(id) => setFocus((cur) => ({ id, gen: (cur?.gen ?? 0) + 1 }))}
            />

            {upload.input}
        </div>
    );
}

/** The face's geometry before its tickets: the reading card (title, count
 *  line, search and upload, the basket bar), the ticket list and the price
 *  book under it. */
function PreciosSkeleton() {
    return (
        <div className="space-y-5" aria-busy>
            <section className="card space-y-5">
                <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
                    <div className="space-y-2">
                        <Skeleton className="h-6 w-24" />
                        <Skeleton className="h-4 w-64 max-w-full" />
                    </div>
                    <div className="flex items-center gap-2">
                        <Skeleton className="h-9 w-56 rounded-input" />
                        <Skeleton className="h-8 w-28 rounded-control" />
                    </div>
                </div>
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-3 w-56" />
            </section>
            <section className="rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="my-3 h-11" />
                ))}
            </section>
            <section className="rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                <Skeleton className="mb-3 h-5 w-40" />
                {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="my-3 h-11" />
                ))}
            </section>
        </div>
    );
}
