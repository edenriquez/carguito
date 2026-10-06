"use client";

import dynamic from "next/dynamic";
import { memo, useMemo, useState } from "react";
import type { ApexOptions } from "apexcharts";
import { ChartSkeleton } from "@/components/ui";
import { useChartsV2 } from "@/lib/chartsV2";
import { baseOptions } from "./theme";

/**
 * ApexCharts touches `window` at import time, so `ssr: false` is load-bearing,
 * not a nicety — a static import fails `next build` during prerender. One
 * wrapper means one shared chunk instead of one per chart. The runtime behind
 * it drives Apex directly; see `ApexRuntime` for why not react-apexcharts.
 */
const ApexRuntime = dynamic(() => import("./ApexRuntime"), { ssr: false });

type Plain = Record<string, unknown>;

function isPlainObject(v: unknown): v is Plain {
    return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Apex options nest three levels deep (`chart.toolbar.show`,
 * `xaxis.labels.style.colors`). A shallow spread silently drops every theme
 * key under any branch the caller also sets, so `{ xaxis: { categories } }`
 * would wipe the axis styling. Arrays replace rather than merge — a caller
 * passing `colors: [...]` means those colours, not those plus ours.
 */
export function deepMerge<T extends Plain>(base: T, override: Plain): T {
    const out: Plain = { ...base };
    for (const [key, value] of Object.entries(override)) {
        if (value === undefined) continue;
        const current = out[key];
        out[key] = isPlainObject(current) && isPlainObject(value)
            ? deepMerge(current, value)
            : value;
    }
    return out as T;
}

export type ApexChartProps = {
    type: NonNullable<ApexOptions["chart"]>["type"];
    series: ApexOptions["series"];
    /** Deep-merged over `baseOptions`; you only declare the differences. */
    options?: ApexOptions;
    height?: number | string;
    width?: number | string;
    className?: string;
    /** What the chart says, for screen readers (v2): the finding, not "gráfica". */
    ariaLabel?: string;
};

/**
 * Memoized on props identity, and that is load-bearing: the runtime pushes an
 * update to Apex for every new `options`/`series` object it is handed, and an
 * update tears down and redraws the chart's internals — so a parent re-render
 * during a drag-selection gesture (the selection handler setting state IS such
 * a re-render) would destroy the gridRect a pending debounce timer still
 * points at. Callers keep `options` and `series` referentially stable via
 * useMemo; this memo turns that stability into "Apex is not touched at all".
 */
export const ApexChart = memo(ApexChartInner);

function ApexChartInner({
    type,
    series,
    options,
    height = 320,
    width = "100%",
    className,
    ariaLabel,
}: ApexChartProps) {
    // The placeholder is this component's, not `next/dynamic`'s, because only
    // here is the chart's height known: a 320px default standing in for a
    // 280px chart is a 40px jump the moment the real one lands.
    const [ready, setReady] = useState(false);

    const v2 = useChartsV2();
    const merged = useMemo(() => {
        const out = deepMerge(baseOptions as Plain, {
            ...(options as Plain),
            chart: { ...((options?.chart ?? {}) as Plain), type },
        }) as ApexOptions;
        // v2: Apex animates from JS, so the CSS media query never reaches it.
        if (v2 && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            out.chart = { ...out.chart, animations: { enabled: false } };
        }
        return out;
    }, [options, type, v2]);

    const reserved = typeof height === "number" ? height : undefined;

    return (
        // The placeholder overlays rather than stacks: for one frame after Apex
        // draws, both are mounted, and a skeleton that took its own row would
        // make the card twice as tall for exactly that frame.
        <div
            style={{ position: "relative", minWidth: 0, minHeight: reserved }}
            role={v2 && ariaLabel ? "img" : undefined}
            aria-label={v2 ? ariaLabel : undefined}
        >
            {!ready && (
                <div className="absolute inset-0" aria-hidden>
                    <ChartSkeleton height={reserved ?? 320} />
                </div>
            )}
            <ApexRuntime
                type={type}
                options={merged}
                series={series}
                height={height}
                width={width}
                className={className}
                onReady={() => setReady(true)}
            />
        </div>
    );
}
