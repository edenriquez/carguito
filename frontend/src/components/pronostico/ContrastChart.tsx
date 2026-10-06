"use client";

import { useMemo } from "react";
import type { ApexOptions } from "apexcharts";
import { colors, chart } from "@/design/tokens";
import { compactMxn, monthLabel, mxn } from "@/lib/format";
import { useChartsV2 } from "@/lib/chartsV2";
import { ApexChart } from "@/components/charts/apex/ApexChart";
import { monthKeyToDate } from "@/components/recurrentes/projection";

export const CONTRAST_COLORS = {
    nomina: colors.signal,
    extra: chart.signalTint[2]!,
    fijos: chart.neutral[1]!,
} as const;

export type ContrastSeries = {
    months: string[];
    firstFutureIndex: number;
    nomina: number[];
    extra: number[];
    fijos: number[];
};

/**
 * v2: what the chart is read for, in numbers — how many months the income
 * covers the fijos, and the average gap. Only measured months count: the
 * current one (its nómina may not have landed yet) and the projected ones are
 * not evidence of coverage. Months with nothing on either side are left out
 * too: an empty month is no evidence either. A deficit the projection shows
 * is named apart. Null when there is no month to count, so the caller falls
 * back to the metric's name.
 */
export function contrastFinding(data: ContrastSeries): {
    covered: number;
    counted: number;
    avgGap: number;
    /** Measured months in deficit — the only ones the chart marks. */
    deficits: number[];
    title: string;
} | null {
    let covered = 0;
    let counted = 0;
    let gapSum = 0;
    const deficits: number[] = [];
    let projectedDeficit = -1;
    data.months.forEach((_, i) => {
        const income = (data.nomina[i] ?? 0) + (data.extra[i] ?? 0);
        const fijos = data.fijos[i] ?? 0;
        if (income === 0 && fijos === 0) return;
        if (i >= data.firstFutureIndex) {
            if (i > data.firstFutureIndex && income < fijos && projectedDeficit < 0) {
                projectedDeficit = i;
            }
            return;
        }
        counted++;
        gapSum += income - fijos;
        if (income >= fijos) covered++;
        else deficits.push(i);
    });
    if (counted === 0) return null;
    const avgGap = gapSum / counted;
    const projected = data.months[projectedDeficit];
    const title =
        `Tus ingresos cubren tus fijos en ${covered} de ${counted} ${counted === 1 ? "mes" : "meses"}; ` +
        `en promedio ${avgGap >= 0 ? "sobran" : "faltan"} ${mxn(Math.abs(avgGap))} al mes` +
        (projected ? `; la proyección marca déficit en ${monthLabel(monthKeyToDate(projected), true)}` : "");
    return { covered, counted, avgGap, deficits, title };
}

/**
 * Grouped bars on one month axis: ingresos (nómina + extra stacked) against
 * the fijos total. No resto line — this chart is the contrast, not a load.
 *
 * v2: the fijos become a line over the stacked income, so the crossing is
 * read off one column instead of compared across two. Straight with markers,
 * not stepline: on a category axis a step lands between two bars and would
 * draw one month's fijos over the next month's income. Deficit months get a
 * negative marker and the first one is named on the chart.
 */
