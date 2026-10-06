"use client";

import { useMemo } from "react";
import type { ApexOptions } from "apexcharts";
import { ApexChart } from "@/components/charts/apex/ApexChart";
import { colors } from "@/design/tokens";
import { useChartsV2 } from "@/lib/chartsV2";
import { compactMxn, monthLabel, mxn } from "@/lib/format";
import { num, parsePeriodKey, type MetricRow } from "@/lib/metrics";

export type MonthPoint = { key: string; label: string; total: number };

/**
 * The set's spend per month, with the scenario laid over it.
 *
 * The scenario is a dotted line on *this* chart rather than a second chart
 * beside it. Two charts is the tempting layout and the wrong one: it creates
 * two sources of truth that can fall out of step, which is exactly what
 * MovimientosView avoids by feeding its scatter and its list from one array.
 * Here the bar is what happened and the line is what you asked about, and the
 * difference between them is a distance you can see rather than a subtraction
 * you have to do.
 *
 * Colour follows the same reasoning: the accent marks the *hypothesis*. The
 * real figure is the neutral stone ramp — data does not need to be pointed at.
 */
export function CohortChart({
    points,
    scenarioMonthly,
    title,
}: {
    points: MonthPoint[];
    /** The scenario's monthly cost, or `null` when no scenario is set. */
    scenarioMonthly: number | null;
    /** v2: overrides the computed headline. */
    title?: string;
}) {
    const v2 = useChartsV2();
    const read = useMemo(() => readPoints(points), [points]);
    const headline = title ?? cohortHeadline(points, read, scenarioMonthly);

    const v2Options = useMemo<ApexOptions>(() => {
        const { average, partial } = read;
        return {
            chart: { stacked: false, toolbar: { show: false } },
            colors: [colors.ash, colors.signal],
            stroke: { width: [0, 2], dashArray: [0, 6], curve: "straight" },
            plotOptions: { bar: { columnWidth: "52%", borderRadius: 2 } },
            xaxis: { categories: points.map((p) => p.label) },
            yaxis: { labels: { formatter: (v: number) => compactMxn(v) } },
            legend: { show: scenarioMonthly !== null },
            markers: { size: 0 },
            // Without a scenario the reference is your own average over the
            // complete months — the level the headline quotes.
            annotations:
                scenarioMonthly === null && average !== null
                    ? {
                          yaxis: [
                              {
                                  y: average,
                                  strokeDashArray: 3,
                                  borderColor: colors.graphite,
                                  label: {
                                      text: `promedio ${mxn(average)}`,
                                      position: "left",
                                      textAnchor: "start",
                                      offsetX: 4,
                                      style: { background: colors.paper, color: colors.graphite },
                                      borderWidth: 0,
                                  },
                              },
                          ],
                          points:
                              partial !== null
                                  ? [
                                        {
                                            x: points[partial]?.label,
                                            y: points[partial]?.total ?? 0,
                                            marker: { size: 0 },
                                            label: {
                                                text: `al ${new Date().getDate()}`,
                                                style: { background: "transparent", color: colors.graphite },
                                                borderWidth: 0,
                                            },
                                        },
                                    ]
                                  : [],
                      }
                    : {},
            tooltip: {
                shared: true,
                intersect: false,
                custom: ({ dataPointIndex }: { dataPointIndex: number }) => {
                    const p = points[dataPointIndex];
                    if (!p) return "";
                    const prev = points[dataPointIndex - 1];
                    const extra = [
                        dataPointIndex === partial ? `mes en curso, al ${new Date().getDate()}` : null,
                        prev ? `vs ${prev.label}: ${signed(p.total - prev.total)}` : null,
                        scenarioMonthly !== null ? `vs escenario: ${signed(p.total - scenarioMonthly)}` : null,
                    ].filter(Boolean);
                    return `
                        <div style="padding:8px 10px">
                            <div style="font-size:12px;color:${colors.graphite}">${p.label}</div>
                            <div style="font-size:13px;color:${colors.ink};font-variant-numeric:tabular-nums">${mxn(p.total)}</div>
                            ${extra.map((t) => `<div style="font-size:12px;color:${colors.graphite};font-variant-numeric:tabular-nums">${t}</div>`).join("")}
                        </div>`;
                },
            },
        };
    }, [points, scenarioMonthly, read]);

    const options = useMemo<ApexOptions>(
        () => ({
            chart: { stacked: false, toolbar: { show: false } },
            // The bar is the real spend; the line is the hypothesis.
            colors: [colors.ash, colors.signal],
            stroke: {
                width: [0, 2],
                dashArray: [0, 6],
                curve: "straight",
            },
            plotOptions: { bar: { columnWidth: "52%", borderRadius: 2 } },
            xaxis: { categories: points.map((p) => p.label) },
            yaxis: { labels: { formatter: (v: number) => compactMxn(v) } },
            tooltip: { y: { formatter: (v: number) => mxn(v) } },
            legend: { show: scenarioMonthly !== null },
            markers: { size: 0 },
        }),
        [points, scenarioMonthly]
    );

    const series = useMemo(() => {
        const actual = {
            name: "Como vas",
            type: "column",
            data: v2
                ? points.map((p, i) => ({
                      x: p.label,
                      y: p.total,
                      // Focus without a click: the last complete month in
                      // Ink, the rest Ash, the month still running washed back (Muted is
                      // Ash at ~0.45 on Paper, opaque).
                      fillColor:
                          i === read.focus ? colors.ink : i === read.partial ? colors.muted : colors.ash,
                  }))
                : points.map((p) => p.total),
        };
        if (scenarioMonthly === null) return [actual];
        return [
            actual,
            {
                name: "Escenario",
                type: "line",
                // A flat line across every month: the scenario is "this much,
                // every month", and drawing it as a constant is what makes the
                // gap against each real bar legible at a glance.
                data: points.map(() => scenarioMonthly),
            },
        ];
    }, [points, scenarioMonthly, v2, read]);

    return (
        // min-w-0 is not optional: a CSS grid item defaults to min-width:auto
        // and an Apex SVG inside one will not shrink below its first render
        // width, so the page overflows the moment the window narrows.
        <div className="min-w-0">
            {v2 && headline && <p className="mb-3 text-body font-medium text-ink">{headline}</p>}
            <ApexChart
                type="line"
                series={series}
                options={v2 ? v2Options : options}
                height={260}
                ariaLabel={headline ?? undefined}
            />
        </div>
    );
}

