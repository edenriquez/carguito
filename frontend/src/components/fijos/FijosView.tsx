"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight, Pin, Plus, X } from "lucide-react";
import { api, type RecurringItem, type Transaction } from "@/lib/api";
import { useBankScope } from "@/lib/banks";
import { categoryName, useCategories } from "@/lib/categories";
import { cn } from "@/lib/cn";
import {
    HORIZONS,
    itemFromManual,
    itemFromRestMark,
    isRestKey,
    reconcileFijos,
    type Horizon,
} from "@/lib/fijos";
import { dayLabel, mxn, mxn2 } from "@/lib/format";
import { parsePeriodKey } from "@/lib/metrics";
import { track } from "@/lib/telemetry";
import { useAppData } from "@/components/AppChrome";
import { ChartCard } from "@/components/ChartCard";
import { LoadTimelineChart } from "@/components/recurrentes/LoadTimelineChart";
import {
    buildTimeline,
    isStale,
    ledgerEnd,
    restByMonth,
    type Timeline,
} from "@/components/recurrentes/projection";
import { rhythmCopy } from "@/components/recurrentes/rhythm";
import { buildSeriesColors, sortByWeight } from "@/components/recurrentes/seriesColors";
import { BackendNotice, Button, EmptyState, Skeleton } from "@/components/ui";
import { AddFijoSheet } from "./AddFijoSheet";
import { useFijos } from "./useFijos";

/**
 * Fijos: the planning view. You pin the charges you treat as certain; the
 * headline is those, cargo a cargo (or a typical month if there is no day),
 * plus the rest of typical recurrences you did not pin. Detection suggests;
 * you decide what is fijo. The chart is the fijos only.
 */

const FREQUENCY_LABELS: Record<RecurringItem["frequency"], string> = {
    weekly: "Semanal",
    biweekly: "Quincenal",
    monthly: "Mensual",
    bimonthly: "Bimestral",
    semiannual: "Semestral",
    yearly: "Anual",
};

const MONTHS_BACK = 12;
const RECENT_CHARGES = 6;

