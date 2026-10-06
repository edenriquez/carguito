"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { CalendarDays } from "lucide-react";
import { useAppData } from "@/components/AppChrome";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import { BackendNotice, EmptyState, Skeleton } from "@/components/ui";
import { useBankScope } from "@/lib/banks";
import { useCategories } from "@/lib/categories";
import { useChartsV2 } from "@/lib/chartsV2";
import { mxn } from "@/lib/format";
import { applyQuery, categoryLens } from "@/lib/movimientosQuery";
import {
    completeAverage,
    composeMonths,
    monthBounds,
    monthName,
    partialMonthOf,
    peakMonth,
    spanBounds,
    spanMonthKeys,
    spansYears,
} from "@/lib/porMes";
import { track } from "@/lib/telemetry";
import { useMovimientosSearch } from "./MovimientosSearchProvider";
import { useTransactions } from "./useTransactions";
import { MesesList } from "./MesesList";
import { PorMesChart } from "./PorMesChart";

/**
 * The run of the last months, in two beats: the months as columns with the
 * mean across them, then every month as a row, openable down to its
 * categories.
 *
 * It reads a fixed span — six calendar months ending on the newest movement
 * on record — not the app's time window. The window is a lens for one period;
 * this face is about the sequence, and a "30 días" lens holds one month.
 * Banks still apply: the scope is which accounts, the span is when.
 *
 * "Ver en transacciones" moves the app's window to that month and opens the
 * modal, so the list, the chart and the header all answer for the same span
 * — the same idiom as a drag across the Categorías chart.
 */
export function PorMesView({
}: {
} = {}) {
    const { dataVersion } = useAppData();
    const { anchor, selectCustom } = useTimeWindow();
    const { statementIds } = useBankScope(dataVersion);
    const categories = useCategories();
    const { query, openModal } = useMovimientosSearch();
    const [openKey, setOpenKey] = useState<string | null>(null);
    const v2 = useChartsV2();

    const keys = useMemo(() => spanMonthKeys(anchor), [anchor]);
    const bounds = useMemo(() => spanBounds(anchor), [anchor]);
    const { items, error, loading } = useTransactions(bounds, dataVersion, statementIds);

    const listed = useMemo(
        () => (items === null ? null : applyQuery(items, query, categoryLens(categories))),
        [items, query, categories]
    );
    const reading = useMemo(
        () => (listed ? composeMonths(listed, categories, keys) : null),
        [listed, categories, keys]
    );

    // v2: the running month is marked and left out of the mean, and the
    // title states the peak against that mean.
    const partial = useMemo(() => (v2 ? partialMonthOf(anchor) : null), [v2, anchor]);
    const average = reading
        ? v2
            ? completeAverage(reading.months, partial?.key ?? null)
            : reading.average
        : 0;
    const peak = useMemo(
        () => (v2 && reading ? peakMonth(reading.months, average, partial?.key ?? null) : null),
        [v2, reading, average, partial]
    );
    const finding = useMemo(() => {
        if (!peak) return null;
        const name = monthName(peak.month.key, spansYears(keys));
        const over = `${Math.round(peak.over * 100)}% más que tu promedio de ${mxn(average)}`;
        return peak.lastComplete
            ? `${capitalize(name)}, tu último mes completo, fue el más alto: ${mxn(peak.month.amount)}, ${over}`
            : `Gastaste ${mxn(peak.month.amount)} en ${name}: ${over}`;
    }, [peak, keys, average]);

    // Stable on purpose: it is part of the chart's options, and a new options
    // object on every render means Apex tearing the chart down and redrawing
    // it for nothing.
    const openRef = useRef(openKey);
    openRef.current = openKey;
    const toggle = useCallback((key: string) => {
        track("movimientos.month_expand", { open: openRef.current !== key });
        setOpenKey((cur) => (cur === key ? null : key));
    }, []);

    function verMes(key: string) {
        const range = monthBounds(key);
        selectCustom(range.start, range.end, "por-mes");
        openModal("por-mes", query);
    }

    function verCategoria(monthKey: string, categoryKey: string) {
        const range = monthBounds(monthKey);
        selectCustom(range.start, range.end, "por-mes");
        openModal("por-mes", { ...query, categoryIds: [categoryKey] });
    }

    if (error) {
        return (
            <div className="space-y-4">
                <BackendNotice what="tus movimientos" detail={error} />
            </div>
        );
    }

    if (reading === null) {
        return <PorMesSkeleton />;
    }

    if (reading.listed.length === 0) {
        return (
            <div className="space-y-4">
                <EmptyState icon={CalendarDays} title="Ningún cargo en los últimos meses">
                    Sube un estado de cuenta y el mes aparece aquí.
                </EmptyState>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <section className="card space-y-5">
                {finding ? (
                    <div className="min-w-0">
                        <p className="eyebrow">Por mes</p>
                        <h2 className="mt-1 text-title-sm font-normal text-ink">{finding}</h2>
                        {partial && (
                            <p className="mt-1 text-body-sm text-graphite">
                                {capitalize(monthName(partial.key, spansYears(keys)))} va al{" "}
                                {partial.day} y no entra al promedio.
                            </p>
                        )}
                    </div>
                ) : (
                    <div className="min-w-0">
                        <h2 className="text-title-sm font-normal text-ink">Por mes</h2>
                        <p className="mt-1 text-body-sm text-graphite">
                            Promedio mensual:{" "}
                            <span className="tabular text-ink">{mxn(average)}</span>
                        </p>
                    </div>
                )}
                <PorMesChart
                    months={reading.months}
                    average={average}
                    openKey={openKey}
                    onPick={toggle}
                    focusKey={peak?.month.key ?? null}
                    partial={partial}
                    ariaLabel={finding ?? undefined}
                />
                <p className="text-label text-ash">
                    Base: cargos del periodo, sin «Entre mis cuentas» ni excluidos.
                </p>
            </section>

            <section className="min-w-0 overflow-hidden rounded-card border border-mist bg-paper shadow-card">
                <MesesList
                    months={reading.listed}
                    total={reading.total}
                    count={reading.count}
                    openKey={openKey}
                    onToggle={toggle}
                    onVerMes={verMes}
                    onVerCategoria={verCategoria}
                />
            </section>
        </div>
    );
}

/** The face's geometry before its data: the reading card (title, average,
 *  the bar chart, the base note) and the month list under it. */
function PorMesSkeleton() {
    return (
        <div className="space-y-5" aria-busy>
            <section className="card space-y-5">
                <div className="space-y-2">
                    <Skeleton className="h-6 w-28" />
                    <Skeleton className="h-4 w-56" />
                </div>
                <Skeleton className="h-[280px] w-full" />
                <Skeleton className="h-3 w-72 max-w-full" />
            </section>
            <section className="rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                <div className="mb-3 flex items-center justify-between">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-5 w-24" />
                </div>
                {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="my-3 h-11" />
                ))}
            </section>
        </div>
    );
}

function capitalize(s: string): string {
    return s.charAt(0).toUpperCase() + s.slice(1);
}
