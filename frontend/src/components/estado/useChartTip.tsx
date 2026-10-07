"use client";

import { useCallback, useEffect, useRef, useState, type FocusEvent, type PointerEvent } from "react";

/**
 * One small ink tooltip per chart, positioned inside the chart's own box so it
 * scrolls with it. `bind(text)` returns the handlers for a mark.
 *
 * The same tip opens on touch and on keyboard focus (each bound mark becomes
 * a tab stop unless `focusable` is false), a tap outside the chart closes it,
 * and the box carries `--lx-fs`: how much the SVG text has to grow so an
 * 11-unit label in a 600-wide viewBox still reads as ~11px on a phone. `TEXT`
 * reads that variable.
 */
export function useChartTip() {
    const box = useRef<HTMLDivElement>(null);
    const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);

    useEffect(() => {
        const el = box.current;
        if (!el) return;
        const measure = () => {
            const w = el.getBoundingClientRect().width;
            // Capped at 18 units: past that the labels of the denser charts
            // (ten deciles, 31 days) would run into each other.
            if (w > 0) el.style.setProperty("--lx-fs", String(Math.min(18 / 11, Math.max(1, 600 / w))));
        };
        measure();
        const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
        ro?.observe(el);
        return () => {
            ro?.disconnect();
            el.style.removeProperty("--lx-fs");
        };
    }, []);

    // A tap anywhere outside the chart closes a tip a tap opened.
    useEffect(() => {
        if (!tip) return;
        const close = (e: Event) => {
            if (!box.current?.contains(e.target as Node)) setTip(null);
        };
        document.addEventListener("pointerdown", close);
        return () => document.removeEventListener("pointerdown", close);
    }, [tip]);

    const bind = useCallback(
        (text: string, focusable = true) => {
            const at = (e: PointerEvent) => {
                const r = box.current?.getBoundingClientRect();
                if (!r) return;
                setTip({ x: e.clientX - r.left, y: e.clientY - r.top, text });
            };
            return {
                onPointerDown: at,
                onPointerMove: at,
                // A finger lifting fires a leave too; only the mouse closes on it.
                onPointerLeave: (e: PointerEvent) => {
                    if (e.pointerType === "mouse") setTip(null);
                },
                ...(focusable && {
                    tabIndex: 0,
                    onFocus: (e: FocusEvent<Element>) => {
                        const r = box.current?.getBoundingClientRect();
                        const m = e.currentTarget.getBoundingClientRect();
                        if (!r) return;
                        setTip({ x: m.left + m.width / 2 - r.left, y: m.top + m.height / 2 - r.top, text });
                    },
                    onBlur: () => setTip(null),
                }),
            };
        },
        []
    );

    const node = tip ? (
        <div
            role="status"
            className="pointer-events-none absolute z-10 -translate-x-1/2 whitespace-nowrap rounded-control bg-soot px-2 py-1 text-label text-paper tabular"
            style={{ left: tip.x, top: tip.y - 36 }}
        >
            {tip.text}
        </div>
    ) : null;

    return { box, bind, node };
}
