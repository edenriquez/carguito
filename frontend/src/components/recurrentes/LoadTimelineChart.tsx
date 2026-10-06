"use client";

import { useMemo } from "react";
import type { ApexOptions } from "apexcharts";
import { colors } from "@/design/tokens";
import { useChartsV2 } from "@/lib/chartsV2";
import { compactMxn, monthLabel, mxn } from "@/lib/format";
import { ApexChart } from "@/components/charts/apex/ApexChart";
import { monthKeyToDate, type Timeline } from "./projection";

/**
 * The selected series month by month: measured months on the left, projected
 * months on the right, one stack per month split by series.
 *
 * The boundary is drawn, not implied. A projection rendered like a
 * measurement is the most expensive lie a finance UI can tell, so the future
 * sits on a Fog band labelled "Proyección", opened by a dashed rule at today's
 * month — the rule survives the horizontal scroll on a phone, where the label
 * can end up off-screen.
 *
 * Colour is the charge: one series is one colour here, on the calendar and on
 * its chip, drawn from the category taxonomy (`buildSeriesColors`).
 *
 * Only confirmed charges are drawn. A series detection merely suspects is not
 * money anyone has committed to, and a column that mixes the two makes its own
 * total unusable.
 *
 * The month's sum lives in the tooltip, not over the column: a number standing
 * on every bar competes with the shape the chart is drawn for. The columns do
 * move into place, though — the app's charts animate a change rather than
 * repaint it.
 */
/**
 * Past this many series the tween itself is the jank — Apex animates every
 * rect in every column — so a crowded chart cuts instead of moving.
 */
const ANIMATED_SERIES = 24;
/** Staggering the grow-in only reads as intent while the stack is small. */
const GRADUAL_SERIES = 10;
/** v2: past this many series the smallest fold into one «Otros» layer — a
 *  stack of twenty slivers has no shape left to read. */
const MAX_DRAWN = 8;
const OTHERS = "Otros";

/**
 * v2 headline: the finding, in the numbers the chart is drawn from. `null`
 * when there is no rate to state, so the caller keeps its plain title.
 */
export function timelineHeadline(timeline: Timeline): string | null {
    const { monthlyRate, projected } = timeline.totals;
    if (!timeline.series.length || monthlyRate <= 0) return null;
    // Months after the current one: buildTimeline lays out back + ahead, and
    // the current month is the first future index.
    const ahead = timeline.months.length - timeline.firstFutureIndex - 1;
    const head = `Tus fijos suman ${mxn(monthlyRate)} al mes`;
    // Named by its last month rather than counted: «los próximos N meses»
    // reads as N after today, and the window may or may not include today.
    const last = timeline.months[timeline.months.length - 1];
    return ahead > 0 && last
        ? `${head}; de aquí a ${monthLabel(monthKeyToDate(last), true)}, ${mxn(projected)}`
        : head;
}

type Drawn = { label: string; values: number[]; color: string };

