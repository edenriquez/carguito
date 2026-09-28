"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export type FaceTab<K extends string> = {
    key: K;
    label: ReactNode;
    /** Tooltip on the tab; the label stays short. */
    title?: string;
};

/**
 * A strip of tabs whose selected mark *travels*.
 *
 * The mark is one element behind the labels, moved with a transform to sit
 * under whichever tab is selected. Switching tabs then reads as the same
 * object sliding from one word to the next, rather than one pill vanishing
 * and another appearing — the eye follows the motion to the new face, which
 * is the whole point of animating a menu.
 *
 * Measured with a layout effect, before paint: the mark is positioned in the
 * same frame the selection changes, so there is no frame where it sits under
 * the wrong word. On the very first render (server, or before the effect)
 * the selected tab paints its own background, so nothing is ever unmarked.
 *
 * Two tones: `dark` is the Movimientos strip (Soot mark, Paper text), `light`
 * is the Plan strip (Fog mark with a hairline ring).
 */
export function FaceTabs<K extends string>({
    tabs,
    value,
    onChange,
    label,
    tone = "dark",
    size = "sm",
    className,
}: {
    tabs: readonly FaceTab<K>[];
    value: K;
    onChange: (next: K) => void;
    /** The `aria-label` of the tablist. */
    label: string;
    tone?: "dark" | "light";
    size?: "sm" | "md";
    className?: string;
}) {
    const listRef = useRef<HTMLDivElement>(null);
    const [mark, setMark] = useState<{ left: number; width: number } | null>(null);
    // Whether the mark was already on screen at the last paint. Its first
    // appearance is placed, not slid: a strip that lives inside a hidden face
    // (Movimientos renders one per face) measures nothing while hidden, and
    // sliding in from the left edge when the face shows would be motion about
    // nothing.
    const wasMarked = useRef(false);
    useEffect(() => {
        wasMarked.current = mark !== null;
    }, [mark]);

    // Re-measured whenever the selection or the set of tabs changes, and on
    // resize: a label that wraps or a font that swaps moves every edge.
    useLayoutEffect(() => {
        const list = listRef.current;
        if (!list) return;
        const measure = () => {
            // Hidden (`display: none` up the tree): nothing to measure, and
            // the selected tab paints its own mark until there is.
            if (list.offsetWidth === 0) {
                setMark(null);
                return;
            }
            const el = list.querySelector<HTMLElement>(`[data-face="${CSS.escape(value)}"]`);
            if (!el) return;
            setMark({ left: el.offsetLeft, width: el.offsetWidth });
        };
        measure();
        const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
        ro?.observe(list);
        return () => ro?.disconnect();
    }, [value, tabs]);

    const dark = tone === "dark";
    const height = size === "sm" ? "h-8" : "h-9";

    return (
        <div
            ref={listRef}
            role="tablist"
            aria-label={label}
            className={cn(
                "relative inline-flex rounded-input border border-mist p-0.5",
                dark ? "bg-fog" : "bg-paper shadow-card",
                className
            )}
        >
            {mark && (
                <span
                    aria-hidden
                    className={cn(
                        "absolute left-0 top-0.5 rounded-[8px]",
                        wasMarked.current && "face-tabs-mark",
                        height,
                        dark ? "bg-soot" : "bg-fog ring-1 ring-inset ring-mist"
                    )}
                    style={{
                        width: mark.width,
                        // `offsetLeft` is measured from the list's padding
                        // edge, which is where `left-0` puts the mark.
                        transform: `translate3d(${mark.left}px, 0, 0)`,
                    }}
                />
            )}
            {tabs.map((tab) => {
                const selected = tab.key === value;
                return (
                    <button
                        key={tab.key}
                        type="button"
                        role="tab"
                        data-face={tab.key}
                        aria-selected={selected}
                        title={tab.title}
                        onClick={() => onChange(tab.key)}
                        className={cn(
                            "relative z-10 inline-flex items-center gap-2 rounded-[8px] transition-colors duration-150",
                            height,
                            size === "sm" ? "px-3.5 text-body-sm" : "px-4 text-body",
                            selected
                                ? cn("font-medium", dark ? "text-paper" : "text-ink")
                                : "text-graphite hover:text-ink",
                            // Until the mark has been measured, the selected
                            // tab paints its own background.
                            selected && !mark && (dark ? "bg-soot" : "bg-fog ring-1 ring-inset ring-mist")
                        )}
                    >
                        {tab.label}
                    </button>
                );
            })}
        </div>
    );
}
