"use client";

import { useMemo, useState, type ReactNode } from "react";
import { List, Plus, Repeat, Trash2, X } from "lucide-react";
import type { RecurringItem } from "@/lib/api";
import { categoryName, useCategories } from "@/lib/categories";
import { cn } from "@/lib/cn";
import { HORIZONS, isRestKey, type Horizon, type RestMark } from "@/lib/fijos";
import { mxn } from "@/lib/format";
import { matchMerchant } from "@/lib/merchants";
import {
    chargedInBounds,
    seriesMatchesQuery,
} from "@/lib/recurrentesQuery";
import { categoryLens } from "@/lib/movimientosQuery";
import {
    EMPTY_QUERY,
    type MovimientosQuery,
} from "@/lib/movimientosQuery";
import { track } from "@/lib/telemetry";
import { useAppData } from "@/components/AppChrome";
import { AddFijoSheet } from "@/components/fijos/AddFijoSheet";
import { useMovimientosSearch } from "@/components/movimientos/MovimientosSearchProvider";
import { BackendNotice, Button, EmptyState, Skeleton } from "@/components/ui";
import { LoadTimelineChart } from "./LoadTimelineChart";
import { buildTimeline } from "./projection";
import { buildSeriesColors, sortByWeight } from "./seriesColors";
import { typicalDayOfMonth } from "./rhythm";
import { useRecurringSeries } from "./useRecurringSeries";

const FREQUENCY_LABELS: Record<RecurringItem["frequency"], string> = {
    weekly: "Semanal",
    biweekly: "Quincenal",
    monthly: "Mensual",
    bimonthly: "Bimestral",
    semiannual: "Semestral",
    yearly: "Anual",
};

const CHART_MONTHS = 6;

/**
 * Act on the set: one list, the charges you have said are fixed. History is
 * always 12 months; the period only marks which series landed in the window.
 * Criterios hide rows — they do not recompute the rhythm.
 *
 * There used to be a second list, "Pendientes de confirmación", holding what
 * detection suspected until it was promoted. It was a waiting room in front of
 * a move that is reversible anyway: adding is direct, and a charge that turns
 * out not to be what you thought is deleted from the row it created. What
 * detection found is now reached through "Añadir un cargo", which searches
 * the whole ledger rather than only the series with a rhythm.
 *
 * The set is the same one Plan reads (`useRecurringSeries`): detection, the
 * manuals, and the merchants taught as frequent. A pin made in either place
 * shows in both.
 */
