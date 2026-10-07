"use client";

import { useState, type CSSProperties } from "react";
import { cn } from "@/lib/cn";
import { mxn2 } from "@/lib/format";
import { barFill, pct, type CategorySlice } from "@/lib/categoryComposition";

/** How many categories the legend names before it stops. Past five the row
 *  wraps into a second line of dots that nobody reads, and the bar underneath
 *  already carries the rest — the count on the right says how many there are. */
const LEGEND_MAX = 5;

function midpoint(slices: CategorySlice[], key: string): number {
    let acc = 0;
    for (const s of slices) {
        if (s.key === key) return (acc + s.share / 2) * 100;
        acc += s.share;
    }
    return 50;
}

/**
 * The set's cargos as one bar: legend on top, the bar under it, the base it
 * is computed over at the foot.
 *
 * Three things the shape is saying:
 *
 * - **It is a bar, not a pill.** The rounded-full version read as a progress
 *   meter — something filling toward a goal. This is a partition of a whole,
 *   so it has square-ish ends and sits at the card's own radius.
 * - **Legend is name + percent, never an amount.** The amount appears once,
 *   on the pin over the open slice, so the bar never competes with the total
 *   stated in the header above it.
 * - **Without `colorOf`, hue is not the channel.** A basket of products has
 *   no colors of its own, so every slice is a step of the stone ramp ordered
 *   by size. Signal is the pointer and the page's subject, in
 *   that order: a slice turns Signal under the cursor, and the one the page is
 *   currently about keeps it plus a white inset ring, so hovering a neighbour
 *   never makes the open slice look closed. Hover is colour only — the click
 *   is the one thing that opens a category in the list below.
 *
 * With `colorOf` (category bars): a category is its taxonomy color here as
 * everywhere else. Focus fades the other slices instead of painting the focused one
 * Signal; the open slice carries an Ink ring.
 */