type CohortRead = {
    /** Mean of the complete months, or `null` with none. */
    average: number | null;
    /** The last complete month — the bar the headline is about. */
    focus: number | null;
    /** The month still running, kept out of the average. */
    partial: number | null;
};

/**
 * The only partial month this chart can know is the calendar's current one:
 * the rows carry a month, not the last day with data.
 */
function readPoints(points: MonthPoint[]): CohortRead {
    const now = new Date();
    const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const last = points.length - 1;
    const partial = last >= 0 && points[last]!.key.startsWith(current) ? last : null;
    const complete = partial === null ? points : points.slice(0, -1);
    const average = complete.length
        ? complete.reduce((s, p) => s + p.total, 0) / complete.length
        : null;
    return { average, focus: complete.length ? complete.length - 1 : null, partial };
}

function cohortHeadline(
    points: MonthPoint[],
    read: CohortRead,
    scenarioMonthly: number | null
): string | null {
    const { average, focus } = read;
    if (average === null || focus === null) return null;
    if (scenarioMonthly !== null) {
        const diff = scenarioMonthly - average;
        return `Tu escenario costaría ${mxn(scenarioMonthly)} al mes: ${mxn(Math.abs(diff))} ${diff <= 0 ? "menos" : "más"} que lo que gastas`;
    }
    const head = `Gastas ${mxn(average)} al mes en promedio`;
    const last = points[focus]!.total;
    const prev = focus > 0 ? points[focus - 1]!.total : 0;
    if (prev <= 0) return `${head}; el último mes, ${mxn(last)}`;
    const pct = Math.round(((last - prev) / prev) * 100);
    return `${head}; el último mes ${mxn(last)} (${pct >= 0 ? "+" : "−"}${Math.abs(pct)}% vs el anterior)`;
}

function signed(v: number): string {
    return `${v >= 0 ? "+" : "−"}${mxn(Math.abs(v))}`;
}

/** `cohort_activity` month rows -> chart points, oldest first. */
export function toMonthPoints(rows: MetricRow[] | undefined): MonthPoint[] {
    if (!rows) return [];
    return rows
        .map((row) => {
            const key = String(row.month ?? "");
            const parsed = parsePeriodKey(key);
            return {
                key,
                label: parsed ? monthLabel(parsed) : key,
                total: num(row.expense_amount),
            };
        })
        .filter((p) => p.key)
        .sort((a, b) => a.key.localeCompare(b.key));
}