export function RecurrentesView({
}: {
} = {}) {
    const { bounds, dataVersion } = useAppData();
    const categories = useCategories();
    const { query, openModal } = useMovimientosSearch();
    const { detected, manuals, taughtRest, fijos, loading, error } =
        useRecurringSeries(dataVersion);
    const [adding, setAdding] = useState(false);

    // A manual has no detection behind it: unpinning drops it, so its only
    // honest verb is "Eliminar".
    const manualKeys = useMemo(() => new Set(manuals.map((m) => m.key)), [manuals]);

    const pinnedSet = useMemo(
        () => new Set(fijos.state.pinnedKeys),
        [fijos.state.pinnedKeys]
    );

    // Detection, then the manuals it has not caught up with, then the
    // merchants taught as frequent. Criterios hide rows from all three.
    const visible = useMemo(() => {
        const lens = categoryLens(categories);
        const fromDetected = detected.filter((i) => seriesMatchesQuery(i, query, lens));
        const detectedKeys = new Set(detected.map((i) => i.key));
        const extra = manuals.filter(
            (m) => !detectedKeys.has(m.key) && seriesMatchesQuery(m, query, lens)
        );
        const rest = taughtRest.filter((i) => seriesMatchesQuery(i, query, lens));
        return [...fromDetected, ...extra, ...rest];
        // `categories` belongs here: the lens reads the taxonomy, and until it
        // has loaded every id looks uncategorized. Without it a category
        // criterio would keep answering from the empty map after the fetch
        // landed.
    }, [detected, manuals, taughtRest, query, categories]);

    const pinned = useMemo(
        () => visible.filter((i) => pinnedSet.has(i.key)),
        [visible, pinnedSet]
    );
    // What detection found and the user has not fixed. No longer a list of its
    // own — it was a waiting room in front of a move that is now direct — but
    // still worth a count: it says the drawing is not the whole story.
    const pending = useMemo(
        () => visible.filter((i) => !pinnedSet.has(i.key)),
        [visible, pinnedSet]
    );

    const fijosNeed = pinned.reduce((s, i) => s + i.monthly_equivalent, 0);

    /**
     * The chart is the fijos and nothing else. A series detection merely
     * suspects is not money the user has committed to, and drawing it — even
     * hatched — puts pesos nobody agreed to inside a total that is supposed to
     * be trustworthy. Confirming a charge is what draws it.
     *
     * The horizon is the one Plan uses — picking 12 meses here picks it there,
     * because it is the same question asked from two rooms.
     */
    const horizon = fijos.state.horizon;
    // Heaviest series first, so the stack darkens downward in step with the
    // ramp the colours come from.
    const fijosTimeline = useMemo(
        () => buildTimeline(sortByWeight(pinned), CHART_MONTHS, horizon),
        [pinned, horizon]
    );

    // Colour by weight along the stone ramp, built over every series in play —
    // not the filtered selection, or hiding one row would repaint the rest
    // (see `buildSeriesColors`).
    const colorOf = useMemo(
        () => buildSeriesColors([...detected, ...manuals, ...taughtRest]),
        [detected, manuals, taughtRest]
    );

    function setHorizon(h: Horizon) {
        track("plan.horizon", { horizon: h, face: "recurrentes" });
        fijos.setHorizon(h);
    }

    /** Fijar: the series counts as committed money, in Recurrentes and Plan. */
    function pin(item: RecurringItem) {
        track("movimientos.recurrente_confirm", { frequency: item.frequency });
        fijos.pin(item.key);
    }

    /**
     * Quitar: back to pending, not gone. A manual fijo has nowhere to fall
     * back to — `unpin` drops it — which is why its button says "Eliminar".
     */
    function unpin(item: RecurringItem) {
        track("movimientos.recurrente_unpin", { kind: kindOf(item) });
        fijos.unpin(item.key);
    }

    /**
     * Eliminar: forget the taught merchant entirely. Only taught things can
     * be deleted — a detected series would come straight back from the
     * backend, so it is only ever pinned or pending.
     */
    function remove(item: RecurringItem) {
        track("movimientos.recurrente_remove", { kind: kindOf(item) });
        if (isRestKey(item.key)) fijos.removeRest(item.key);
        fijos.unpin(item.key);
    }

    /**
     * Detection needs three charges with a readable rhythm; rent paid by
     * transfer, a yearly renewal, anything the bank writes differently each
     * month never reaches this list. So the list is not the limit: any charge
     * in the ledger can be named by hand, and naming it is itself the
     * confirmation — it lands in Cargos fijos and in Plan.
     */
    function addManual(manual: Parameters<typeof fijos.addManual>[0]) {
        track("plan.fijo_add_manual", { frequency: manual.frequency, face: "recurrentes" });
        fijos.addManual(manual);
    }

    function addTaught(mark: RestMark) {
        track("plan.fijo_pin", { kind: "rest", face: "recurrentes" });
        fijos.pinRest(mark);
    }

    function openCharges(item: RecurringItem) {
        const slug = matchMerchant(item.label);
        const seed: MovimientosQuery = slug
            ? { ...EMPTY_QUERY, merchantSlugs: [slug] }
            : { ...EMPTY_QUERY, needle: item.label };
        openModal("recurrente", { ...query, ...seed, categoryIds: query.categoryIds });
    }

    const emptyDetection =
        !loading &&
        detected.length === 0 &&
        manuals.length === 0 &&
        taughtRest.length === 0 &&
        !error;
    const emptyFilter = !loading && !emptyDetection && visible.length === 0;

    return (
        <div className="space-y-5">
            {error && <BackendNotice what="Cargos Recurrentes" detail={error} />}

            {emptyDetection ? (
                <>
                    <EmptyState
                        icon={Repeat}
                        title="Tomin aún no ve cobros que se repitan"
                        action={
                            <Button
                                variant="ghost"
                                size="sm"
                                icon={<Plus size={14} />}
                                onClick={() => setAdding(true)}
                            >
                                Añadir un cargo
                            </Button>
                        }
                    >
                        Hacen falta al menos tres cobros del mismo lugar con un ritmo
                        reconocible. Sube más estados de cuenta, o añade el cargo a
                        mano.
                    </EmptyState>
                </>
            ) : emptyFilter ? (
                <>
                    <EmptyState icon={Repeat} title="Ninguna serie coincide">
                        Un criterio no cambia el cálculo: solo esconde filas. Quita
                        categoría o comercio para verlas todas.
                    </EmptyState>
                </>
            ) : (
                <>
                    <section className="card space-y-5">
                        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
                            <div className="min-w-0">
                                <h2 className="text-title-sm font-normal text-ink">
                                    Cargos Recurrentes
                                </h2>
                                <p className="mt-1 text-body-sm text-graphite">
                                    {loading ? (
                                        "Cargando la carga mensual…"
                                    ) : pinned.length === 0 ? (
                                        <>
                                            Solo se dibuja lo que fijas
                                            {pending.length > 0 &&
                                                `: detección ya encontró ${pending.length} cobros que se repiten`}
                                            .
                                        </>
                                    ) : (
                                        <>
                                            Próximos {horizon} meses en cargos fijos:{" "}
                                            <span className="tabular text-ink">
                                                {mxn(fijosTimeline.totals.projected)}
                                            </span>
                                            {pending.length > 0 && (
                                                <>
                                                    {" · "}
                                                    {pending.length} cobro
                                                    {pending.length === 1 ? "" : "s"}{" "}
                                                    detectado
                                                    {pending.length === 1 ? "" : "s"}{" "}
                                                    {pending.length === 1
                                                        ? "queda"
                                                        : "quedan"}{" "}
                                                    fuera
                                                </>
                                            )}
                                        </>
                                    )}
                                </p>
                            </div>
                            <div className="flex flex-col items-end gap-2">
                                <div
                                    role="radiogroup"
                                    aria-label="Horizonte"
                                    className="inline-flex rounded-control border border-mist bg-paper p-0.5"
                                >
                                    {HORIZONS.map((h) => {
                                        const selected = horizon === h;
                                        return (
                                            <button
                                                key={h}
                                                type="button"
                                                role="radio"
                                                aria-checked={selected}
                                                onClick={() => setHorizon(h)}
                                                className={cn(
                                                    "rounded-control px-3 py-1 text-body-sm",
                                                    "transition-colors duration-100",
                                                    selected
                                                        ? "bg-fog font-medium text-ink"
                                                        : "text-graphite hover:text-ink"
                                                )}
                                            >
                                                {h} meses
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        </div>
                        {loading ? (
                            <Skeleton className="h-[280px] w-full" />
                        ) : (
                            <LoadTimelineChart
                                timeline={fijosTimeline}
                                colorFor={colorOf}
                                height={280}
                            />
                        )}
                    </section>

                    <SeriesCard
                        title="Transacciones"
                        monthly={fijosNeed}
                        loading={loading}
                        empty="Añade el primer cobro que sí o sí llega."
                        action={
                            <Button
                                variant="ghost"
                                size="sm"
                                icon={<Plus size={14} />}
                                onClick={() => setAdding(true)}
                            >
                                Añadir un cargo
                            </Button>
                        }
                        note="Añadir busca en todo el historial: detección propone las series con ritmo, y cualquier otro cobro se fija a mano. Si el cargo no era lo que creías, elimínalo aquí."
                    >
                        {pinned.map((item) => (
                            <FijoRow
                                key={item.key}
                                item={item}
                                category={categoryName(categories, item.category_id)}
                                inPeriod={chargedInBounds(item, bounds)}
                                deletable={deletable(item, manualKeys)}
                                onOpenList={() => {
                                    track("movimientos.recurrente_open_list");
                                    openCharges(item);
                                }}
                                onUnpin={() => unpin(item)}
                                onRemove={() => remove(item)}
                            />
                        ))}
                    </SeriesCard>

                </>
            )}

            <AddFijoSheet
                open={adding}
                onClose={() => setAdding(false)}
                detected={detected}
                dataVersion={dataVersion}
                onPin={(key) => fijos.pin(key)}
                onAddManual={addManual}
                onPinRest={addTaught}
            />
        </div>
    );
}

function SeriesCard({
    title,
    count,
    monthly,
    loading,
    empty,
    action,
    note,
    children,
}: {
    title: string;
    count?: number;
    monthly: number;
    loading: boolean;
    empty: string;
    /** A control at the end of the header row. */
    action?: ReactNode;
    /** One line under the rows — what to do when the list is short. */
    note?: string;
    children: ReactNode;
}) {
    return (
        <section className="min-w-0 overflow-hidden rounded-card border border-mist bg-paper shadow-card">
            <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-mist px-5 py-4 sm:px-6">
                <h2 className="flex flex-wrap items-baseline gap-2 text-title-sm font-normal text-ink">
                    {title}
                    <span className="text-mist">·</span>
                    <span className="tabular font-sans text-body-sm text-graphite">{count}</span>
                    <span className="text-mist">·</span>
                </h2>
                <div className="flex items-center gap-3">{action}</div>
            </header>
            {loading ? (
                <div className="space-y-2 px-5 py-4 sm:px-6">
                    {[0, 1, 2].map((i) => (
                        <Skeleton key={i} className="h-14" />
                    ))}
                </div>
            ) : count === 0 ? (
                <p className="px-5 py-6 text-body text-graphite sm:px-6">{empty}</p>
            ) : (
                <ul className="divide-y divide-mist px-2 py-1 sm:px-3">{children}</ul>
            )}
            {note && !loading && (
                <p className="border-t border-mist px-5 py-3 text-label text-ash sm:px-6">
                    {note}
                </p>
            )}
        </section>
    );
}

function FijoRow({
    item,
    category,
    inPeriod,
    deletable,
    onOpenList,
    onUnpin,
    onRemove,
}: {
    item: RecurringItem;
    category: string;
    inPeriod: boolean;
    /** Taught by hand, so it can be forgotten rather than just unpinned. */
    deletable: boolean;
    /** The charges behind the series, in Movimientos. Fixing a charge is now
     *  a direct move, so checking what it actually caught has to be one too —
     *  that is the half of "add it, delete it if it does not match" that the
     *  delete alone cannot do. */
    onOpenList: () => void;
    onUnpin: () => void;
    onRemove: () => void;
}) {
    return (
        <li className="flex min-h-14 items-center justify-between gap-3 rounded-control px-3 py-2.5">
            <div className="flex min-w-0 items-center gap-3.5">
                <Initial label={item.label} />
                <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="text-body font-medium text-ink">{item.label}</span>
                    <Meta>{cadence(item)}</Meta>
                    {category !== "Sin categoría" && <Meta>{category}</Meta>}
                    {inPeriod && <InPeriod />}
                </div>
            </div>
            <div className="flex shrink-0 items-center gap-3">
                <span className="tabular text-body font-medium text-ink">
                    {item.amount_stable ? "" : "~"}
                    {mxn(item.monthly_equivalent)}/mes
                </span>
                <span className="rounded-full border border-mist bg-fog px-2.5 py-0.5 text-label text-graphite">
                    {isRestKey(item.key) ? "Frecuente" : "Fijo"}
                </span>
                <RowAction
                    icon={<List size={14} aria-hidden />}
                    label={`Ver los cobros de ${item.label}`}
                    title="Ver movimientos"
                    onClick={onOpenList}
                />
                <RowAction
                    icon={<X size={14} aria-hidden />}
                    label={`Quitar ${item.label} de fijos`}
                    title="Quitar de fijos"
                    onClick={onUnpin}
                />
                {deletable && (
                    <RowAction
                        icon={<Trash2 size={14} aria-hidden />}
                        label={`Eliminar ${item.label}`}
                        title="Eliminar de Tomin"
                        danger
                        onClick={onRemove}
                    />
                )}
            </div>
        </li>
    );
}

/** The small square buttons at the end of a row. */
function RowAction({
    icon,
    label,
    title,
    danger,
    onClick,
}: {
    icon: ReactNode;
    label: string;
    title: string;
    danger?: boolean;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            aria-label={label}
            title={title}
            className={cn(
                "shrink-0 rounded-control p-1.5 text-graphite transition-colors duration-100",
                danger ? "hover:bg-negative/10 hover:text-negative" : "hover:bg-fog hover:text-ink"
            )}
        >
            {icon}
        </button>
    );
}

/** Which rows offer "Eliminar": the ones the user taught. */
function deletable(item: RecurringItem, manualKeys: Set<string>): boolean {
    return isRestKey(item.key) || manualKeys.has(item.key);
}

function kindOf(item: RecurringItem): string {
    return isRestKey(item.key) ? "rest" : "series";
}

function Initial({ label, active }: { label: string; active?: boolean }) {
    const letter = (label.match(/\p{L}|\p{N}/u)?.[0] ?? "?").toUpperCase();
    return (
        <span
            aria-hidden
            className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-label font-medium",
                active
                    ? "border-signal/50 bg-paper text-edge"
                    : "border-mist bg-fog text-graphite"
            )}
        >
            {letter}
        </span>
    );
}

function Meta({ children }: { children: ReactNode }) {
    return (
        <>
            <span aria-hidden className="text-mist">
                ·
            </span>
            <span className="text-label text-graphite">{children}</span>
        </>
    );
}

function InPeriod({ active }: { active?: boolean } = {}) {
    return (
        <span
            className={cn(
                "rounded px-2 py-0.5 text-label",
                active
                    ? "border border-wash bg-wash text-edge"
                    : "border border-mist bg-fog text-graphite"
            )}
        >
            Registrado en el periodo
        </span>
    );
}

function cadence(item: RecurringItem): string {
    // A taught frequent merchant has a typical month, not a day to expect.
    if (isRestKey(item.key)) return "Sin fecha fija";
    const day = typicalDayOfMonth(item.charges ?? []);
    if (!day) {
        return item.amount_stable
            ? FREQUENCY_LABELS[item.frequency]
            : "Sin día fijo";
    }
    return `${FREQUENCY_LABELS[item.frequency]} · día ${day}`;
}