export function CompositionBar({
    slices,
    activeKey,
    onPick,
    countLabel = defaultCountLabel,
    label = "Composición del periodo por categoría",
    colorOf,
}: {
    slices: CategorySlice[];
    activeKey: string | null;
    onPick: (key: string) => void;
    /** The count at the legend's right end, in the caller's noun: the same
     *  bar partitions a period by category and a basket by product. */
    countLabel?: (n: number) => string;
    /** What the bar is a picture of, for assistive tech. */
    label?: string;
    /** Category bars only: each slice's own taxonomy color. The focused
     *  slice (pointed at or open) keeps it and gets an Ink outline; the rest
     *  fade. Absent — a basket of products — the stone ramp stands. */
    colorOf?: (slice: CategorySlice) => string;
}) {
    // Above the early return, where every hook has to be: a period with no
    // cargos is exactly the render that would change the hook order.
    //
    // The pointer outranks the click: while you are on a slice the pin states
    // *that* slice, and it falls back to the open one when you leave. Two pins
    // at once would need two gutters, and the question under the cursor is
    // always the more urgent of the two.
    const [hoverKey, setHoverKey] = useState<string | null>(null);

    if (slices.length === 0) return null;

    const named = slices.filter((s) => !s.uncategorized);
    // A gap worth more than a twentieth of the spend is part of the
    // reading, so the legend names it too — last, like the bar draws it.
    const gap = slices.find((s) => s.uncategorized && s.share > 0.05);
    const legend = [...named.slice(0, LEGEND_MAX), ...(gap ? [gap] : [])];
    // With nothing pointed at or open, the pin rests on the biggest slice
    // — the one the title names — so its figure is on screen without a hover.
    const restKey = named[0]?.key ?? null;
    const pinned = slices.find((s) => s.key === (hoverKey ?? activeKey ?? restKey)) ?? null;
    const pin = pinned ? midpoint(slices, pinned.key) : null;
    // Own colors: only a real focus fades the others — the resting pin on
    // the biggest slice is a label, not a selection.
    const own = colorOf;
    const focusKey = hoverKey ?? activeKey;
    const faded = (key: string) => focusKey !== null && key !== focusKey;

    return (
        <div>
            {/* The pin hangs in this gutter. It has to clear the legend
                above it at every width, including the one where a long
                category name has just wrapped the legend to a second line. */}
            <div className="relative mt-3 pt-9">
                {pinned && pin !== null && (
                    <div
                        className="pointer-events-none absolute top-0 z-10 flex -translate-x-1/2 flex-col items-center"
                        style={{ left: `${pin}%` }}
                    >
                        <div className="flex items-center gap-1.5 whitespace-nowrap rounded-input bg-soot px-2.5 py-1 text-label text-paper">
                            <span className="font-medium">{pinned.name}</span>
                            <span aria-hidden className="text-ash">
                                ·
                            </span>
                            <span className="tabular">{mxn2(pinned.amount)}</span>
                            <span aria-hidden className="text-ash">
                                ·
                            </span>
                            <span className="tabular text-signal">{pct(pinned.share)}%</span>
                        </div>
                        <span
                            aria-hidden
                            className="h-1.5 w-1.5 -translate-y-[3px] rotate-45 bg-soot"
                        />
                    </div>
                )}

                <div
                    className="flex h-10 overflow-hidden rounded-card bg-fog"
                    role="img"
                    aria-label={label}
                >
                    {slices.map((s, i) => {
                        const on = activeKey === s.key;
                        return (
                            <button
                                key={s.key}
                                type="button"
                                // `aria-label`, not `title`: the pin below is
                                // the tooltip now, and the browser's own would
                                // arrive a second later saying the same thing.
                                // But a slice has no text of its own, so
                                // without a label it would be a nameless
                                // button to a screen reader.
                                aria-label={`${s.name} · ${pct(s.share)}%`}
                                aria-pressed={on}
                                onClick={() => onPick(s.key)}
                                onPointerEnter={() => setHoverKey(s.key)}
                                onPointerLeave={() => setHoverKey((c) => (c === s.key ? null : c))}
                                // Focus too, so tabbing the bar reads the same
                                // as pointing at it.
                                onFocus={() => setHoverKey(s.key)}
                                onBlur={() => setHoverKey((c) => (c === s.key ? null : c))}
                                // The slice's own step of the ramp rides on a
                                // variable so hover can swap it for Signal as a
                                // class. An inline `background` would win over
                                // any class and there would be nothing to swap.
                                style={{
                                    flex: `0 0 ${Math.max(s.share * 100, s.share > 0 ? 0.8 : 0)}%`,
                                    "--seg": own ? own(s) : barFill(i, s.uncategorized, on),
                                    ...(own && faded(s.key) ? { opacity: 0.3 } : {}),
                                } as CSSProperties}
                                className={own ? cn(
                                    "h-full bg-[color:var(--seg)] transition-opacity duration-100",
                                    on && "ring-2 ring-inset ring-ink"
                                ) : cn(
                                    // Signal under the pointer, and nothing
                                    // else: pointing at a slice must not open
                                    // it. The click is what opens it, below.
                                    "h-full bg-[color:var(--seg)] transition-colors duration-100 hover:bg-signal",
                                    on && "ring-2 ring-inset ring-paper"
                                )}
                            />
                        );
                    })}
                </div>
            </div>
            <div className="flex items-start justify-between gap-4 mt-5">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-body-sm text-graphite">
                    {legend.map((s) => {
                        const on = activeKey === s.key;
                        const rank = named.indexOf(s);
                        return (
                            <button
                                key={s.key}
                                type="button"
                                onClick={() => onPick(s.key)}
                                onPointerEnter={() => setHoverKey(s.key)}
                                onPointerLeave={() => setHoverKey((c) => (c === s.key ? null : c))}
                                onFocus={() => setHoverKey(s.key)}
                                onBlur={() => setHoverKey((c) => (c === s.key ? null : c))}
                                style={{
                                    "--dot": own ? own(s) : barFill(rank, s.uncategorized, on),
                                } as CSSProperties}
                                className={cn(
                                    "group inline-flex items-center gap-1.5 transition-colors duration-100",
                                    on ? "font-medium text-ink" : "hover:text-ink"
                                )}
                            >
                                {/* The legend opens the same category the bar
                                    does, so it answers the pointer the same
                                    way. A grey dot beside a name that is
                                    already darkening would read as a dead
                                    control. */}
                                <span
                                    aria-hidden
                                    className={cn(
                                        "h-2 w-2 shrink-0 rounded-full bg-[color:var(--dot)]",
                                        own
                                            ? cn("transition-opacity duration-100", faded(s.key) && "opacity-30")
                                            : "transition-colors duration-100 group-hover:bg-signal"
                                    )}
                                />
                                <span className="whitespace-nowrap">
                                    {s.name} <span className="tabular">{pct(s.share)}%</span>
                                </span>
                            </button>
                        );
                    })}
                </div>
                <span className="tabular hidden shrink-0 text-label text-ash sm:inline">
                    {countLabel(slices.length)}
                </span>
            </div>
        </div>
    );
}

function defaultCountLabel(n: number): string {
    return `${n} categoría${n === 1 ? "" : "s"} activa${n === 1 ? "" : "s"}`;
}
