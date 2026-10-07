"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { LensCallout } from "./LensCallout";
import { useLensAnnotations, type AppliedAnchor } from "./useLensAnnotations";
import type { Lectura, LensFocus, LensGroup } from "./types";

/**
 * Wraps any Apex chart and lends it a focus: the lectura in focus gets a
 * pulsing ring on its mark and a callout beside it; everything else recedes.
 * Sibling of `RangeBrush` — an overlay that reads the chart's DOM and never
 * writes to its options.
 *
 * The ring is an Apex point annotation (see useLensAnnotations); the callout
 * is HTML positioned over that ring's `getBoundingClientRect()`, so both stay
 * on the mark through resizes and remounts.
 */
export function ChartLens({
    groups,
    focus,
    onFocus,
    actions,
    reducedMotion = false,
    className,
    children,
}: {
    groups: LensGroup[];
    focus: LensFocus;
    onFocus: (next: LensFocus) => void;
    /** Actions for the callout of the focused lectura (Ver, Es mío…). */
    actions?: (lectura: Lectura) => ReactNode;
    /** Force the reduced-motion presentation (dev preview toggle). */
    reducedMotion?: boolean;
    className?: string;
    children: ReactNode;
}) {
    const rootRef = useRef<HTMLDivElement>(null);
    // The OS setting reduces motion too, not only the dev toggle. Read
    // after mount — there is no matchMedia on the server.
    const [osReduced, setOsReduced] = useState(false);
    useEffect(() => {
        const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
        setOsReduced(mq.matches);
        const onChange = () => setOsReduced(mq.matches);
        mq.addEventListener("change", onChange);
        return () => mq.removeEventListener("change", onChange);
    }, []);
    const reduced = reducedMotion || osReduced;

    const focused: Lectura | null = useMemo(() => {
        if (!focus) return null;
        const g = groups.find((x) => x.id === focus.groupId);
        return g?.lecturas[focus.index] ?? null;
    }, [groups, focus]);

    // Only the focused lectura gets a ring: one emphasis per chart.
    const rings = useMemo(() => (focused ? [focused] : []), [focused]);

    const [callout, setCallout] = useState<{ style: CSSProperties; below: boolean } | null>(null);

    const onApplied = useCallback((applied: AppliedAnchor[]) => {
        const root = rootRef.current;
        const node = applied[0]?.node;
        if (!root || !node) {
            setCallout(null);
            return;
        }
        const r = root.getBoundingClientRect();
        const m = node.getBoundingClientRect();
        const cx = m.left - r.left + m.width / 2;
        const cy = m.top - r.top + m.height / 2;
        // A mark outside the plot (zoomed away, or a category not on the
        // axis) has nothing to point at: no callout, the chip still says
        // the lectura exists.
        const grid = root.querySelector(".apexcharts-grid")?.getBoundingClientRect();
        if (grid) {
            const inside =
                m.left + m.width / 2 >= grid.left - 2 &&
                m.left + m.width / 2 <= grid.right + 2 &&
                m.top + m.height / 2 >= grid.top - 2 &&
                m.top + m.height / 2 <= grid.bottom + 2;
            if (!inside) {
                setCallout(null);
                return;
            }
        }
        const below = cy < 96;
        // Keep the card inside the wrapper horizontally.
        const left = Math.min(Math.max(cx, 130), Math.max(130, r.width - 130));
        setCallout({
            style: below
                ? { left, top: cy + 14, transform: "translateX(-50%)" }
                : { left, top: cy - 14, transform: "translate(-50%, -100%)" },
            below,
        });
    }, []);

    useLensAnnotations(rootRef, rings, onApplied);

    // Esc lets go of the focus, the way it closes a sheet.
    useEffect(() => {
        if (!focus) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onFocus(null);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [focus, onFocus]);

    const keep = focused?.anchor.seriesIndex;

    return (
        <div
            ref={rootRef}
            className={cn("lens relative", focused && "lens-active", reduced && "lens-reduced", className)}
            style={keep !== undefined ? ({ "--lens-keep": String(keep + 1) } as CSSProperties) : undefined}
            data-lens-keep={keep !== undefined ? keep + 1 : undefined}
        >
            {children}
            {focused && callout && (
                <LensCallout
                    lectura={focused}
                    style={callout.style}
                    below={callout.below}
                    actions={actions?.(focused)}
                />
            )}
        </div>
    );
}
