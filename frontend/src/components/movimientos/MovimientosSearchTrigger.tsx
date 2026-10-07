"use client";

import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { categoryName, useCategories } from "@/lib/categories";
import {
    clearChip,
    EMPTY_QUERY,
    queryChips,
} from "@/lib/movimientosQuery";
import { useMovimientosSearch } from "./MovimientosSearchProvider";

/**
 * The header's search bar. A real input, not a button dressed as one.
 *
 * It used to be a button whose whole job was to open the dialog, and the
 * docstring defended that: "not a search field pretending to be a filter."
 * The dialog is still where results live — a 1200px header has nowhere to put
 * them — but the handover now happens on the first keystroke rather than on a
 * click, so what you typed is the search the dialog opens on. That is the part
 * that was not functional before: you pressed a button and then typed again.
 *
 * Three things the shape has to get right:
 *
 * - **⌘K is a flex sibling, not an overlay.** It sits at the trailing edge and
 *   the input is `flex-1` beside it, so the field's own box ends where the key
 *   begins and typed text can never run underneath it. An absolutely
 *   positioned key would need a hard-coded `pr-*` that goes wrong the moment
 *   the label changes.
 * - **Glass, which means genuinely translucent.** `bg-paper/70` over a blur
 *   rather than an opaque near-white: the bar samples the canvas instead of
 *   covering it.
 * - **It is the tallest thing in the header, on purpose.** `h-11` against the
 *   `h-9` of Pagos and Documentos. An earlier pass argued the opposite — that
 *   matching its siblings was what kept it from reading as a banner — and that
 *   was the right call for a button. This is the way into the ledger, so it
 *   outranks the nav rather than sitting level with it.
 * - **Four properties animate, and none of them is a bevel.** Width, shadow,
 *   glass opacity, hairline. The shadow carries the focus state: `fieldFocus`
 *   adds a 4px halo of the accent that grows out of nothing, which is the
 *   modern version of the job a hard ring does. Easing is expo-out — fast
 *   away from rest, long settle — so the growth reads as motion rather than a
 *   step. Skipped entirely under `prefers-reduced-motion`: a box that changes
 *   size is exactly what that setting is asking us not to do.
 *
 * And focus alone opens nothing, so all of that plays on a bar the user is
 * still looking at rather than behind the dialog — see `handOff`.
 */
export function MovimientosSearchTrigger() {
    const { open, openModal } = useMovimientosSearch();
    const [text, setText] = useState("");
    const shortcut = isApple() ? "⌘K" : "Ctrl K";

    // The dialog owns the query once it is open, and it keeps its own field.
    // Holding stale text here would show two different searches at once.
    useEffect(() => {
        if (!open) setText("");
    }, [open]);

    /**
     * The first keystroke opens the dialog, seeded with what was typed, and
     * its own field takes over from there.
     *
     * Deliberately the *keystroke* and not focus or a click. Two reasons, and
     * both are load-bearing:
     *
     * - `useOverlay` restores focus to whatever was focused before the dialog
     *   opened, which is this input. Opening on focus would mean closing the
     *   dialog re-focuses the bar, which reopens the dialog, forever.
     * - The focus animation belongs to a bar that still has focus. If the
     *   dialog took over the moment you arrived, the one thing that was asked
     *   for would play behind an overlay.
     *
     * So focus is quiet: the bar grows and waits. Typing is what commits.
     */
    function handOff(next: string) {
        setText(next);
        if (next.trim()) openModal("bar", { ...EMPTY_QUERY, needle: next });
    }

    return (
        <div
            className={cn(
                "group relative flex h-11 items-center gap-2.5 rounded-control pl-4 pr-2.5",
                // Glass: translucent over a blur, with a hairline to hold the
                // edge that the translucency gives up.
                "border border-mist bg-paper/70 backdrop-blur-xl backdrop-saturate-150",
                "shadow-field",
                // Full width on a phone, where it gets a row of its own out of
                // the header's wrap rather than fighting the nav for 320px.
                // 24rem at rest, 32.5rem focused: both 20% over the old
                // 20/27, so the focus still grows it by the same proportion.
                "w-full sm:w-[24rem] sm:focus-within:w-[32.5rem]",
                "transition-[width,box-shadow,background-color,border-color]",
                "duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
                "hover:border-muted",
                "focus-within:border-signal focus-within:bg-paper/90 focus-within:shadow-fieldFocus",
                "focus-within:hover:border-signal",
                // A box that resizes is the one thing this setting is about.
                // The halo and the hairline still change — those are state, not
                // movement — but the width lands at its focused value.
                "motion-reduce:sm:w-[32.5rem] motion-reduce:transition-none"
            )}
        >
            <Search
                size={17}
                strokeWidth={1.75}
                aria-hidden
                className={cn(
                    "shrink-0 text-ash transition-colors duration-300",
                    "group-focus-within:text-edge"
                )}
            />

            <input
                type="search"
                value={text}
                onChange={(e) => handOff(e.target.value)}
                // Enter with nothing typed is "show me everything", which is
                // the browse-rather-than-type way in.
                onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    e.preventDefault();
                    openModal("bar", text.trim() ? { ...EMPTY_QUERY, needle: text } : undefined);
                }}
                placeholder="Buscar movimientos"
                aria-label="Buscar movimientos"
                aria-keyshortcuts={isApple() ? "Meta+K" : "Control+K"}
                className={cn(
                    // 16px, up from 14: the field leads the header, and it is
                    // also the one input here that gets typed into on a phone,
                    // where anything under 16px makes iOS Safari zoom the page.
                    "min-w-0 flex-1 bg-transparent text-body-lg text-ink outline-none",
                    "placeholder:text-ash",
                    "[&::-webkit-search-cancel-button]:hidden"
                )}
            />

            <kbd
                className={cn(
                    // Always on, at every width: it is the fastest way in and
                    // hiding it on the sizes where typing is hardest is
                    // backwards.
                    "pointer-events-none shrink-0 rounded-[5px] bg-fog px-1.5 py-0.5",
                    "font-sans text-label font-medium text-graphite"
                )}
            >
                {shortcut}
            </kbd>
        </div>
    );
}

export function MovimientosQueryChips() {
    const { query, setQuery } = useMovimientosSearch();
    const categories = useCategories();
    const chips = queryChips(query, (id) => categoryName(categories, id));
    if (chips.length === 0) return null;

    return (
        <div className="-mt-4 flex flex-wrap items-center gap-1.5 pb-5">
            {chips.map((chip) => (
                <span
                    key={chip.key}
                    className="inline-flex items-center gap-1 rounded-tag bg-fog py-0.5 pl-2 pr-1 text-label text-ink ring-1 ring-inset ring-mist"
                >
                    {chip.label}
                    <button
                        type="button"
                        aria-label={`Quitar ${chip.label}`}
                        onClick={() => setQuery(clearChip(query, chip))}
                        className="rounded-full p-0.5 text-ash hover:text-ink"
                    >
                        <X size={12} aria-hidden />
                    </button>
                </span>
            ))}
            <button
                type="button"
                onClick={() => setQuery(EMPTY_QUERY)}
                className="rounded-control px-1.5 py-0.5 text-label text-graphite underline decoration-mist underline-offset-4 hover:text-ink"
            >
                Quitar criterios
            </button>
        </div>
    );
}

function isApple(): boolean {
    if (typeof navigator === "undefined") return true;
    return /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
}
