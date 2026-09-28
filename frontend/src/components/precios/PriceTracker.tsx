"use client";

import { useMemo } from "react";
import type { ApexOptions } from "apexcharts";
import { chart, colors } from "@/design/tokens";
import { cn } from "@/lib/cn";
import { dayLabel, mxn2 } from "@/lib/format";
import { fromIso } from "@/lib/porMes";
import { basisLabel, type PricePoint, type ProductPrices } from "@/lib/prices";
import { ApexChart } from "@/components/charts/apex/ApexChart";

/** A purchase that can be drawn: it has a date and a comparable figure. */
type Plotted = {
    at: number;
    /** The date is the photo's, not the print's: the ticket had no legible one. */
    approx: boolean;
    value: number;
    point: PricePoint;
};

/**
 * When a purchase happened, as well as it can be known. The printed date
 * first; failing that the photo's timestamp, flagged so every place that
 * shows it can say "≈".
 */
export function pointDate(pt: PricePoint): { at: Date; approx: boolean } | null {
    if (pt.purchased_at) return { at: fromIso(pt.purchased_at), approx: false };
    if (pt.captured_at) {
        const at = new Date(pt.captured_at);
        if (!Number.isNaN(at.getTime())) return { at, approx: true };
    }
    return null;
}

/** "3 mar" or "≈ 3 mar". */
export function pointDateLabel(pt: PricePoint): string {
    const d = pointDate(pt);
    if (!d) return "fecha ilegible";
    return `${d.approx ? "≈ " : ""}${dayLabel(d.at)}`;
}

/**
 * What one product has cost you, purchase by purchase, drawn as a line.
 *
 * The book's row says the typical price and the spread; this is the shape
 * behind those two numbers — whether the product creeps up, jumps at one
 * store, or sits still. One series, so no legend: the row above names it.
 * The line is the one stone grey every chart here draws in, and hue is spent
 * on exactly two points, the cheapest and the dearest, because those are the
 * two purchases the reading is about. The typical price runs across as a
 * dashed rule, the same way the monthly mean does on Por mes.
 *
 * The x-axis is real time, not one slot per purchase: a price that held for
 * six months and then moved should look like six months, not like one step.
 * Purchases with no comparable figure (a line the reader could not size) are
 * left out of the line and stay in the list under it, which is the table view
 * of this chart.
 */
