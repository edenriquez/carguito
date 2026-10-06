"use client";

import { useEffect, useMemo, useRef } from "react";
import type { ApexOptions } from "apexcharts";
import type { Transaction } from "@/lib/api";
import { chart as chartTokens, colors } from "@/design/tokens";
import { categoryColor, categoryName, type CategoryInfo } from "@/lib/categories";
import { compactMxn, dayLabel, monthLabel, mxn, mxn2 } from "@/lib/format";
import { useChartsV2 } from "@/lib/chartsV2";
import { ApexChart } from "./apex/ApexChart";

const CHART_ID = "tx-chart";

/**
 * The two readings of "every movement, charted":
 *
 * - `scatter`: one dot per transaction, x = date, y = amount. WHEN was the
 *   odd charge — outliers sit above the cloud, bursts cluster on the axis.
 *   Selection is two-way with the list.
 * - `flujo`: the aggregate — income and expense as translucent areas per
 *   time bucket (days on short windows, months on long) with the running net
 *   as a line. The shape of money moving, not its individual events;
 *   selection is deliberately inert here (an area is many movements).
 *
 * Modes `bars`, `ranking` and the stacked-by-category lived here once and
 * were retired: the first two answered questions the list already answers on
 * sort, the third was Categorías' chart twice. Stored values for them fall
 * back to `scatter` via the caller's unknown-mode guard.
 */
export const CHART_MODES = ["scatter", "flujo"] as const;
export type ChartMode = (typeof CHART_MODES)[number];

export const CHART_MODE_LABELS: Record<ChartMode, string> = {
    scatter: "Puntos",
    flujo: "Flujo",
};

/** What decides a mark's color: nothing (the neutral), or its category. */
export const COLOR_MODES = ["neutral", "categoria"] as const;
export type ColorMode = (typeof COLOR_MODES)[number];

export const COLOR_MODE_LABELS: Record<ColorMode, string> = {
    neutral: "Neutro",
    categoria: "Categoría",
};

/** Local-midnight ms, parsed by hand: Date.parse("2026-08-12") is UTC
 *  midnight, which is the previous evening in Mexico City.
 *
 *  Exported because the range filter compares against the chart's own x
 *  values: the caller must place a transaction on the axis exactly the way
 *  the chart did, or a selection edge would include a dot it visibly excludes. */
export function dateToMs(isoDate: string): number {
    const [y, m, d] = isoDate.split("-").map(Number);
    return new Date(y, (m ?? 1) - 1, d ?? 1).getTime();
}

const toMs = dateToMs;

/** v2: categories named in the stone ramp before the rest go to one Ash series. */
const NAMED_CATEGORIES = 5;

/** The middle cargo: what "a normal charge" is in this window. */
export function medianAmount(transactions: Transaction[]): number | null {
    const amounts = transactions
        .filter((t) => t.type === "expense")
        .map((t) => Math.abs(t.amount))
        .sort((a, b) => a - b);
    if (amounts.length === 0) return null;
    const mid = Math.floor(amounts.length / 2);
    return amounts.length % 2 ? amounts[mid]! : (amounts[mid - 1]! + amounts[mid]!) / 2;
}

/** A dragged x-range, in the same local-midnight ms as the marks. */
export type ChartRange = { start: number; end: number };

const HOUR_MS = 3_600_000;

/** Above this many marks the scatter stops animating: the tween would stutter. */
const ANIMATED_MARKS = 1500;

/**
 * Selection is two-way with the table:
 * - mark → row: Apex `dataPointSelection` → `onSelect(id)`.
 * - row → mark: `ApexCharts.exec(..., "toggleDataPointSelection")` from an
 *   effect. Two guards are load-bearing: `exec` TOGGLES (re-execing the
 *   selected point would deselect it) and it RE-FIRES `dataPointSelection`
 *   (without suppression, select → event → select is a loop).
 */
