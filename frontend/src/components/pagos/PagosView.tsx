"use client";

import { useMemo } from "react";
import { BellOff, CreditCard } from "lucide-react";
import { cn } from "@/lib/cn";
import { useAppData } from "@/components/AppChrome";
import { BackendNotice, EmptyState, Skeleton } from "@/components/ui";
import { useStatements } from "@/lib/banks";
import { dayLabel, mxn2 } from "@/lib/format";
import { fromIso } from "@/lib/porMes";
import { useRecurringSeries } from "@/components/recurrentes/useRecurringSeries";
import { cardStateFrom, latestStatementEnd, type CardState } from "./cardPayment";
import { isScheduledPayment } from "./dueMonth";
import { PagosCalendar } from "./PagosCalendar";

/**
 * Pagos: what has to be paid, and when.
 *
 * The card payment first. It is the one payment on the page that is not a
 * projection — the statement prints its amount and its due date — and, for
 * a card holder, the one that costs the most to miss. Then the month, and
 * beside it the day's charges and everything after them. Confirming or
 * editing a series stays in Recurrentes and Plan; this is the glance.
 *
 * The last line says where the reading stops: the newest statement on
 * record. A calendar projected from a ledger that ends in August should say
 * so in September.
 */
export function PagosView() {
    const { dataVersion } = useAppData();
    const { dated, loading, error } = useRecurringSeries(dataVersion);
    const statements = useStatements(dataVersion);
    const card = cardStateFrom(statements);
    const ledgerEnd = latestStatementEnd(statements);
    // Store visits that merely repeat (OXXO, Walmart, Bodega) are a habit:
    // the amount swings. The calendar keeps a stable charge, and a bill whose
    // cadence is the commitment — bimonthly, semiannual — even when it moves.
    const items = useMemo(() => dated.filter(isScheduledPayment), [dated]);

    const empty =
        !loading && !error && items.length === 0 && card.kind !== "read";

    return (
        <div className="pagos-stack space-y-5">
            {error && <BackendNotice what="tus pagos" detail={error} />}

            <CardRow card={card} />

            {loading ? (
                <PagosSkeleton />
            ) : empty ? (
                <EmptyState icon={BellOff} title="Sin pagos que anticipar">
                    El calendario se llena con cargos de monto fijo, y con los bimestrales
                    y semestrales. Una visita a la tienda, aunque se repita, no es un pago.
                </EmptyState>
            ) : (
                <section className="card space-y-5">
                    <PagosCalendar
                        items={items}
                        card={card.kind === "read" ? card.payment : null}
                    />
                    <p className="text-label text-ash">
                        Proyectado desde tus cargos fijos, bimestrales y semestrales.
                        {ledgerEnd && <> Último estado de cuenta: {dayLabel(fromIso(ledgerEnd))}.</>}
                    </p>
                </section>
            )}
        </div>
    );
}

/**
 * The card's row. One shape, three things it can say: the payment and its
 * date; that a card statement is here but its figures were not read; or that
 * no statement has been labelled as a card yet. The dash on the right is only
 * ever "not read", never "nothing due".
 */
function CardRow({ card }: { card: CardState }) {
    const title =
        card.kind === "none"
            ? "Tarjeta de crédito"
            : `${card.bank} crédito · pago para no generar intereses`;
    const meta =
        card.kind === "read"
            ? [
                  card.due ? `fecha límite ${dayLabel(card.due)}` : "sin fecha límite legible",
                  card.minimum !== null ? `pago mínimo ${mxn2(card.minimum)}` : null,
              ]
                  .filter(Boolean)
                  .join(" · ")
            : card.kind === "pending"
              ? "Monto y fecha límite pendientes de leer del estado de cuenta"
              : "Marca un estado de cuenta como crédito en Documentos para verlo aquí";

    return (
        <div className="flex items-center justify-between gap-4 rounded-card bg-fog px-4 py-3.5">
            <span className="flex min-w-0 items-center gap-3">
                <CreditCard size={16} aria-hidden className="shrink-0 text-graphite" />
                <span className="min-w-0">
                    <span className="block truncate text-body font-medium text-ink">{title}</span>
                    <span className="block truncate text-label text-ash">{meta}</span>
                </span>
            </span>
            <span
                className={cn(
                    "tabular shrink-0 text-body",
                    card.kind === "read" ? "text-ink" : "text-ash"
                )}
            >
                {card.kind === "read" ? mxn2(card.amount) : "—"}
            </span>
        </div>
    );
}

/** The wait, at the shape of the arrival: the card row is already drawn, so
 *  this is only the calendar card — grid on the left, rows on the right. */
function PagosSkeleton() {
    return (
        <section className="card space-y-5">
            <div className="grid gap-8 md:grid-cols-[minmax(0,56fr)_minmax(0,44fr)]">
                <Skeleton className="h-64" />
                <div className="space-y-3">
                    <Skeleton className="h-5 w-40" />
                    {[0, 1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-10" />
                    ))}
                </div>
            </div>
            <Skeleton className="h-4 w-72 max-w-full" />
        </section>
    );
}