export function PriceTracker({
    product,
    points,
    height = 180,
    className,
}: {
    product: ProductPrices;
    points: PricePoint[];
    height?: number;
    className?: string;
}) {
    const basis = basisLabel(product);

    const plotted = useMemo<Plotted[]>(
        () =>
            points
                .flatMap((p) => {
                    const d = p.value === null ? null : pointDate(p);
                    return d ? [{ at: d.at.getTime(), approx: d.approx, value: p.value!, point: p }] : [];
                })
                .sort((a, b) => a.at - b.at),
        [points]
    );

    const extremes = useMemo(() => {
        if (plotted.length < 2) return null;
        let lo = 0;
        let hi = 0;
        plotted.forEach((p, i) => {
            if (p.value < plotted[lo].value) lo = i;
            if (p.value > plotted[hi].value) hi = i;
        });
        return { lo, hi };
    }, [plotted]);

    const options: ApexOptions = useMemo(
        () => ({
            chart: {
                toolbar: { show: false },
                zoom: { enabled: false },
                animations: { enabled: false },
            },
            colors: [chart.neutral[1]],
            stroke: { width: 2, curve: "straight" },
            // Every purchase is a mark, big enough to hover; the two the
            // reading is about are the only ones in colour, with a 2px Paper
            // ring so they sit on the line rather than in it.
            markers: {
                size: 4,
                strokeWidth: 2,
                strokeColors: colors.paper,
                hover: { size: 6 },
                discrete: extremes
                    ? [
                          {
                              seriesIndex: 0,
                              dataPointIndex: extremes.lo,
                              fillColor: colors.positive,
                              strokeColor: colors.paper,
                              size: 5,
                          },
                          {
                              seriesIndex: 0,
                              dataPointIndex: extremes.hi,
                              fillColor: colors.negative,
                              strokeColor: colors.paper,
                              size: 5,
                          },
                      ]
                    : [],
            },
            dataLabels: { enabled: false },
            legend: { show: false },
            xaxis: {
                type: "datetime",
                labels: {
                    formatter: (value: string) => dayLabel(new Date(Number(value))),
                    style: { colors: colors.graphite, fontSize: "11px" },
                    datetimeUTC: false,
                },
                axisTicks: { show: false },
                tooltip: { enabled: false },
            },
            yaxis: {
                forceNiceScale: true,
                labels: { formatter: (v: number) => mxn2(v) },
            },
            grid: {
                xaxis: { lines: { show: false } },
                yaxis: { lines: { show: true } },
                padding: { left: 4, right: 12 },
            },
            annotations:
                product.median !== null
                    ? {
                          yaxis: [
                              {
                                  y: product.median,
                                  strokeDashArray: 4,
                                  borderColor: colors.muted,
                                  label: {
                                      text: "típico",
                                      position: "right",
                                      textAnchor: "end",
                                      offsetY: -4,
                                      borderWidth: 0,
                                      style: {
                                          background: "transparent",
                                          color: colors.ash,
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
                    const p = plotted[dataPointIndex];
                    if (!p) return "";
                    const pt = p.point;
                    const size =
                        pt.size !== null && pt.size_unit ? ` · ${pt.size} ${pt.size_unit}` : "";
                    const qty = pt.quantity !== null && pt.quantity !== 1 ? ` · × ${pt.quantity}` : "";
                    return `
                        <div style="padding:8px 10px">
                            <div style="font-size:12px;color:${colors.graphite}">${p.approx ? "≈ " : ""}${dayLabel(new Date(p.at))} · ${pt.store ?? "tienda ilegible"}</div>
                            <div style="font-size:13px;color:${colors.ink};font-variant-numeric:tabular-nums">${mxn2(p.value)} ${basis}</div>
                            <div style="font-size:12px;color:${colors.graphite};font-variant-numeric:tabular-nums">${mxn2(pt.amount)}${size}${qty}</div>
                        </div>`;
                },
            },
        }),
        [plotted, extremes, product.median, basis]
    );

    const series = useMemo(
        () => [{ name: basis, data: plotted.map((p) => [p.at, p.value] as [number, number]) }],
        [plotted, basis]
    );

    if (plotted.length < 2) {
        return (
            <p className={cn("text-body-sm text-graphite", className)}>
                {plotted.length === 0
                    ? "Ninguna compra con precio comparable todavía."
                    : "Una sola compra con precio comparable; la línea aparece con la segunda."}
            </p>
        );
    }

    const lo = extremes ? plotted[extremes.lo] : null;
    const hi = extremes ? plotted[extremes.hi] : null;
    const last = plotted[plotted.length - 1];
    const anyApprox = plotted.some((p) => p.approx);

    return (
        <div className={className}>
            {/* The three figures the line is read for, said in words above it
                so the chart is never the only place they live. */}
            <dl className="mb-1 flex flex-wrap gap-x-5 gap-y-1 text-label">
                {lo && <Fact mark="bg-positive" label="Más barato" point={lo} basis={basis} />}
                {hi && <Fact mark="bg-negative" label="Más caro" point={hi} basis={basis} />}
                <Fact
                    mark="bg-graphite"
                    label="Última"
                    point={last}
                    basis={basis}
                    delta={product.latest_vs_median}
                />
            </dl>
            <ApexChart
                key={`${product.product_key}·${plotted.length}`}
                type="line"
                series={series}
                options={options}
                height={height}
            />
            {anyApprox && (
                <p className="mt-1 text-label text-ash">
                    ≈ fecha de la foto: ese ticket no traía una fecha legible.
                </p>
            )}
        </div>
    );
}

/** One of the chart's three facts: a coloured dot that matches its mark on
 *  the line, the word, then the figure in Ink. */
function Fact({
    mark,
    label,
    point,
    basis,
    delta,
}: {
    mark: string;
    label: string;
    point: Plotted;
    basis: string;
    /** The last purchase against the typical one, in %. */
    delta?: number | null;
}) {
    return (
        <div className="flex items-baseline gap-1.5">
            <span className={cn("inline-block h-2 w-2 shrink-0 rounded-full", mark)} aria-hidden />
            <dt className="text-graphite">{label}</dt>
            <dd className="tabular text-ink">
                {mxn2(point.value)} {basis}
                <span className="text-ash">
                    {" "}
                    · {point.approx ? "≈ " : ""}
                    {dayLabel(new Date(point.at))}
                    {point.point.store ? ` · ${point.point.store}` : ""}
                    {delta !== null && delta !== undefined && delta !== 0 && (
                        <span className={delta > 0 ? "text-negative" : "text-positive"}>
                            {" "}
                            ({delta > 0 ? "+" : ""}
                            {delta}% vs típico)
                        </span>
                    )}
                </span>
            </dd>
        </div>
    );
}