export function ContrastChart({
    data,
    height = 300,
}: {
    data: ContrastSeries;
    height?: number;
}) {
    const labels = useMemo(
        () => data.months.map((m) => monthLabel(monthKeyToDate(m), true)),
        [data.months]
    );

    const v2 = useChartsV2();
    const finding = useMemo(() => (v2 ? contrastFinding(data) : null), [v2, data]);

    const empty =
        data.nomina.every((v) => v === 0) &&
        data.extra.every((v) => v === 0) &&
        data.fijos.every((v) => v === 0);

    const options: ApexOptions = useMemo(() => {
        const firstFuture = labels[data.firstFutureIndex];
        const lastLabel = labels[labels.length - 1];
        const deficits = finding?.deficits ?? [];
        const firstDeficit = deficits[0];

        const projection: NonNullable<NonNullable<ApexOptions["annotations"]>["xaxis"]> =
            firstFuture && data.firstFutureIndex < labels.length
                ? [
                      {
                          x: firstFuture,
                          x2: lastLabel,
                          fillColor: colors.fog,
                          opacity: 0.75,
                          label: {
                              text: "Proyección",
                              position: "top",
                              orientation: "horizontal",
                              offsetY: -4,
                              style: {
                                  background: "transparent",
                                  color: v2 ? colors.graphite : colors.ash,
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
                  ]
                : [];

        const tooltip: ApexOptions["tooltip"] = {
            shared: true,
            intersect: false,
            custom: ({ dataPointIndex }) => {
                const i = dataPointIndex;
                const nomina = data.nomina[i] ?? 0;
                const extra = data.extra[i] ?? 0;
                const fijos = data.fijos[i] ?? 0;
                const ingresos = nomina + extra;
                const gap = ingresos - fijos;
                const gapRow = v2
                    ? `<div style="margin-top:2px;font-size:12px;font-variant-numeric:tabular-nums;color:${gap < 0 ? colors.negative : colors.ink}">${gap < 0 ? "Falta" : "Sobra"} ${mxn(Math.abs(gap))}</div>`
                    : "";
                return `
                    <div style="padding:8px 10px">
                        <div style="font-size:12px;color:${colors.graphite}">${escapeHtml(labels[i] ?? "")}</div>
                        ${row("Nómina", nomina, CONTRAST_COLORS.nomina)}
                        ${row("Extra", extra, CONTRAST_COLORS.extra)}
                        <div style="margin-top:2px;font-size:12px;color:${colors.graphite}">Ingresos ${mxn(ingresos)}</div>
                        ${row("Fijos", fijos, CONTRAST_COLORS.fijos)}
                        ${gapRow}
                    </div>`;
            },
        };

        if (v2) {
            return {
                chart: {
                    stacked: true,
                    stackOnlyBar: true,
                    toolbar: { show: false },
                    animations: { enabled: false },
                },
                colors: [CONTRAST_COLORS.nomina, CONTRAST_COLORS.extra, CONTRAST_COLORS.fijos],
                plotOptions: { bar: { columnWidth: "58%", borderRadius: 2 } },
                stroke: { width: [0, 0, 2], curve: "straight" },
                markers: {
                    size: [0, 0, 4],
                    strokeColors: colors.paper,
                    strokeWidth: 2,
                    hover: { size: 6 },
                    // A ring, not a fill: Negative is a text color, never a
                    // chart fill (tokens.ts).
                    discrete: deficits.map((i) => ({
                        seriesIndex: 2,
                        dataPointIndex: i,
                        fillColor: colors.paper,
                        strokeColor: colors.negative,
                        size: 5,
                    })),
                },
                dataLabels: { enabled: false },
                xaxis: {
                    categories: labels,
                    labels: { style: { colors: colors.graphite, fontSize: "12px" } },
                    axisTicks: { show: false },
                },
                yaxis: { labels: { formatter: (v: number) => compactMxn(v) } },
                grid: { xaxis: { lines: { show: false } }, yaxis: { lines: { show: true } } },
                legend: { show: false },
                annotations: {
                    xaxis: projection,
                    points:
                        firstDeficit !== undefined
                            ? [
                                  {
                                      x: labels[firstDeficit],
                                      y: Math.round(data.fijos[firstDeficit] ?? 0),
                                      marker: { size: 0 },
                                      label: {
                                          text: "primer mes en déficit",
                                          borderWidth: 0,
                                          offsetY: -6,
                                          style: {
                                              background: "transparent",
                                              color: colors.negative,
                                              fontSize: "11px",
                                          },
                                      },
                                  },
                              ]
                            : [],
                },
                tooltip,
            };
        }

        return {
            chart: {
                stacked: true,
                toolbar: { show: false },
                animations: { enabled: false },
            },
            colors: [CONTRAST_COLORS.nomina, CONTRAST_COLORS.extra, CONTRAST_COLORS.fijos],
            plotOptions: { bar: { columnWidth: "58%", borderRadius: 2 } },
            stroke: { width: 0 },
            dataLabels: { enabled: false },
            xaxis: {
                categories: labels,
                labels: { style: { colors: colors.graphite, fontSize: "12px" } },
                axisTicks: { show: false },
            },
            yaxis: { labels: { formatter: (v: number) => compactMxn(v) } },
            grid: { xaxis: { lines: { show: false } }, yaxis: { lines: { show: true } } },
            legend: { show: false },
            annotations: projection.length ? { xaxis: projection } : {},
            tooltip,
        };
    }, [labels, data, v2, finding]);

    if (empty) {
        return (
            <p className="py-10 text-center text-body text-graphite">
                Etiqueta un ingreso o fija un cargo para contrastarlos.
            </p>
        );
    }

    const series = v2
        ? [
              { name: "Nómina", type: "bar", data: data.nomina.map(round) },
              { name: "Extra", type: "bar", data: data.extra.map(round) },
              { name: "Fijos", type: "line", data: data.fijos.map(round) },
          ]
        : [
              { name: "Nómina", group: "Ingresos", data: data.nomina.map(round) },
              { name: "Extra", group: "Ingresos", data: data.extra.map(round) },
              { name: "Fijos", group: "Fijos", data: data.fijos.map(round) },
          ];

    return (
        <div>
            <ApexChart
                key={`${data.months[0]}·${data.months.length}·${data.firstFutureIndex}·${v2}`}
                type={v2 ? "line" : "bar"}
                series={series}
                options={options}
                height={height}
                ariaLabel={finding?.title}
            />
            <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-label text-graphite">
                <LegendSwatch color={CONTRAST_COLORS.nomina} label="Nómina" />
                <LegendSwatch color={CONTRAST_COLORS.extra} label="Extra" />
                {v2 ? (
                    <>
                        <li className="flex items-center gap-1.5">
                            <span
                                aria-hidden
                                className="h-0.5 w-3"
                                style={{ background: CONTRAST_COLORS.fijos }}
                            />
                            Fijos
                        </li>
                        {finding && finding.deficits.length > 0 && (
                            <LegendSwatch color={colors.negative} label="Mes en déficit" ring />
                        )}
                    </>
                ) : (
                    <LegendSwatch color={CONTRAST_COLORS.fijos} label="Fijos" />
                )}
            </ul>
        </div>
    );
}

function row(label: string, value: number, swatch: string): string {
    return `
        <div style="font-size:13px;color:${colors.ink};display:flex;align-items:center;gap:6px">
            <span style="width:8px;height:8px;border-radius:9999px;background:${swatch};display:inline-block"></span>
            <span>${label}</span>
            <span style="font-variant-numeric:tabular-nums">${mxn(value)}</span>
        </div>`;
}

function LegendSwatch({ color, label, ring }: { color: string; label: string; ring?: boolean }) {
    return (
        <li className="flex items-center gap-1.5">
            <span
                aria-hidden
                className="h-2 w-2 rounded-full"
                style={ring ? { boxShadow: `inset 0 0 0 1.5px ${color}` } : { background: color }}
            />
            {label}
        </li>
    );
}

function round(v: number): number {
    return Math.round(v);
}

function escapeHtml(s: string): string {
    return s
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}