export function LoadTimelineChart({
    timeline,
    colorFor,
    height = 300,
}: {
    timeline: Timeline;
    /** Series label -> colour, shared with the calendar and the chips so one
     *  series is one colour everywhere on the page. */
    colorFor: (label: string) => string;
    height?: number;
}) {
    const v2 = useChartsV2();
    const labels = useMemo(
        () => timeline.months.map((m) => monthLabel(monthKeyToDate(m), true)),
        [timeline.months]
    );

    // What is actually stacked. v1 draws every series; v2 keeps the heaviest
    // and folds the tail into «Otros» in Ash, after them on the stack.
    const drawn: Drawn[] = useMemo(() => {
        const all = timeline.series.map((s) => ({
            label: s.item.label,
            values: s.values,
            color: colorFor(s.item.label),
        }));
        if (!v2 || all.length <= MAX_DRAWN) return all;
        const sum = (d: Drawn) => d.values.reduce((a, b) => a + b, 0);
        const ranked = [...all].sort((a, b) => sum(b) - sum(a));
        const keep = new Set(ranked.slice(0, MAX_DRAWN - 1));
        const tail = all.filter((d) => !keep.has(d));
        return [
            ...all.filter((d) => keep.has(d)),
            {
                label: OTHERS,
                values: timeline.months.map((_, i) => tail.reduce((s, d) => s + (d.values[i] ?? 0), 0)),
                color: colors.ash,
            },
        ];
    }, [timeline, colorFor, v2]);

    const options: ApexOptions = useMemo(() => {
        const firstFuture = labels[timeline.firstFutureIndex];
        const lastLabel = labels[labels.length - 1];
        const count = drawn.length;
        const totals = timeline.months.map((_, i) => drawn.reduce((s, d) => s + (d.values[i] ?? 0), 0));
        // v2 callout: the tallest column, named by the charge that makes it.
        const peakAt = totals.reduce((best, t, i) => (t > (totals[best] ?? 0) ? i : best), 0);
        const peakBy = drawn.reduce<Drawn | null>(
            (best, d) => (!best || (d.values[peakAt] ?? 0) > (best.values[peakAt] ?? 0) ? d : best),
            null
        );
        const rate = timeline.totals.monthlyRate;

        return {
            chart: {
                stacked: true,
                toolbar: { show: false },
                animations:
                    count <= ANIMATED_SERIES
                        ? {
                              enabled: true,
                              speed: 320,
                              easing: "easeinout",
                              animateGradually: {
                                  enabled: count <= GRADUAL_SERIES,
                                  delay: 40,
                              },
                              dynamicAnimation: { enabled: true, speed: 320 },
                          }
                        : { enabled: false },
            },
            colors: drawn.map((d) => d.color),
            plotOptions: { bar: { columnWidth: "62%", borderRadius: 2 } },
            stroke: { width: 0 },
            dataLabels: { enabled: false },
            // Eighteen columns on a phone: thinner gaps and a smaller month
            // label are what keep the axis readable at that width.
            // v2 keeps the theme's axis type at every width.
            responsive: [
                {
                    breakpoint: 640,
                    options: {
                        plotOptions: { bar: { columnWidth: "72%" } },
                        ...(v2 ? {} : { xaxis: { labels: { style: { fontSize: "10px" } } } }),
                    },
                },
            ],
            xaxis: {
                categories: labels,
                ...(v2 ? {} : { labels: { style: { colors: colors.graphite, fontSize: "12px" } } }),
                axisTicks: { show: false },
            },
            yaxis: { labels: { formatter: (v: number) => compactMxn(v) } },
            grid: { xaxis: { lines: { show: false } }, yaxis: { lines: { show: true } } },
            legend: { show: false },
            annotations: v2
                ? {
                      // The future is marked by its own columns (lighter, see
                      // `series`), so the band is only a faint ground and the
                      // dashed rule; it no longer greys the charges out.
                      xaxis:
                          firstFuture && timeline.firstFutureIndex < labels.length
                              ? [
                                    {
                                        x: firstFuture,
                                        x2: lastLabel,
                                        fillColor: colors.fog,
                                        opacity: 0.12,
                                        label: {
                                            text: "Proyección",
                                            position: "top",
                                            orientation: "horizontal",
                                            offsetY: -4,
                                            style: { background: "transparent", color: colors.graphite },
                                            borderWidth: 0,
                                        },
                                    },
                                    { x: firstFuture, strokeDashArray: 4, borderColor: colors.muted },
                                ]
                              : [],
                      // The steady rate the headline states, as a level the
                      // columns can be read against.
                      yaxis:
                          rate > 0
                              ? [
                                    {
                                        y: rate,
                                        strokeDashArray: 3,
                                        borderColor: colors.graphite,
                                        label: {
                                            text: `tus fijos: ${mxn(rate)}/mes`,
                                            position: "left",
                                            textAnchor: "start",
                                            offsetX: 4,
                                            style: { background: colors.paper, color: colors.graphite },
                                            borderWidth: 0,
                                        },
                                    },
                                ]
                              : [],
                      points:
                          peakBy && (totals[peakAt] ?? 0) > 0
                              ? [
                                    {
                                        x: labels[peakAt],
                                        y: totals[peakAt],
                                        marker: { size: 0 },
                                        label: {
                                            text: `Pico: ${peakBy.label}, ${mxn(peakBy.values[peakAt] ?? 0)}`,
                                            offsetY: -2,
                                            style: { background: colors.paper, color: colors.ink },
                                            borderWidth: 0,
                                        },
                                    },
                                ]
                              : [],
                  }
                : firstFuture && timeline.firstFutureIndex < labels.length
                    ? {
                          xaxis: [
                              {
                                  x: firstFuture,
                                  x2: lastLabel,
                                  fillColor: colors.fog,
                                  // The band sits *over* the columns (Apex
                                  // draws annotations last), so it has to be
                                  // thin enough to leave each charge its
                                  // colour — the future is marked, not muted
                                  // into one grey block.
                                  opacity: 0.35,
                                  label: {
                                      text: "Proyección",
                                      position: "top",
                                      orientation: "horizontal",
                                      offsetY: -4,
                                      style: {
                                          background: "transparent",
                                          color: colors.ash,
                                          fontSize: "10px",
                                      },
                                      borderWidth: 0,
                                  },
                              },
                              {
                                  x: firstFuture,
                                  strokeDashArray: 4,
                                  borderColor: colors.muted,
                              },
                          ],
                      }
                    : {},
            tooltip: v2
                ? {
                      // The whole month at once, heaviest first, with its sum:
                      // a single-layer tooltip made the reader hunt slivers.
                      shared: true,
                      intersect: false,
                      cssClass: "load-timeline-tooltip",
                      custom: ({ dataPointIndex }: { dataPointIndex: number }) => {
                          const rows = drawn
                              .map((d) => ({ d, v: Math.round(d.values[dataPointIndex] ?? 0) }))
                              .filter((r) => r.v > 0)
                              .sort((a, b) => b.v - a.v);
                          const total = rows.reduce((s, r) => s + r.v, 0);
                          return `
                        <div style="padding:8px 10px">
                            <div style="font-size:12px;color:${colors.graphite}">${escapeHtml(labels[dataPointIndex] ?? "")}${monthState(dataPointIndex, timeline.firstFutureIndex)}</div>
                            ${rows
                                .map(
                                    (r) => `<div style="font-size:13px;color:${colors.ink};display:flex;align-items:center;gap:6px">
                                <span style="width:8px;height:8px;border-radius:9999px;background:${r.d.color};display:inline-block"></span>
                                <span style="flex:1">${escapeHtml(r.d.label)}</span>
                                <span style="font-variant-numeric:tabular-nums">${mxn(r.v)}</span>
                            </div>`
                                )
                                .join("")}
                            <div style="margin-top:2px;font-size:12px;color:${colors.ink};font-variant-numeric:tabular-nums">Total del mes ${mxn(total)}</div>
                        </div>`;
                      },
                  }
                : {
                shared: false,
                intersect: true,
                cssClass: "load-timeline-tooltip",
                custom: ({ series, seriesIndex, dataPointIndex }) => {
                    const label = timeline.series[seriesIndex]?.item.label ?? "";
                    const value = series[seriesIndex]?.[dataPointIndex] ?? 0;
                    const total = (series as number[][]).reduce(
                        (sum, layer) => sum + (layer[dataPointIndex] ?? 0),
                        0
                    );
                    const swatch = colorFor(label);
                    return `
                        <div style="padding:8px 10px">
                            <div style="font-size:12px;color:${colors.graphite}">${escapeHtml(labels[dataPointIndex] ?? "")}${monthState(dataPointIndex, timeline.firstFutureIndex)}</div>
                            <div style="font-size:13px;color:${colors.ink};display:flex;align-items:center;gap:6px">
                                <span style="width:8px;height:8px;border-radius:9999px;background:${swatch};display:inline-block"></span>
                                <span>${escapeHtml(label)}</span>
                                <span style="font-variant-numeric:tabular-nums">${mxn(value)}</span>
                            </div>
                            <div style="margin-top:2px;font-size:12px;color:${colors.graphite}">Total del mes ${mxn(total)}</div>
                        </div>`;
                },
            },
        };
    }, [labels, timeline, colorFor, drawn, v2]);

    // Referentially stable, and that is what makes the chart move: a fresh
    // array on every parent render makes `ApexChart`'s memo miss, which lands
    // in react-apexcharts as an update — and an update repaints the columns
    // where a mount would have grown them.
    // v2: projected columns (the current month included) are the same colour
    // washed toward the page, so measured and simulated never look alike.
    const series = useMemo(
        () =>
            drawn.map((d) => ({
                name: d.label,
                data: v2
                    ? d.values.map((v, i) => ({
                          x: labels[i],
                          y: Math.round(v),
                          fillColor: i >= timeline.firstFutureIndex ? wash(d.color) : d.color,
                      }))
                    : d.values.map((v) => Math.round(v)),
            })),
        [drawn, v2, labels, timeline.firstFutureIndex]
    );

    if (!timeline.series.length) {
        return (
            <p className="py-10 text-center text-body text-graphite">
                Elige lo que sí o sí se cobra para dibujarlo.
            </p>
        );
    }

    return (
        <ApexChart
            key={`${drawn.map((d) => d.label).join("|")}·${timeline.months[0]}·${timeline.months.length}`}
            type="bar"
            series={series}
            options={options}
            height={height}
            ariaLabel={timelineHeadline(timeline) ?? undefined}
        />
    );
}

/**
 * The tooltip's month qualifier. The current month is where the projection
 * band starts, so it is already partly projected: what landed is measured,
 * the rest of the month is simulated.
 */
function monthState(index: number, firstFutureIndex: number): string {
    if (index === firstFutureIndex) return " · en curso · parte proyectada";
    return index > firstFutureIndex ? " · proyectado" : "";
}

/** A series colour 55% of the way to Paper — the projected column's fill,
 *  opaque so stacked layers do not show through each other. */
function wash(hex: string): string {
    const n = parseInt(hex.slice(1), 16);
    const ch = (c: number) => Math.round(c + (255 - c) * 0.55).toString(16).padStart(2, "0");
    return `#${ch((n >> 16) & 255)}${ch((n >> 8) & 255)}${ch(n & 255)}`;
}

/** Series labels are bank/user text landing in tooltip HTML. */
function escapeHtml(s: string): string {
    return s
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}
