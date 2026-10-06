"use client";

import { useMemo, useRef } from "react";
import type { ApexOptions } from "apexcharts";
import { colors as palette } from "@/design/tokens";
import { compactMxn, mxn } from "@/lib/format";
import { UNCATEGORIZED_COLOR } from "@/lib/categories";
import { useChartsV2 } from "@/lib/chartsV2";
import { ApexChart } from "@/components/charts/apex/ApexChart";

export type MonthlyCategoryPoint = {
    /** "2026-05" — the metric's month bucket key. */
    month: string;
    monthLabel: string;
    category: string;
    amount: number;
};

/**
 * Stacked columns: one column per month, one layer per category, each layer
 * in its category's color. The column's full height is the month's spend and
 * the layers answer where it went — the "how much did each month cost, and
 * on what" reading in a single mark per month.
 *
 * A layer is also a question: "which charges are these?". Clicking one asks
 * it, and the list below answers — same gesture as a dot in Movimientos, so
 * a mark in this app always means the rows behind it are one click away.
 *
 * v2: the chips are the legend (Apex's is hidden); layers outside the hovered
 * category fade; a dashed rule carries the monthly mean of the complete
 * months and the peak month shows its total; the month still being written
 * (`partial`) is drawn faded with "al {día}" and stays out of the mean.
 */
