"use client";

import { useMemo } from "react";
import type { ApexOptions } from "apexcharts";
import { chart, colors } from "@/design/tokens";
import { compactMxn, monthLabel, mxn } from "@/lib/format";
import { ApexChart } from "@/components/charts/apex/ApexChart";
import {
    monthKeyToDate,
    monthName,
    spansYears,
    type MonthSlice,
    type PartialMonth,
} from "@/lib/porMes";

/** "#78716c" at `alpha`, for one bar of a distributed series: Apex has no
 *  per-point opacity, but it does take any CSS colour per point. */
function withAlpha(hex: string, alpha: number): string {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/**
 * One column per calendar month, the mean as a dashed rule across them.
 *
 * Hue is not the month channel: every column is the one stone grey, and
 * Signal marks only the month whose lid is off in the list below — the same
 * rule the composition bar follows. A click on a column opens that month.
 *
 * No value over the columns. The exact figure is one row down in the list;
 * a number standing on every bar competes with the shape the chart is drawn
 * for, and the shape is the reading here.
 */
export function PorMesChart({
    months,
    average,
    openKey,
    onPick,
    height = 280,
    focusKey = null,
    partial = null,
    ariaLabel,
}: {
    months: MonthSlice[];
    average: number;
    openKey: string | null;
    onPick: (key: string) => void;
    height?: number;
    /** The month the title names, lit until the user opens another. */
    focusKey?: string | null;
    /** The running month, drawn faint and labelled "al {día}". */
    partial?: PartialMonth | null;
    /** The title's sentence, for screen readers. */
    ariaLabel?: string;
}) {
    const withYear = spansYears(months.map((m) => m.key));
    const labels = useMemo(
        () =>
            months.map((m) => {
                const label = monthLabel(monthKeyToDate(m.key), withYear);
                // A two-line category: the month, then how far into it the
                // record goes, so the short bar reads as unfinished, not low.
                return partial?.key === m.key ? [label, `al ${partial.day}`] : label;
            }),
        [months, withYear, partial]
    );
    // The user's pick, else the month the title is about.
    const litKey = openKey ?? focusKey;
    const litIndex = months.findIndex((m) => m.key === litKey);

    const options: ApexOptions = useMemo(
        () => ({
            chart: {
                toolbar: { show: false },
                events: {
                    dataPointSelection: (_e, _ctx, cfg: { dataPointIndex: number }) => {
                        const picked = months[cfg.dataPointIndex];
                        if (picked && picked.count > 0) onPick(picked.key);
                    },
                },
            },
            colors: months.map((m) =>
                m.key === litKey
                    ? colors.signal
                    : m.key === partial?.key
                      ? withAlpha(chart.neutral[3]!, 0.45)
                      : chart.neutral[3]!
            ),
            plotOptions: {
                bar: {
                    columnWidth: "58%",
                    borderRadius: 2,
                    distributed: true,
                    dataLabels: { position: "top" },
                },
            },
            stroke: { width: 0 },
            // The lit column carries its figure, so the selection is
            // not colour alone and the title's number is on the chart.
            dataLabels:
                litIndex >= 0
                    ? {
                          enabled: true,
                          formatter: (v: number, o: { dataPointIndex: number }) =>
                              o.dataPointIndex === litIndex ? mxn(v) : "",
                          offsetY: -20,
                          style: { colors: [colors.ink], fontSize: "12px", fontWeight: 500 },
                          background: { enabled: false },
                      }
                    : { enabled: false },
            legend: { show: false },
            xaxis: { categories: labels },
            yaxis: {
                min: 0,
                forceNiceScale: true,
                labels: { formatter: (v: number) => compactMxn(v) },
            },
            grid: { xaxis: { lines: { show: false } }, yaxis: { lines: { show: true } } },
            annotations:
                average > 0
                    ? {
                          yaxis: [
                              {
                                  y: average,
                                  strokeDashArray: 4,
                                  borderColor: colors.muted,
                                  label: {
                                      text: `promedio ${mxn(average)}`,
                                      position: "right",
                                      textAnchor: "end",
                                      offsetY: -4,
                                      borderWidth: 0,
                                      style: {
                                          background: "transparent",
                                          // Graphite: Ash is 2.4:1, too faint to read.
                                          color: colors.graphite,
                                          fontSize: "10px",
                                      },
                                  },
                              },
                          ],
                      }
                    : {},
            tooltip: {
                shared: false,
                intersect: true,
                custom: ({ dataPointIndex }) => {
                    const m = months[dataPointIndex];
                    if (!m) return "";
                    const name = monthName(m.key, withYear);
                    // Where the month sits against the mean, or why it
                    // is not compared at all.
                    let vs = "";
                    if (m.count > 0) {
                        if (partial?.key === m.key) vs = `al ${partial.day}, fuera del promedio`;
                        else if (average > 0) {
                            const d = Math.round(((m.amount - average) / average) * 100);
                            vs = `${d > 0 ? "+" : d < 0 ? "−" : ""}${Math.abs(d)}% vs promedio`;
                        }
                    }
                    const body =
                        m.count === 0
                            ? `<div style="font-size:13px;color:${colors.graphite}">Sin cargos</div>`
                            : `<div style="font-size:13px;color:${colors.ink};font-variant-numeric:tabular-nums">${mxn(m.amount)}</div>
                               <div style="font-size:12px;color:${colors.graphite};font-variant-numeric:tabular-nums">${m.count} cargo${m.count === 1 ? "" : "s"}</div>${
                                   vs
                                       ? `<div style="font-size:12px;color:${colors.graphite};font-variant-numeric:tabular-nums">${vs}</div>`
                                       : ""
                               }`;
                    return `
                        <div style="padding:8px 10px">
                            <div style="font-size:12px;color:${colors.graphite}">${name}</div>
                            ${body}
                        </div>`;
                },
            },
        }),
        [months, labels, average, litKey, litIndex, onPick, withYear, partial]
    );

    const series = useMemo(
        () => [{ name: "Cargos", data: months.map((m) => Math.round(m.amount)) }],
        [months]
    );

    return (
        <ApexChart
            key={`${months[0]?.key ?? ""}·${months.length}`}
            type="bar"
            series={series}
            options={options}
            height={height}
            ariaLabel={ariaLabel}
        />
    );
}
