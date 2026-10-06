"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { mxn2 } from "@/lib/format";
import { useCategories } from "@/lib/categories";
import { useChartsV2 } from "@/lib/chartsV2";
import { barFill, pct, sliceColor, type CategorySlice } from "@/lib/categoryComposition";
import { monthName, spansYears, type MonthSlice } from "@/lib/porMes";

/**
 * One row per month, newest first; opening it shows the month's categories.
 *
 * The rows are the category accordion's rows — chevron, name, count, share
 * bar, share, amount — so the two faces read as one list cut two ways. Open
 * is grey, not blue, for the same reason: a lid off is not a selection. The
 * share figure is the one thing that takes Edge when open, as it does there.
 *
 * A category line inside a month opens the modal on that month and that
 * category; the footer opens the month whole.
 */
export function MesesList({
    months,
    total,
    count,
    openKey,
    onToggle,
    onVerMes,
    onVerCategoria,
}: {
    months: MonthSlice[];
    total: number;
    count: number;
    openKey: string | null;
    onToggle: (key: string) => void;
    onVerMes: (key: string) => void;
    onVerCategoria: (monthKey: string, categoryKey: string) => void;
}) {
    const withYear = spansYears(months.map((m) => m.key));

    return (
        <>
            <header className="flex items-center justify-between gap-3 border-b border-mist px-5 py-4 sm:px-6">
                <h2 className="flex items-baseline gap-2 text-title-sm font-normal text-ink">
                    Meses
                    <span className="tabular font-sans text-body-sm text-graphite">
                        {months.length}
                    </span>
                </h2>
                <span className="tabular shrink-0 text-body-sm text-graphite">
                    {mxn2(total)}
                    <span className="hidden sm:inline"> · {count} cargo{count === 1 ? "" : "s"}</span>
                </span>
            </header>

            <ul className="divide-y divide-mist">
                {months.map((m) => {
                    const open = openKey === m.key;
                    const color = barFill(m.rank, false);
                    return (
                        <li key={m.key} className={cn(open && "bg-fog/60")}>
                            <div
                                className={cn(
                                    "flex min-h-12 items-center gap-3 px-5 py-2.5 transition-colors duration-100 sm:px-6",
                                    open ? "border-b border-muted/70 bg-fog" : "hover:bg-fog/50"
                                )}
                            >
                                <button
                                    type="button"
                                    aria-expanded={open}
                                    onClick={() => onToggle(m.key)}
                                    className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                                >
                                    <ChevronRight
                                        size={16}
                                        aria-hidden
                                        className={cn(
                                            "shrink-0 transition-transform duration-150",
                                            open ? "rotate-90 text-graphite" : "text-ash"
                                        )}
                                    />
                                    <span className="min-w-0 truncate text-body font-medium text-ink">
                                        {monthName(m.key, withYear)}
                                    </span>
                                    <Count n={m.count} />
                                </button>

                                <div className="flex shrink-0 items-center gap-3 sm:gap-4">
                                    <span className="hidden h-1.5 w-28 overflow-hidden rounded-full bg-mist sm:block lg:w-40">
                                        <span
                                            className="block h-full rounded-full"
                                            style={{
                                                width: `${Math.max(pct(m.share), 2)}%`,
                                                background: color,
                                            }}
                                        />
                                    </span>
                                    <span
                                        className={cn(
                                            "tabular w-10 text-right text-body-sm",
                                            open ? "font-medium text-edge" : "text-graphite"
                                        )}
                                    >
                                        {pct(m.share)}%
                                    </span>
                                    <span className="tabular w-24 text-right text-body font-medium text-ink sm:w-28">
                                        {mxn2(m.amount)}
                                    </span>
                                </div>
                            </div>

                            {open && (
                                <>
                                    <Categorias
                                        slices={m.composition.bar}
                                        onPick={(key) => onVerCategoria(m.key, key)}
                                    />
                                    <div className="flex justify-end border-t border-muted/70 px-5 py-2 sm:px-6">
                                        <button
                                            type="button"
                                            onClick={() => onVerMes(m.key)}
                                            className="rounded-control px-2 py-1 text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                                        >
                                            Ver en transacciones
                                        </button>
                                    </div>
                                </>
                            )}
                        </li>
                    );
                })}
            </ul>
        </>
    );
}

/** The month's categories, biggest first, uncategorized last — the bar's
 *  order. Each line is the accordion's folded group: name, count, share of
 *  the month, amount. */
function Categorias({
    slices,
    onPick,
}: {
    slices: CategorySlice[];
    onPick: (key: string) => void;
}) {
    // v2: each line carries its category's swatch — the same color it wears
    // in the bar and the accordion. The month rows above keep the stone ramp:
    // a month is not a category.
    const v2 = useChartsV2();
    const categories = useCategories();
    return (
        <div className="py-3 pl-7 pr-5 sm:pl-12 sm:pr-6">
            {slices.map((s) => (
                <button
                    key={s.key}
                    type="button"
                    onClick={() => onPick(s.key)}
                    className="flex w-full items-center justify-between gap-3 border-t border-muted/50 py-1.5 text-left transition-colors duration-100 first:border-t-0 hover:text-ink"
                >
                    <span className="flex min-w-0 items-baseline gap-1.5">
                        <ChevronRight
                            size={14}
                            aria-hidden
                            className="shrink-0 translate-y-0.5 text-ash"
                        />
                        {v2 && (
                            <span
                                aria-hidden
                                className="h-2 w-2 shrink-0 self-center rounded-full"
                                style={{ background: sliceColor(s, categories) }}
                            />
                        )}
                        <span className="truncate text-body-sm text-graphite">{s.name}</span>
                        <span className="tabular whitespace-nowrap text-label font-normal text-ash">
                            · {s.count.toLocaleString("es-MX")} cargo{s.count === 1 ? "" : "s"} ·{" "}
                            {pct(s.share)}% del mes
                        </span>
                    </span>
                    <span className="tabular shrink-0 text-body-sm text-ink">{mxn2(s.amount)}</span>
                </button>
            ))}
        </div>
    );
}

/** "· 35 cargos". Quiet enough to sit beside a name without competing. */
function Count({ n }: { n: number }) {
    return (
        <span className="tabular shrink-0 whitespace-nowrap text-label text-ash">
            · {n.toLocaleString("es-MX")} cargo{n === 1 ? "" : "s"}
        </span>
    );
}
