"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { mxn } from "@/lib/format";

export type CategoryChip = {
    name: string;
    color: string;
    amount: number;
    /** v2: another category has the focus, so this swatch steps back. */
    faded?: boolean;
};

/**
 * The chips that say which slice of the period the list below is showing.
 *
 * They are the same choice the chart offers by click, in a form you can read
 * without hunting a layer — and, unlike the chart, they name what is currently
 * active. A filter you can't see is a filter you will forget you set.
 *
 * Chips are ordered by spend (the stack's own order), so the first one is the
 * category most worth opening.
 */
export function CategoryFilterBar({
    chips,
    picked,
    onPick,
    month,
    monthLabel,
    onClearMonth,
    onHover,
}: {
    chips: CategoryChip[];
    /** Category names in the set, empty for "todas". */
    picked: string[];
    onPick: (name: string | null) => void;
    month: string | null;
    monthLabel?: string;
    onClearMonth: () => void;
    /** v2: a chip under the pointer (or keyboard focus) lights its layer in
     *  the chart; null when it leaves. Absent in v1. */
    onHover?: (name: string | null) => void;
}) {
    return (
        <div className="flex flex-wrap items-center gap-1.5">
            <button
                type="button"
                aria-pressed={picked.length === 0}
                onClick={() => onPick(null)}
                className={cn(
                    CHIP,
                    picked.length === 0
                        ? "bg-soot font-medium text-paper"
                        : "border border-mist text-graphite hover:text-ink"
                )}
            >
                Todas
            </button>

            {chips.map((c) => {
                const active = picked.some((n) => n === c.name);
                return (
                    <button
                        key={c.name}
                        type="button"
                        aria-pressed={active}
                        title={`${c.name} · ${mxn(c.amount)}`}
                        onClick={() => onPick(c.name)}
                        onMouseEnter={onHover && (() => onHover(c.name))}
                        onMouseLeave={onHover && (() => onHover(null))}
                        onFocus={onHover && (() => onHover(c.name))}
                        onBlur={onHover && (() => onHover(null))}
                        className={cn(
                            CHIP,
                            "gap-1.5",
                            active
                                ? "bg-soot font-medium text-paper"
                                : "border border-mist text-graphite hover:text-ink"
                        )}
                    >
                        <span
                            aria-hidden
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ background: c.color, opacity: c.faded ? 0.3 : undefined }}
                        />
                        {c.name}
                    </button>
                );
            })}

            {month && (
                // The month only ever comes from clicking a layer, so it is
                // shown as a removable token rather than a row of 12 chips
                // duplicating the axis.
                <button
                    type="button"
                    onClick={onClearMonth}
                    aria-label={`Quitar filtro de ${monthLabel ?? month}`}
                    className={cn(CHIP, "gap-1 border border-edge bg-wash text-ink")}
                >
                    {monthLabel ?? month}
                    <X size={12} aria-hidden />
                </button>
            )}
        </div>
    );
}

const CHIP =
    "inline-flex items-center rounded-control px-3 py-1.5 text-body-sm transition-colors duration-100";