export function TransactionsChart({
    transactions,
    mode,
    colorMode,
    categories,
    showIncome,
    grain,
    selectedId,
    onSelect,
    onRangeSelect,
    zoomRange = null,
    height = 320,
    focusCategoryId = null,
    ariaLabel,
}: {
    /** Already window+search filtered, `tx_date DESC` from the API. */
    transactions: Transaction[];
    mode: ChartMode;
    /** "categoria" colors every mark by its category; corrections become
     *  visible — fix a category and watch the mark change. */
    colorMode: ColorMode;
    /** From useCategories(); null degrades to the neutral palette. */
    categories: Map<string, CategoryInfo> | null;
    showIncome: boolean;
    /** Bucket size for the aggregate modes: the window decides, not the chart. */
    grain: "day" | "month";
    selectedId: string | null;
    onSelect: (id: string | null) => void;
    /** Drag a horizontal range over the scatter → this fires with its bounds.
     *  Scatter only: an aggregate bucket is many movements, and `flujo`'s axis
     *  is categories, not time. Absent = dragging does nothing. */
    onRangeSelect?: (range: ChartRange | null) => void;
    /** The selected range, applied back to the axis as a zoom: the x domain
     *  narrows to these bounds, so the drag reads as "open these weeks up",
     *  not just "filter the table below". Scatter only. The chart REMOUNTS
     *  when this changes (it is part of the key): a remount both applies the
     *  new axis cleanly and erases the drawn rectangle — zoomed in, the
     *  selection would cover the whole plot and say nothing. */
    zoomRange?: ChartRange | null;
    height?: number;
    /** v2, categoria mode: the category the reading is about, in Signal. */
    focusCategoryId?: string | null;
    /** v2: the title's sentence, for screen readers. */
    ariaLabel?: string;
}) {
    const v2 = useChartsV2();
    const byCategory = colorMode === "categoria" && categories !== null;

    const { series, pointIds, idToPoint, seriesColors, stackedBuckets, firstBucket } = useMemo(() => {
        const pool = showIncome
            ? transactions
            : transactions.filter((t) => t.type === "expense");

        if (mode === "scatter") {
            // Scatter colors are per-series, so the grouping IS the coloring:
            // by direction in neutral mode, by category in categoria mode.
            let groups: Transaction[][];
            let names: string[];
            let seriesColors: string[];
            if (byCategory && v2) {
                // v2: identity is position in the stone ramp, not hue. The
                // ramp follows each category's total over the whole window,
                // so a colour means the same rank wherever it shows; Signal
                // is only the focused category; past the top five, one Ash.
                const keys = new Map<string | null, Transaction[]>();
                for (const t of pool) {
                    const k = t.category_id ?? null;
                    const g = keys.get(k);
                    if (g) g.push(t);
                    else keys.set(k, [t]);
                }
                const total = (txns: Transaction[]) =>
                    txns.reduce((s, t) => s + Math.abs(t.amount), 0);
                const ranked = Array.from(keys.entries()).sort(
                    (a, b) => total(b[1]) - total(a[1])
                );
                const focus = ranked.find(([k]) => focusCategoryId !== null && k === focusCategoryId);
                const others = ranked.filter((e) => e !== focus);
                const top = others.slice(0, NAMED_CATEGORIES);
                const rest = others.slice(NAMED_CATEGORIES).flatMap(([, txns]) => txns);
                groups = [...(focus ? [focus[1]] : []), ...top.map(([, txns]) => txns)];
                names = [
                    ...(focus ? [categoryName(categories, focus[0])] : []),
                    ...top.map(([k]) => categoryName(categories, k)),
                ];
                seriesColors = [
                    ...(focus ? [colors.signal] : []),
                    ...top.map((_, i) => chartTokens.neutral[i]!),
                ];
                if (rest.length > 0) {
                    groups.push(rest);
                    names.push("Otras categorías");
                    seriesColors.push(colors.ash);
                }
            } else if (byCategory) {
                const keys = new Map<string | null, Transaction[]>();
                for (const t of pool) {
                    const k = t.category_id ?? null;
                    const g = keys.get(k);
                    if (g) g.push(t);
                    else keys.set(k, [t]);
                }
                // Biggest group first so the legend leads with what dominates.
                const entries = Array.from(keys.entries()).sort(
                    (a, b) => b[1].length - a[1].length
                );
                groups = entries.map(([, txns]) => txns);
                names = entries.map(([k]) => categoryName(categories, k));
                seriesColors = entries.map(([k]) => categoryColor(categories, k));
            } else {
                groups = showIncome
                    ? [
                          pool.filter((t) => t.type === "expense"),
                          pool.filter((t) => t.type === "income"),
                      ]
                    : [pool];
                names = ["Gastos", "Ingresos"];
                seriesColors = [chartTokens.neutral[3], colors.signal];
            }
            return {
                series: groups.map((txns, gi) => ({
                    name: names[gi],
                    data: txns.map((t) => ({ x: toMs(t.date), y: t.amount })),
                })),
                pointIds: groups.map((txns) => txns.map((t) => t.id)),
                idToPoint: new Map(
                    groups.flatMap((txns, si) =>
                        txns.map((t, di) => [t.id, [si, di] as [number, number]])
                    )
                ),
                seriesColors,
                stackedBuckets: [] as string[],
                firstBucket: null as string | null,
            };
        }

        if (mode === "flujo") {
            // Aggregate: income and expense per bucket, plus the running net —
            // the answer to "¿voy ganando o perdiendo?" over the window.
            const bucketOf = (iso: string) => (grain === "day" ? iso : iso.slice(0, 7));

            const buckets: string[] = [];
            const income = new Map<string, number>();
            const expense = new Map<string, number>();
            for (const t of transactions) {
                // Same ledger rules as the cube: a transfer between the
                // user's own accounts is not income or spend, and excluded
                // rows stay excluded. The scatter still shows them — it is
                // the ledger — but an aggregate that counted them would call
                // moving your own money "losing" it.
                if (t.is_transfer || t.excluded_from_stats) continue;
                const b = bucketOf(t.date);
                if (!buckets.includes(b)) buckets.push(b);
                const bag = t.type === "income" ? income : expense;
                bag.set(b, (bag.get(b) ?? 0) + t.amount);
            }
            buckets.sort();
            let running = 0;
            const net = buckets.map((b) => {
                running += (income.get(b) ?? 0) - (expense.get(b) ?? 0);
                return Math.round(running);
            });

            return {
                series: [
                    {
                        name: "Ingresos",
                        type: "area" as const,
                        data: buckets.map((b) => Math.round(income.get(b) ?? 0)),
                    },
                    {
                        name: "Gastos",
                        type: "area" as const,
                        data: buckets.map((b) => Math.round(expense.get(b) ?? 0)),
                    },
                    { name: "Neto acumulado", type: "line" as const, data: net },
                ],
                // No per-mark identity in an aggregate: selection stays inert.
                pointIds: [] as string[][],
                idToPoint: new Map<string, [number, number]>(),
                seriesColors: [chartTokens.neutral[1], chartTokens.neutral[4], colors.signal],
                firstBucket: buckets[0] ?? null,
                stackedBuckets: buckets.map((b) => {
                    const date = toMs(grain === "day" ? b : `${b}-01`);
                    return grain === "day"
                        ? dayLabel(new Date(date))
                        : monthLabel(new Date(date), true);
                }),
            };
        }

        // Unreachable: both modes return above. Keeps TS's control-flow happy.
        throw new Error(`unknown chart mode: ${mode}`);
    }, [transactions, showIncome, mode, byCategory, categories, grain, v2, focusCategoryId]);

    // v2: the typical cargo, drawn as a rule so an outlier reads as "far above
    // normal", not just "high".
    const median = useMemo(
        () => (v2 && mode === "scatter" ? medianAmount(transactions) : null),
        [v2, mode, transactions]
    );

    // Both handlers live in refs so the options memo does not rebuild every
    // time the parent re-renders (parents pass inline functions). This is
    // load-bearing, not an optimization: a rebuilt options object makes
    // react-apexcharts call updateOptions, which tears down and redraws the
    // chart's internals — and if that happens while a drag-selection gesture
    // has a debounce timer pending, the timer fires against a destroyed
    // gridRect and crashes with "Cannot read properties of null".
    const onRangeSelectRef = useRef(onRangeSelect);
    onRangeSelectRef.current = onRangeSelect;
    const onSelectRef = useRef(onSelect);
    onSelectRef.current = onSelect;

    // Refs shared between the event handler and the row→mark effect.
    const suppressEvent = useRef(false);
    const lastExeced = useRef<[number, number] | null>(null);
    const idToPointRef = useRef(idToPoint);
    idToPointRef.current = idToPoint;
    const pointIdsRef = useRef(pointIds);
    pointIdsRef.current = pointIds;

    // A mode change remounts the chart (see the `key` on ApexChart below), so
    // whatever selection was exec'd into the previous instance is gone with
    // it. Forget it BEFORE the selection effect runs — effects run in
    // declaration order — so the effect re-applies onto the fresh chart.
    useEffect(() => {
        lastExeced.current = null;
    }, [mode, showIncome, colorMode, zoomRange, v2, focusCategoryId]);

    // Row → mark. Data or mode changes rebuild the chart, so re-run then too.
    useEffect(() => {
        const target = selectedId ? idToPointRef.current.get(selectedId) ?? null : null;
        const prev = lastExeced.current;
        const same =
            (target === null && prev === null) ||
            (target !== null && prev !== null && target[0] === prev[0] && target[1] === prev[1]);
        if (same) return;

        let cancelled = false;
        (async () => {
            // apexcharts touches `window` at import time — client-only import.
            const Apex = (await import("apexcharts")).default;
            // After a remount the new chart may not have registered under
            // CHART_ID yet — exec on a missing chart is a silent no-op and the
            // selection would just vanish. Wait for it, bounded.
            type Registry = { getChartByID?: (id: string) => unknown };
            const registry = Apex as unknown as Registry;
            for (let i = 0; i < 10 && !cancelled; i++) {
                if (registry.getChartByID?.(CHART_ID)) break;
                await new Promise((r) => setTimeout(r, 50));
            }
            if (cancelled) return;
            suppressEvent.current = true;
            try {
                if (prev) Apex.exec(CHART_ID, "toggleDataPointSelection", prev[0], prev[1]);
                if (target) Apex.exec(CHART_ID, "toggleDataPointSelection", target[0], target[1]);
                lastExeced.current = target;
            } finally {
                suppressEvent.current = false;
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [selectedId, series]);

    // Drag-to-filter, scatter only. `autoSelected: "selection"` is what makes
    // a drag draw the range rectangle instead of zooming — Apex gates the
    // gesture on that flag plus the (hidden) toolbar's selection tool, not on
    // zoom.enabled.
    const brushable = mode === "scatter" && onRangeSelect !== undefined;

    const options: ApexOptions = useMemo(() => {
        const neutral = chartTokens.neutral[3];

        const base: ApexOptions = {
            chart: {
                id: CHART_ID,
                // A window change should move the marks to where they now
                // belong, not repaint them. The one honest limit is volume:
                // past ~1,500 SVG marks the tween itself stutters on phones,
                // and a stutter is worse than a cut. Below it, dynamicAnimation
                // is the whole feeling of the filter.
                animations:
                    transactions.length <= ANIMATED_MARKS
                        ? {
                              enabled: true,
                              speed: 360,
                              easing: "easeinout" as const,
                              animateGradually: { enabled: false },
                              dynamicAnimation: { enabled: true, speed: 360 },
                          }
                        : { enabled: false },
                ...(brushable && {
                    toolbar: { show: false, autoSelected: "selection" as const },
                    zoom: { enabled: false },
                    selection: {
                        enabled: true,
                        type: "x" as const,
                        fill: { color: colors.signal, opacity: 0.08 },
                        stroke: {
                            width: 1,
                            color: colors.signal,
                            opacity: 0.5,
                            dashArray: 3,
                        },
                    },
                }),
                events: {
                    ...(brushable && {
                        selection: (
                            _ctx: unknown,
                            { xaxis }: { xaxis?: { min?: number; max?: number } }
                        ) => {
                            const { min, max } = xaxis ?? {};
                            onRangeSelectRef.current?.(
                                Number.isFinite(min) && Number.isFinite(max)
                                    ? { start: min!, end: max! }
                                    : null
                            );
                        },
                    }),
                    dataPointSelection: (_e, _ctx, ctx) => {
                        if (suppressEvent.current) return;
                        const { seriesIndex, dataPointIndex, selectedDataPoints } = ctx;
                        const still = (selectedDataPoints as number[][]).some(
                            (s) => (s?.length ?? 0) > 0
                        );
                        const id = still
                            ? pointIdsRef.current[seriesIndex]?.[dataPointIndex] ?? null
                            : null;
                        lastExeced.current = still ? [seriesIndex, dataPointIndex] : null;
                        onSelectRef.current(id);
                    },
                },
            },
            yaxis: { labels: { formatter: (v: number) => compactMxn(v) } },
            grid: { xaxis: { lines: { show: false } }, yaxis: { lines: { show: true } } },
            states: {
                // The selected mark darkens; everything else keeps its color.
                active: { filter: { type: "darken", value: 0.55 } },
            },
            tooltip: {
                shared: false,
                intersect: true,
                custom: ({ seriesIndex, dataPointIndex }) => {
                    const id = pointIdsRef.current[seriesIndex]?.[dataPointIndex];
                    const t = transactions.find((x) => x.id === id);
                    if (!t) return "";
                    const d = new Date(toMs(t.date));
                    return `
                        <div style="padding:8px 10px;max-width:260px">
                            <div style="font-size:12px;color:${colors.graphite}">${dayLabel(d)} · ${escapeHtml(categoryName(categories, t.category_id))}</div>
                            <div style="font-size:13px;color:${colors.ink};white-space:normal">${escapeHtml(t.description)}</div>
                            <div style="font-size:13px;color:${colors.ink};font-variant-numeric:tabular-nums">${t.type === "income" ? "+" : ""}${mxn2(t.amount)}</div>
                        </div>`;
                },
            },
        };

        if (mode === "flujo") {
            return {
                ...base,
                colors: seriesColors,
                // Two translucent areas whose overlap IS the reading: where
                // income shows through above expense, the month gained; the
                // Signal line carries the verdict. Straight segments — a
                // spline invents money between real points.
                stroke: { width: [2, 2, 2], curve: "straight" },
                fill: {
                    type: ["solid", "solid", "solid"],
                    opacity: [0.14, 0.22, 1],
                },
                markers: { size: 0, hover: { size: 4 } },
                xaxis: { categories: stackedBuckets },
                legend: {
                    show: true,
                    position: "top",
                    horizontalAlign: "left",
                    fontSize: "13px",
                    markers: { size: 6, shape: "circle" },
                    itemMargin: { horizontal: 10 },
                    offsetY: -4,
                },
                // Aggregate marks: the per-transaction custom tooltip would
                // lie here, so the shared default (every layer's amount for
                // the hovered bucket) replaces it.
                tooltip: {
                    shared: true,
                    intersect: false,
                    custom: undefined,
                    y: { formatter: (v: number) => mxn(v) },
                },
                // Nothing to select in an aggregate.
                states: { active: { filter: { type: "none", value: 0 } } },
                // v2: the net is a running sum that starts at zero on the
                // window's first bucket; the zero is drawn and says so.
                ...(v2 &&
                    firstBucket && {
                        annotations: {
                            yaxis: [
                                ruleAnnotation(
                                    0,
                                    `neto acumulado desde ${
                                        grain === "day"
                                            ? dayLabel(new Date(toMs(firstBucket)))
                                            : monthLabel(new Date(toMs(`${firstBucket}-01`)), true)
                                    }`
                                ),
                            ],
                        },
                    }),
            };
        }

        if (mode === "scatter") {
            return {
                ...base,
                colors: seriesColors,
                markers: { size: 4, strokeWidth: 0, hover: { size: 6 } },
                ...(median !== null && {
                    annotations: { yaxis: [ruleAnnotation(median, `mediana ${mxn(median)}`)] },
                }),
                xaxis: {
                    type: "datetime",
                    // The dragged range, applied as the axis domain. A hair of
                    // padding keeps the boundary dots off the plot's edges.
                    ...(zoomRange && {
                        min: zoomRange.start - HOUR_MS * 12,
                        max: zoomRange.end + HOUR_MS * 12,
                    }),
                    // Points are local-midnight ms; UTC rendering shifts them.
                    labels: {
                        datetimeUTC: false,
                        // Apex's datetime defaults are English — always format.
                        formatter: (value: string) => {
                            // Apex calls this with whatever it has, including
                            // undefined while an axis is still empty — which
                            // `Number()` turns into NaN and a Date into an
                            // Invalid Date. Nothing is the right label then.
                            const ms = Number(value);
                            if (!Number.isFinite(ms)) return "";
                            const d = new Date(ms);
                            return grain === "day"
                                ? dayLabel(d)
                                : monthLabel(d, true);
                        },
                        style: { colors: chartTokens.axisLabel, fontSize: "12px" },
                    },
                },
                // The legend names the grouping — directions or categories.
                legend:
                    showIncome || byCategory
                        ? {
                              show: true,
                              position: "top",
                              horizontalAlign: "left",
                              fontSize: "13px",
                              markers: { size: 6, shape: "circle" },
                              itemMargin: { horizontal: 10 },
                              offsetY: -4,
                          }
                        : { show: false },
            };
        }

        // Unreachable: both modes return above.
        throw new Error(`unknown chart mode: ${mode}`);
    }, [mode, grain, showIncome, byCategory, categories, transactions, seriesColors, stackedBuckets, brushable, zoomRange, v2, median, firstBucket]);

    const type = mode === "scatter" ? "scatter" : "line";
    return (
        // key={mode}: react-apexcharts MUTATES the mounted chart when type or
        // options change, and a scatter half-morphed into a bar chart keeps
        // stale axes and markers. A mode switch is a different chart, not an
        // update — remount it.
        <ApexChart
            // showIncome and colorMode are in the key too: both change the
            // series structure or color strategy, both remount-worthy.
            // v2 regroups categoria mode around its focus: also a new chart.
            key={`${mode}-${showIncome}-${colorMode}-${zoomRange?.start ?? "all"}-${zoomRange?.end ?? "all"}${v2 ? `-v2-${focusCategoryId ?? ""}` : ""}`}
            type={type}
            series={series}
            options={options}
            height={height}
            ariaLabel={ariaLabel}
        />
    );
}

/** v2: a dashed reference rule with its value written on it, in Graphite —
 *  the reference is stone, never Signal. */
function ruleAnnotation(y: number, text: string) {
    return {
        y,
        strokeDashArray: 4,
        borderColor: colors.muted,
        label: {
            text,
            position: "right",
            textAnchor: "end",
            offsetY: -4,
            borderWidth: 0,
            style: { background: "transparent", color: colors.graphite, fontSize: "11px" },
        },
    };
}

function escapeHtml(s: string): string {
    return s
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}