export function CategorySpendChart({
    points,
    categoryColors,
    onPick,
    height = 360,
    dimmed,
    partial,
    ariaLabel,
}: {
    points: MonthlyCategoryPoint[];
    /** category name -> color; drives layer colors and legend order. */
    categoryColors: Map<string, string>;
    /** A layer was clicked: its category and its month bucket ("2026-05"). */
    onPick?: (category: string, month: string) => void;
    height?: number;
    /** v2: categories drawn faded because another one has the focus. */
    dimmed?: Set<string>;
    /** v2: the month the latest movement falls in, when it is not over yet. */
    partial?: { month: string; day: number } | null;
    ariaLabel?: string;
}) {
    const v2 = useChartsV2();
    // The click handler reads these through a ref: Apex keeps the options
    // object it was mounted with, so a stale closure would report last
    // render's categories after a period change.
    const lookup = useRef<{ categories: string[]; months: string[] }>({
        categories: [],
        months: [],
    });

    const { series, colors, monthLabels, opacity, average, peak } = useMemo(() => {
        const months: string[] = [];
        const monthLabels: string[] = [];
        const totals = new Map<string, number>();
        for (const p of points) {
            if (!months.includes(p.month)) {
                months.push(p.month);
                monthLabels.push(p.monthLabel);
            }
            totals.set(p.category, (totals.get(p.category) ?? 0) + p.amount);
        }
        // Biggest category at the bottom of the stack: the stable base makes
        // month-to-month comparison of the dominant cost possible by eye.
        const categories = Array.from(totals.keys()).sort(
            (a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0)
        );

        const byKey = new Map(points.map((p) => [`${p.month}|${p.category}`, p.amount]));
        const colors = categories.map((c) => categoryColors.get(c) ?? UNCATEGORIZED_COLOR);
        lookup.current = { categories, months };

        if (!v2) {
            const series = categories.map((cat) => ({
                name: cat,
                data: months.map((m) => Math.round(byKey.get(`${m}|${cat}`) ?? 0)),
            }));
            return { series, colors, monthLabels, opacity: 1, average: null, peak: null };
        }

        // The unfinished month: its label says how far it got, and its layers
        // carry the fade in their own fill (#rrggbb + alpha) because Apex has
        // no per-point opacity.
        const partialIndex = partial ? months.indexOf(partial.month) : -1;
        if (partialIndex >= 0) monthLabels[partialIndex] += ` · al ${partial!.day}`;
        const series = categories.map((cat, ci) => ({
            name: cat,
            data: months.map((m, i) => ({
                x: monthLabels[i]!,
                y: Math.round(byKey.get(`${m}|${cat}`) ?? 0),
                ...(i === partialIndex ? { fillColor: `${colors[ci]}73` } : {}),
            })),
        }));
        const monthTotals = months.map((_, i) =>
            series.reduce((sum, s) => sum + (s.data[i]?.y ?? 0), 0)
        );
        const complete = monthTotals.filter((_, i) => i !== partialIndex);
        const average =
            complete.length >= 2 ? complete.reduce((a, b) => a + b, 0) / complete.length : null;
        let peakIndex = -1;
        monthTotals.forEach((total, i) => {
            if (i === partialIndex || total <= 0) return;
            if (peakIndex < 0 || total > monthTotals[peakIndex]!) peakIndex = i;
        });
        const peak =
            peakIndex >= 0 ? { label: monthLabels[peakIndex]!, total: monthTotals[peakIndex]! } : null;
        const opacity = categories.map((c) => (dimmed?.has(c) ? 0.3 : 1));
        return { series, colors, monthLabels, opacity, average, peak };
    }, [points, categoryColors, v2, dimmed, partial]);

    const options: ApexOptions = useMemo(
        () => ({
            chart: {
                stacked: true,
                events: {
                    dataPointSelection: (_e, _ctx, ctx) => {
                        const { categories, months } = lookup.current;
                        const category = categories[ctx.seriesIndex];
                        const month = months[ctx.dataPointIndex];
                        if (category && month) onPick?.(category, month);
                    },
                },
            },
            colors,
            plotOptions: { bar: { columnWidth: "55%", borderRadius: 2 } },
            stroke: { width: 0 },
            xaxis: { categories: monthLabels },
            ...(v2
                ? {
                      fill: { opacity },
                      annotations: {
                          yaxis: average
                              ? [
                                    {
                                        y: Math.round(average),
                                        strokeDashArray: 4,
                                        borderColor: palette.graphite,
                                        label: {
                                            text: `promedio ${mxn(average)}`,
                                            position: "left",
                                            textAnchor: "start",
                                            offsetY: -4,
                                            borderWidth: 0,
                                            style: {
                                                background: "transparent",
                                                color: palette.graphite,
                                                fontSize: "11px",
                                            },
                                        },
                                    },
                                ]
                              : [],
                          points: peak
                              ? [
                                    {
                                        x: peak.label,
                                        y: peak.total,
                                        marker: { size: 0 },
                                        label: {
                                            text: mxn(peak.total),
                                            borderWidth: 0,
                                            offsetY: -4,
                                            style: {
                                                background: "transparent",
                                                color: palette.ink,
                                                fontSize: "11px",
                                            },
                                        },
                                    },
                                ]
                              : [],
                      },
                  }
                : {}),
            yaxis: { labels: { formatter: (v: number) => compactMxn(v) } },
            legend: {
                show: !v2,
                position: "top",
                horizontalAlign: "left",
                fontSize: "13px",
                markers: { size: 6, shape: "circle" },
                itemMargin: { horizontal: 10 },
                offsetY: -4,
            },
            // Per-layer, not shared: the tooltip names the thing a click would
            // filter to, so hovering previews the gesture. The month's total
            // rides along — the layer answers "on what", the total "how much",
            // without hunting the column's full height against the axis.
            tooltip: {
                shared: false,
                intersect: true,
                custom: ({ series, seriesIndex, dataPointIndex }) => {
                    const category = lookup.current.categories[seriesIndex] ?? "";
                    const value = series[seriesIndex]?.[dataPointIndex] ?? 0;
                    const total = (series as number[][]).reduce(
                        (sum, layer) => sum + (layer[dataPointIndex] ?? 0),
                        0
                    );
                    return `
                        <div style="padding:8px 10px">
                            <div style="font-size:12px;color:${palette.graphite}">${escapeHtml(monthLabels[dataPointIndex] ?? "")}</div>
                            <div style="font-size:13px;color:${palette.ink};display:flex;align-items:center;gap:6px">
                                <span style="width:8px;height:8px;border-radius:9999px;background:${colors[seriesIndex]};display:inline-block"></span>
                                <span>${escapeHtml(category)}</span>
                                <span style="font-variant-numeric:tabular-nums">${mxn(value)}</span>
                            </div>
                            <div style="margin-top:2px;font-size:12px;color:${palette.graphite};font-variant-numeric:tabular-nums">Total del mes ${mxn(total)}</div>
                        </div>`;
                },
            },
            // v2: a click filters the chart down to that layer, which is the
            // feedback; darkening it as well would muddy the category's own color.
            states: {
                active: { filter: v2 ? { type: "none", value: 0 } : { type: "darken", value: 0.6 } },
            },
        }),
        [colors, monthLabels, onPick, v2, opacity, average, peak]
    );

    return (
        <ApexChart
            type="bar"
            series={series}
            options={options}
            height={height}
            ariaLabel={ariaLabel}
        />
    );
}

/** Category names are user-written text landing in tooltip HTML. */
function escapeHtml(s: string): string {
    return s
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}