export function FijosView({ onGoToIngresos }: { onGoToIngresos?: () => void } = {}) {
    const { dataVersion } = useAppData();
    const [items, setItems] = useState<RecurringItem[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const categories = useCategories();
    const fijos = useFijos();
    const { state, hydrated, replace } = fijos;
    // Every decision the user makes here is recorded: which suggestions get
    // pinned, how often pins are undone, which horizon people plan on. The
    // store stays dumb; the view is where a click has a meaning.
    const pin = useCallback(
        (key: string) => {
            track("plan.fijo_pin", { kind: isRestKey(key) ? "rest" : "series" });
            fijos.pin(key);
        },
        [fijos]
    );
    const unpin = useCallback(
        (key: string) => {
            track("plan.fijo_unpin", { kind: isRestKey(key) ? "rest" : "series" });
            fijos.unpin(key);
        },
        [fijos]
    );
    const addManual: typeof fijos.addManual = useCallback(
        (manual) => {
            track("plan.fijo_add_manual", { frequency: manual.frequency });
            fijos.addManual(manual);
        },
        [fijos]
    );
    const addRest: typeof fijos.addRest = useCallback(
        (mark) => {
            track("plan.rest_add", { curated: mark.merchant !== null });
            fijos.addRest(mark);
        },
        [fijos]
    );
    const pinRest: typeof fijos.pinRest = useCallback(
        (mark) => {
            track("plan.fijo_pin", { kind: "rest", curated: mark.merchant !== null });
            fijos.pinRest(mark);
        },
        [fijos]
    );
    const setHorizon = useCallback(
        (h: Horizon) => {
            track("plan.horizon", { horizon: h, face: "fijos" });
            fijos.setHorizon(h);
        },
        [fijos]
    );
    const [openKey, setOpenKey] = useState<string | null>(null);
    const [adding, setAdding] = useState(false);
    const [ledger, setLedger] = useState<Transaction[] | null>(null);

    const { statementIds } = useBankScope(dataVersion);
    const scopeQuery = statementIds
        ? `?${statementIds.map((id) => `statement_id=${id}`).join("&")}`
        : "";

    useEffect(() => {
        let stale = false;
        api.recurring(scopeQuery)
            .then((res) => {
                if (stale) return;
                setItems(res.items.map((i) => ({ ...i, key: i.key || i.label })));
                setError(null);
            })
            .catch((e) => {
                if (stale) return;
                setError((e as Error).message);
                setItems([]);
            });
        return () => {
            stale = true;
        };
    }, [dataVersion, scopeQuery]);

    useEffect(() => {
        if (!hydrated || (state.restMarks ?? []).length === 0) {
            setLedger([]);
            return;
        }
        let stale = false;
        const params = new URLSearchParams();
        params.set("limit", "10000");
        for (const id of statementIds ?? []) params.append("statement_id", id);
        api.transactions(`?${params}`)
            .then((page) => {
                if (!stale) setLedger(page.items);
            })
            .catch(() => {
                if (!stale) setLedger([]);
            });
        return () => {
            stale = true;
        };
    }, [hydrated, dataVersion, statementIds, state.restMarks]);

    // Merge manuals that detection has since found, once both sides exist.
    useEffect(() => {
        if (!hydrated || !items) return;
        const next = reconcileFijos(state, items);
        if (next !== state) replace(next);
    }, [hydrated, items, state, replace]);

    const loading = items === null || !hydrated;
    const detected = items ?? [];

    const manuals = useMemo(() => state.manuals.map(itemFromManual), [state.manuals]);

    const taughtRest = useMemo(() => {
        if (!ledger?.length) return [];
        return (state.restMarks ?? [])
            .map((m) => itemFromRestMark(m, ledger))
            .filter((i): i is RecurringItem => i !== null);
    }, [state.restMarks, ledger]);

    const pinnedRest = useMemo(
        () => taughtRest.filter((i) => state.pinnedKeys.includes(i.key)),
        [taughtRest, state.pinnedKeys]
    );
    const looseRest = useMemo(
        () => taughtRest.filter((i) => !state.pinnedKeys.includes(i.key)),
        [taughtRest, state.pinnedKeys]
    );

    const pinned = useMemo(() => {
        const fromDetected = detected.filter((i) => state.pinnedKeys.includes(i.key));
        const detectedKeys = new Set(fromDetected.map((i) => i.key));
        return [
            ...fromDetected,
            ...manuals.filter((m) => !detectedKeys.has(m.key)),
            ...pinnedRest,
        ];
    }, [detected, manuals, pinnedRest, state.pinnedKeys]);

    const suggested = useMemo(() => {
        const pinnedSet = new Set(state.pinnedKeys);
        const asOf = ledgerEnd(detected);
        return detected
            .filter((i) => !pinnedSet.has(i.key))
            .slice()
            .sort((a, b) => {
                const endedA = isStale(a, asOf) ? 1 : 0;
                const endedB = isStale(b, asOf) ? 1 : 0;
                if (endedA !== endedB) return endedA - endedB;
                if (a.amount_stable !== b.amount_stable) return a.amount_stable ? -1 : 1;
                return b.monthly_equivalent - a.monthly_equivalent;
            });
    }, [detected, state.pinnedKeys]);

    const activeDetected = useMemo(() => {
        const asOf = ledgerEnd(detected);
        return detected.filter((i) => !isStale(i, asOf));
    }, [detected]);

    const noisePool = useMemo(() => {
        const pinnedSet = new Set(state.pinnedKeys);
        return activeDetected.filter((i) => !pinnedSet.has(i.key));
    }, [activeDetected, state.pinnedKeys]);

    const allForColor = useMemo(
        () => [...detected, ...manuals, ...taughtRest],
        [detected, manuals, taughtRest]
    );
    const colorOf = useMemo(() => buildSeriesColors(allForColor), [allForColor]);

    const ledgerAsOf = useMemo(() => ledgerEnd(detected.length ? detected : pinned), [detected, pinned]);
    const horizon = state.horizon;

    // Heaviest series first: the stack darkens downward in step with the ramp
    // the colours come from.
    const timeline = useMemo(
        () => buildTimeline(sortByWeight(pinned), MONTHS_BACK, horizon),
        [pinned, horizon]
    );

    const rest = useMemo(() => {
        if (noisePool.length === 0 && activeDetected.length === 0 && looseRest.length === 0) {
            return undefined;
        }
        return restByMonth(
            noisePool,
            timeline.months,
            timeline.firstFutureIndex,
            activeDetected,
            looseRest
        );
    }, [noisePool, activeDetected, looseRest, timeline.months, timeline.firstFutureIndex]);

    const fijosNeed = timeline.totals.projected;
    const restNeed = rest && rest.rate > 0 ? rest.rate * horizon : 0;
    const need = fijosNeed + restNeed;

    const emptyDetection = !loading && detected.length === 0 && manuals.length === 0 && !error;

    return (
        <div className="space-y-4 sm:space-y-6">
            {error && <BackendNotice what="Cargos Recurrentes" detail={error} />}

            {emptyDetection ? (
                <EmptyState icon={Pin} title="Tomin aún no ve cobros que se repitan">
                    Hacen falta al menos tres cobros del mismo lugar con un ritmo
                    reconocible. Sube más estados de cuenta y aparecen solos.
                </EmptyState>
            ) : (
                <>
                    <Headline
                        need={need}
                        fijosNeed={fijosNeed}
                        restNeed={restNeed}
                        hasRest={!!rest && rest.rate > 0}
                        horizon={horizon}
                        monthlyRate={timeline.totals.monthlyRate}
                        pinnedCount={pinned.length}
                        suggestedCount={suggested.length + looseRest.length}
                        loading={loading}
                        onHorizon={setHorizon}
                        timeline={timeline}
                        onGoToIngresos={onGoToIngresos}
                    />

                    <ChartCard title="Mes a mes, y lo que viene">
                        {loading ? (
                            <Skeleton className="h-[300px]" />
                        ) : (
                            <LoadTimelineChart
                                timeline={timeline}
                                colorFor={colorOf}
                            />
                        )}
                    </ChartCard>

                    <section className="min-w-0 rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <h2 className="text-title-sm font-normal text-ink">
                                Mis fijos
                                {pinned.length > 0 && (
                                    <span className="ml-2 font-sans text-body-sm text-graphite">
                                        {pinned.length}
                                    </span>
                                )}
                            </h2>
                            <Button
                                variant="ghost"
                                size="sm"
                                icon={<Plus size={14} />}
                                onClick={() => setAdding(true)}
                            >
                                Añadir un cargo
                            </Button>
                        </div>
                        <p className="mt-1 text-body-sm text-graphite">
                            Lo que sí o sí se cobra. Con día fijo, cargo a cargo; sin
                            él, el mes típico.
                        </p>
                        <div className="mt-4">
                            {loading ? (
                                <div className="space-y-2">
                                    {[0, 1].map((i) => (
                                        <Skeleton key={i} className="h-12" />
                                    ))}
                                </div>
                            ) : pinned.length === 0 ? (
                                <p className="py-6 text-body text-graphite">
                                    Confírmalos en Cargos recurrentes, o añade uno a mano.
                                </p>
                            ) : (
                                <SeriesList
                                    items={pinned}
                                    openKey={openKey}
                                    onToggle={(i) =>
                                        setOpenKey((cur) => (cur === i.key ? null : i.key))
                                    }
                                    onUnpin={unpin}
                                    colorOf={colorOf}
                                    categories={categories}
                                    asOf={ledgerAsOf}
                                />
                            )}
                        </div>
                    </section>
                </>
            )}

            <AddFijoSheet
                open={adding}
                intent="fijo"
                onClose={() => setAdding(false)}
                detected={detected}
                dataVersion={dataVersion}
                onPin={pin}
                onAddManual={addManual}
                onAddRest={addRest}
                onPinRest={pinRest}
            />
        </div>
    );
}

function Headline({
    need,
    fijosNeed,
    restNeed,
    hasRest,
    horizon,
    monthlyRate,
    pinnedCount,
    suggestedCount,
    loading,
    onHorizon,
    timeline,
    onGoToIngresos,
}: {
    need: number;
    fijosNeed: number;
    restNeed: number;
    hasRest: boolean;
    horizon: Horizon;
    monthlyRate: number;
    pinnedCount: number;
    /** Detected series (and taught rest) still waiting for a decision. */
    suggestedCount: number;
    loading: boolean;
    onHorizon: (h: Horizon) => void;
    timeline: Timeline;
    onGoToIngresos?: () => void;
}) {
    // Nothing pinned yet: the headline is the work to do, not a total nobody
    // chose. The unconfirmed estimate moves to the small print. Voice per
    // docs/voice-and-type.md: "cobros que se repiten", never "series".
    const unstarted = !loading && pinnedCount === 0;
    const stale = daysBetween(timeline.asOf, new Date());
    const { totals } = timeline;

    return (
        <section className="min-w-0 rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                    <p className="eyebrow">
                        {unstarted ? "Para empezar" : "Necesitas"}
                    </p>
                    {loading ? (
                        <Skeleton className="mt-1 h-9 w-48" />
                    ) : unstarted ? (
                        <p className="mt-0.5 font-display text-title-md font-normal text-ink">
                            {suggestedCount > 0
                                ? `${suggestedCount} cobro${suggestedCount === 1 ? "" : "s"} que se repite${suggestedCount === 1 ? "" : "n"}`
                                : "Aún nada que fijar"}
                        </p>
                    ) : (
                        <p className="tabular mt-0.5 text-metric font-normal text-ink">
                            {mxn(need)}
                        </p>
                    )}
                    <p className="mt-1 text-body text-graphite">
                        {unstarted
                            ? suggestedCount > 0
                                ? "Confírmalos en Cargos recurrentes; el total aparece con el primero."
                                : "Elige lo que sí o sí se cobra, o añade un cargo a mano."
                            : `en los próximos ${horizon} meses`}
                    </p>
                    {unstarted && hasRest && (
                        <p className="mt-2 text-body-sm text-graphite">
                            Lo que aún no confirmas suma ~{mxn(restNeed)} en {horizon} meses.
                        </p>
                    )}
                    {!loading && pinnedCount > 0 && (
                        <p className="mt-2 text-body-sm text-graphite">
                            Fijos {mxn(fijosNeed)}
                            {hasRest && (
                                <>
                                    <span className="text-ash"> · </span>
                                    Sin confirmar {mxn(restNeed)}
                                </>
                            )}
                            {pinnedCount > 0 && (
                                <>
                                    <span className="text-ash"> · </span>
                                    ritmo de fijos {mxn(monthlyRate)}/mes
                                </>
                            )}
                        </p>
                    )}
                </div>

                <div className="flex flex-col items-end gap-3">
                    <div className="flex flex-wrap items-center justify-end gap-x-3">
                        {suggestedCount > 0 && (
                            <Link
                                href="/"
                                className="text-body-sm text-graphite underline decoration-mist underline-offset-4 hover:text-ink"
                            >
                                Confirmar en Movimientos › Cargos recurrentes →
                            </Link>
                        )}
                        {onGoToIngresos && !loading && (
                            <button
                                type="button"
                                onClick={onGoToIngresos}
                                className="text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                            >
                                Ver ingresos →
                            </button>
                        )}
                    </div>
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
                                    onClick={() => onHorizon(h)}
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

            {!loading && (totals.endedSeries > 0 || (totals.projected === 0 && stale > 30 && pinnedCount > 0)) && (
                <p className="mt-4 text-body-sm text-graphite">
                    {totals.endedSeries > 0 && (
                        <>
                            {totals.endedSeries} fijo
                            {totals.endedSeries === 1 ? "" : "s"} sin cargos desde antes del
                            último movimiento; no {totals.endedSeries === 1 ? "se proyecta" : "se proyectan"}.{" "}
                        </>
                    )}
                    {stale > 30 && (
                        <>
                            Tu último movimiento es del {dayLabel(timeline.asOf)}: sube un
                            estado de cuenta más reciente para afinar la proyección.
                        </>
                    )}
                </p>
            )}
        </section>
    );
}

function SeriesList({
    items,
    openKey,
    onToggle,
    onUnpin,
    colorOf,
    categories,
    asOf,
}: {
    items: RecurringItem[];
    openKey: string | null;
    onToggle: (i: RecurringItem) => void;
    onUnpin: (key: string) => void;
    colorOf: (label: string) => string;
    categories: ReturnType<typeof useCategories>;
    asOf: Date;
}) {
    return (
        <ul className="divide-y divide-mist">
            {items.map((i) => {
                const open = openKey === i.key;
                const rest = isRestKey(i.key);
                return (
                    <li key={i.key}>
                        <div className="flex items-start gap-2 py-2.5">
                            <button
                                type="button"
                                onClick={() => onToggle(i)}
                                aria-expanded={open}
                                aria-controls={`fijo-${i.key}`}
                                className="min-w-0 flex-1 text-left"
                            >
                                <div className="flex items-center justify-between gap-3">
                                    <span className="flex min-w-0 items-center gap-2">
                                        <ChevronRight
                                            size={14}
                                            aria-hidden
                                            className={cn(
                                                "shrink-0 text-ash transition-transform duration-100",
                                                open && "rotate-90"
                                            )}
                                        />
                                        <span
                                            aria-hidden
                                            title={categoryName(categories, i.category_id)}
                                            className="h-2 w-2 shrink-0 rounded-full"
                                            style={{ background: colorOf(i.label) }}
                                        />
                                        <span className="truncate text-body text-ink">{i.label}</span>
                                    </span>
                                    <span className="tabular shrink-0 whitespace-nowrap text-body-sm text-ink">
                                        {i.amount_stable ? "" : "~"}
                                        {mxn2(i.typical_amount)}
                                    </span>
                                </div>
                                <div className="mt-0.5 flex items-center justify-between gap-3 pl-6 text-body-sm text-graphite">
                                    <span>
                                        {rest
                                            ? `Sin fecha fija · ${mxn(i.monthly_equivalent)}/mes`
                                            : `${FREQUENCY_LABELS[i.frequency]} · ${mxn(i.monthly_equivalent)}/mes`}
                                        {!rest && !i.amount_stable && " · varía"}
                                    </span>
                                    {!rest && <NextExpected item={i} asOf={asOf} />}
                                </div>
                            </button>
                            <button
                                type="button"
                                onClick={() => onUnpin(i.key)}
                                aria-label={`Quitar ${i.label}`}
                                title="Quitar de fijos"
                                className="shrink-0 rounded-control p-1.5 text-graphite hover:bg-fog hover:text-ink"
                            >
                                <X size={14} aria-hidden />
                            </button>
                        </div>
                        {open && (
                            <div id={`fijo-${i.key}`} className="pb-3 pl-6">
                                <SeriesDetail item={i} rest={rest} />
                            </div>
                        )}
                    </li>
                );
            })}
        </ul>
    );
}

function SeriesDetail({ item, rest }: { item: RecurringItem; rest?: boolean }) {
    const charges = item.charges ?? [];
    const rhythm = rest ? null : rhythmCopy(charges, item.frequency);

    if (!charges.length) {
        return (
            <p className="text-body-sm text-graphite">
                Este cargo se detectó antes de que guardáramos sus fechas. Vuelve a subir
                el estado de cuenta para verlas.
            </p>
        );
    }

    const recent = [...charges]
        .sort((a, b) => b.date.localeCompare(a.date))
        .slice(0, RECENT_CHARGES);

    return (
        <div className="min-w-0">
            <p className="text-body text-ink">
                {rhythm ??
                    (rest
                        ? "Sin un día fijo: el mes típico es lo que cobraron, no un calendario."
                        : "Sin un día fijo: el ritmo es regular, el día no.")}
            </p>
            <p className="mt-2 text-body-sm text-graphite">
                Últimos cargos:{" "}
                <span className="tabular text-ink">
                    {recent.map((c) => isoToLabel(c.date)).join(" · ")}
                </span>
                {charges.length > RECENT_CHARGES &&
                    ` · y ${charges.length - RECENT_CHARGES} más`}
            </p>
        </div>
    );
}

function daysUntil(item: RecurringItem): number | null {
    const next = parsePeriodKey(item.next_expected);
    if (!next) return null;
    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((next.getTime() - midnight.getTime()) / 86_400_000);
}

function expectedCopy(item: RecurringItem): string {
    const days = daysUntil(item);
    if (days === null) return item.next_expected;
    if (days < -1) return `esperado hace ${-days} días`;
    if (days === -1) return "esperado ayer";
    if (days === 0) return "hoy";
    if (days === 1) return "mañana";
    return `en ${days} días`;
}

function NextExpected({ item, asOf }: { item: RecurringItem; asOf: Date }) {
    const copy = expectedCopy(item);
    const overdue = copy.startsWith("esperado");
    const days = daysUntil(item);
    const imminent = !overdue && days !== null && days <= 3;
    const ended = isStale(item, asOf);
    return (
        <span
            className={cn(
                "hidden text-body-sm sm:inline",
                overdue ? "text-ash" : imminent ? "font-medium text-ink" : "text-graphite"
            )}
        >
            {isoToLabel(item.next_expected)} · {copy}
            {ended && <span className="text-ash"> · sin proyección</span>}
        </span>
    );
}

function isoToLabel(iso: string): string {
    const d = parsePeriodKey(iso);
    return d ? dayLabel(d) : iso;
}

function daysBetween(a: Date, b: Date): number {
    return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}
