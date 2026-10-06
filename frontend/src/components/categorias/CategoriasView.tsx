"use client";

import { cn } from "@/lib/cn";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Shapes } from "lucide-react";
import {
    categoryName,
    UNCATEGORIZED_COLOR,
    useCategories,
} from "@/lib/categories";
import { useBankScope } from "@/lib/banks";
import { useChartsV2 } from "@/lib/chartsV2";
import { chart as chartTokens, colors as palette } from "@/design/tokens";
import { monthLabel, mxn } from "@/lib/format";
import {
    isMetricError,
    num,
    parsePeriodKey,
    queryMetrics,
    type MetricEntry,
} from "@/lib/metrics";
import { monthsToRange } from "@/lib/window";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import { track } from "@/lib/telemetry";
import { useAppData } from "@/components/AppChrome";
import { BackendNotice, EmptyState, Skeleton } from "@/components/ui";
import { ChartCard } from "@/components/ChartCard";
import { LecturaDock } from "@/components/lectura/LecturaDock";
import { useLectura } from "@/components/lectura/LecturaProvider";
import { draftFromClauses } from "@/lib/lectura";
import { RangeBrush, type BucketRange } from "@/components/charts/RangeBrush";
import { TransactionsList } from "@/components/movimientos/TransactionsList";
import { useTransactions } from "@/components/movimientos/useTransactions";
import { CategorySpendChart, type MonthlyCategoryPoint } from "./CategorySpendChart";
import { CategoryFilterBar, type CategoryChip } from "./CategoryFilterBar";

/**
 * The Categorías view: one stacked column per month of the selected period,
 * layered by category — each month's height is what it cost, its layers say
 * on what — and, under it, the movements those layers are made of.
 *
 * The chart is an aggregate and the list is its evidence. Clicking a layer
 * filters the list to that category *and* that month; the chips do the same
 * for a category across the whole period. Without this the view could only
 * ever be admired, never checked — and "¿qué fue ese mes de Comida?" is the
 * first question the chart provokes.
 *
 * Two sources feed this screen and they are reconciled deliberately: the
 * columns come from the metrics cube (aggregated server-side, keyed by
 * category NAME), the rows come from the transactions API (keyed by category
 * ID). `sameCategory` is the seam — see the note there.
 */

/** Rows revealed per page in the evidence list. */
const PAGE = 50;

/**
 * The cube labels the unlabelled bucket "Sin Categoria" (no accent); the
 * frontend says "Sin categoría" everywhere, including as the fallback below.
 * Comparing raw strings would silently drop every uncategorized movement out
 * of its own filter, so names are compared accent- and case-insensitively.
 */
function normalize(name: string): string {
    return name
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .trim();
}

function sameCategory(a: string, b: string): boolean {
    return normalize(a) === normalize(b);
}

function categoryIdByName(
    map: ReturnType<typeof useCategories>,
    name: string
): string | undefined {
    if (!map) return undefined;
    for (const [id, info] of Array.from(map.entries())) {
        if (sameCategory(info.name, name)) return id;
    }
    return undefined;
}

export function CategoriasView() {
    const { windowKey, period, bounds, dataVersion } = useAppData();
    const { selectCustom } = useTimeWindow();
    const categories = useCategories();
    const [entry, setEntry] = useState<MetricEntry | null>(null);
    const [fetching, setFetching] = useState(true);
    const [error, setError] = useState<string | null>(null);
    // Bumped when an edit here changes a category: the cube has to be asked
    // again, or the columns would keep showing the category the user just
    // corrected.
    const [edits, setEdits] = useState(0);
    const { openDraft, opening } = useLectura();
    const v2 = useChartsV2();
    // v2: the chip under the pointer — a transient focus over the chart.
    const [hovered, setHovered] = useState<string | null>(null);

    // What the list is showing. Both come from the chart or the chips, and
    // both are session state — a filter is a question, not a preference.
    // Months are a RANGE ("2026-02".."2026-04"): a layer click asks about one
    // month (start === end), a drag across the columns asks about several.
    const [pickedCategories, setPickedCategories] = useState<string[]>([]);
    const [pickedMonths, setPickedMonths] = useState<{ start: string; end: string } | null>(
        null
    );
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [visibleCount, setVisibleCount] = useState(PAGE);

    const { statementIds } = useBankScope(dataVersion);
    const scopeKey = statementIds?.join("|") ?? "";


    useEffect(() => {
        let stale = false;
        // The old columns stay mounted while the new ones load, so Apex can
        // tween one set into the other instead of repainting from a skeleton.
        setFetching(true);
        queryMetrics(period, [
            // Month grain alongside the category dimension: rows arrive as
            // {month, category, expense_amount} — the stacked reading's shape.
            {
                key: "cats",
                metric: "spend_by_category",
                grain: "month",
                ...(statementIds ? { filters: { statement: statementIds } } : {}),
            },
        ])
            .then((batch) => {
                if (stale) return;
                setEntry(batch.results.cats);
                setError(null);
                setFetching(false);
            })
            .catch((e) => {
                if (stale) return;
                setError((e as Error).message);
                setFetching(false);
            });
        return () => {
            stale = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [period, dataVersion, edits, scopeKey]);

    // The rows behind the columns. Same window, same cap as Movimientos.
    const {
        items,
        error: txError,
        reload,
        patchItem,
    } = useTransactions(bounds, dataVersion, statementIds);

    // A new period is a new reading: filters and paging reset rather than
    // silently applying to data the user hasn't looked at yet.
    useEffect(() => {
        setPickedCategories([]);
        setPickedMonths(null);
        setSelectedId(null);
        setVisibleCount(PAGE);
    }, [windowKey]);

    const result = entry && !isMetricError(entry) ? entry : null;
    const loading = entry === null && !error;
    const refreshing = fetching && !loading;

    const points: MonthlyCategoryPoint[] = useMemo(() => {
        if (!result) return [];
        return (
            result.rows
                .map((row) => {
                    const month = String(row.month ?? "");
                    const date = parsePeriodKey(month);
                    return {
                        month,
                        monthLabel: date ? monthLabel(date, true) : month,
                        category: String(row.category ?? "Sin categoría"),
                        amount: num(row.expense_amount),
                    };
                })
                // The API orders breakdowns by measure; the month axis must be
                // chronological regardless.
                .sort((a, b) => a.month.localeCompare(b.month))
        );
    }, [result]);

    // The metric rows carry the category NAME (the cube's dimension); colors
    // come from the taxonomy, matched by name.
    const categoryColors = useMemo(() => {
        const map = new Map<string, string>();
        categories?.forEach((info) => map.set(info.name, info.color ?? UNCATEGORIZED_COLOR));
        return map;
    }, [categories]);

    /** One chip per category the period actually touched, biggest first —
     *  the stack's own order, so chart and chips agree on what matters. */
    const ranked = useMemo(() => {
        const totals = new Map<string, number>();
        for (const p of points) totals.set(p.category, (totals.get(p.category) ?? 0) + p.amount);
        return Array.from(totals.entries()).sort((a, b) => b[1] - a[1]);
    }, [points]);

    // v2: the category the reading is about — the one picked alone, else the
    // window's biggest. The title names it and it is the one layer in Signal.
    const focus = v2
        ? pickedCategories.length === 1
            ? pickedCategories[0]!
            : pickedCategories.length === 0
              ? (ranked[0]?.[0] ?? null)
              : null
        : null;
    const lit = hovered ?? focus;

    // v2: hue is not a category's identity. Each one takes a step of the stone
    // ramp by its rank over the whole window — stable across months and
    // filters — and Signal goes to the focused one only. Chart and chips read
    // from this same map, so a chip is its layer's swatch.
    const layerColors = useMemo(() => {
        if (!v2) return categoryColors;
        const map = new Map<string, string>();
        ranked.forEach(([name], i) =>
            map.set(
                name,
                lit !== null && sameCategory(name, lit)
                    ? palette.signal
                    : chartTokens.neutral[i % chartTokens.neutral.length]!
            )
        );
        return map;
    }, [v2, categoryColors, ranked, lit]);

    const chips: CategoryChip[] = useMemo(
        () =>
            ranked.map(([name, amount]) => ({
                name,
                amount,
                color: layerColors.get(name) ?? UNCATEGORIZED_COLOR,
            })),
        [ranked, layerColors]
    );

    // Taxonomy entries the period never touched.
    const untouched = useMemo(() => {
        if (!categories) return [];
        const spent = new Set(points.map((p) => p.category));
        return Array.from(categories.values())
            .map((c) => c.name)
            .filter((name) => !spent.has(name));
    }, [categories, points]);

    const filtered = useMemo(() => {
        if (items === null) return null;
        // Expenses only: the columns are spend, so an income row in the list
        // would be evidence for a mark that isn't there.
        let out = items.filter((t) => t.type === "expense");
        if (pickedCategories.length) {
            out = out.filter((t) =>
                pickedCategories.some((name) =>
                    sameCategory(categoryName(categories, t.category_id), name)
                )
            );
        }
        if (pickedMonths) {
            out = out.filter((t) => {
                const m = t.date.slice(0, 7);
                return m >= pickedMonths.start && m <= pickedMonths.end;
            });
        }
        return out;
    }, [items, categories, pickedCategories, pickedMonths]);

    const filteredTotal = useMemo(
        () => (filtered ?? []).reduce((sum, t) => sum + t.amount, 0),
        [filtered]
    );

    // Clicking the layer that is already filtered clears it: the gesture that
    // asked the question takes it back, so there is no dead-end selection.
    const handlePick = useCallback(
        (category: string, month: string) => {
            const already = pickedCategories.some((n) => sameCategory(n, category));
            const sameMonth =
                already &&
                pickedCategories.length === 1 &&
                pickedMonths?.start === month &&
                pickedMonths?.end === month;
            if (sameMonth) {
                setPickedCategories([]);
                setPickedMonths(null);
            } else {
                setPickedCategories([category]);
                setPickedMonths({ start: month, end: month });
            }
            setSelectedId(null);
            setVisibleCount(PAGE);
        },
        [pickedCategories, pickedMonths]
    );

    function pickCategory(name: string | null) {
        if (!name) {
            setPickedCategories([]);
        } else {
            track("categorias.pick_category");
            setPickedCategories((cur) =>
                cur.some((n) => n === name) ? cur.filter((n) => n !== name) : [...cur, name]
            );
        }
        setSelectedId(null);
        setVisibleCount(PAGE);
    }

    // The chart answers the same filter the list does: one category picked →
    // its own monthly columns; a month range dragged → only those months, a
    // zoom-in. The click or drag that narrows the question narrows the
    // drawing — chart and list always describe the same set.
    const chartPoints = useMemo(() => {
        let out = points;
        if (pickedCategories.length) {
            out = out.filter((pt) =>
                pickedCategories.some((name) => sameCategory(pt.category, name))
            );
        }
        if (pickedMonths) {
            out = out.filter(
                (pt) => pt.month >= pickedMonths.start && pt.month <= pickedMonths.end
            );
        }
        return out;
    }, [points, pickedCategories, pickedMonths]);

    // The drawn chart's month axis, chronological — the brush maps drag
    // pixels to indices into exactly this.
    const monthKeys = useMemo(() => {
        const keys: string[] = [];
        for (const p of chartPoints) if (!keys.includes(p.month)) keys.push(p.month);
        return keys;
    }, [chartPoints]);

    // A drag across the months is not a local zoom any more: it sets the
    // app's time window to those months, so this chart, the list, and every
    // other view answer for the same span — and the header shows it.
    const handleBrush = useCallback(
        (r: BucketRange) => {
            const start = monthKeys[r.start];
            const end = monthKeys[r.end];
            if (!start || !end) return;
            const range = monthsToRange(start, end);
            selectCustom(range.start, range.end, "drag:categorias");
            setPickedMonths(null);
            setSelectedId(null);
            setVisibleCount(PAGE);
        },
        [monthKeys, selectCustom]
    );

    // v2: hovering a chip whose layer is drawn fades every other layer.
    const dimmed = useMemo(() => {
        if (!v2 || !hovered || !chartPoints.some((p) => sameCategory(p.category, hovered))) {
            return undefined;
        }
        return new Set(chartPoints.map((p) => p.category).filter((c) => !sameCategory(c, hovered)));
    }, [v2, hovered, chartPoints]);

    // v2: the month of the latest movement, if the statement stops before it
    // ends — drawn apart and kept out of the mean and the month-on-month delta.
    const partial = useMemo(() => {
        if (!v2 || !items?.length) return null;
        const latest = items.reduce((max, t) => (t.date > max ? t.date : max), items[0]!.date);
        const [y, m, d] = latest.split("-").map(Number);
        if (!y || !m || !d) return null;
        const lastDay = new Date(y, m, 0).getDate();
        return d < lastDay ? { month: latest.slice(0, 7), day: d } : null;
    }, [v2, items]);

    // v2: the chart's title is its finding, from the whole window (not the
    // drawn subset): the focus category's share, its total, and — with two
    // complete months — how the last one moved against the one before.
    const finding = useMemo(() => {
        if (!v2 || !focus || points.length === 0) return null;
        let all = 0;
        let own = 0;
        const months: string[] = [];
        const byMonth = new Map<string, number>();
        for (const p of points) {
            all += p.amount;
            if (!months.includes(p.month)) months.push(p.month);
            if (sameCategory(p.category, focus)) {
                own += p.amount;
                byMonth.set(p.month, (byMonth.get(p.month) ?? 0) + p.amount);
            }
        }
        if (all <= 0 || own <= 0) return null;
        const n = months.length;
        let text = `${focus} fue ${Math.round((own / all) * 100)}% de tu gasto: ${mxn(own)} en ${n} ${n === 1 ? "mes" : "meses"}`;
        const complete = months.filter((m) => m !== partial?.month);
        const last = complete[complete.length - 1];
        const prev = complete[complete.length - 2];
        const before = prev ? (byMonth.get(prev) ?? 0) : 0;
        if (last && prev && before > 0) {
            const delta = Math.round((((byMonth.get(last) ?? 0) - before) / before) * 100);
            const label = (key: string) => {
                const date = parsePeriodKey(key);
                return date ? monthLabel(date) : key;
            };
            text += `; ${delta > 0 ? "+" : ""}${delta}% en ${label(last)} vs ${label(prev)}`;
        }
        return text;
    }, [v2, focus, points, partial]);

    const pickedMonthLabel = useMemo(() => {
        if (!pickedMonths) return undefined;
        const label = (key: string) => {
            const d = parsePeriodKey(key);
            return d ? monthLabel(d, true) : key;
        };
        return pickedMonths.start === pickedMonths.end
            ? label(pickedMonths.start)
            : `${label(pickedMonths.start)} – ${label(pickedMonths.end)}`;
    }, [pickedMonths]);

    return (
        <div className="space-y-4 sm:space-y-6">
            {error && <BackendNotice what="el gasto por categoría" detail={error} />}

            {!loading && points.length === 0 && !error ? (
                <EmptyState icon={Shapes} title="Ningún cargo en este periodo">
                    Prueba con un periodo más amplio, o sube un estado de cuenta que lo cubra.
                </EmptyState>
            ) : (
                <>
                    <ChartCard
                        title={finding ?? "Gasto por categoría, mes a mes"}
                        subtitle={finding ? "Gasto por categoría, mes a mes" : undefined}
                    >
                        {loading ? (
                            <Skeleton className="h-[360px]" />
                        ) : (
                            <>
                                {/* The zoom IS the feedback: the axis narrows
                                    to the dragged months, so no persistent
                                    highlight is drawn (range={null}) — it
                                    would cover the whole plot. A drag inside
                                    the zoom narrows further; the month chip
                                    below is the way back out. */}
                                <div className={cn("transition-opacity duration-300", refreshing && "opacity-50")}>
                                <RangeBrush
                                    buckets={monthKeys.length}
                                    range={null}
                                    onRange={handleBrush}
                                >
                                    <CategorySpendChart
                                        // Keyed by the filters: react-apexcharts
                                        // mutates the mounted chart and keeps
                                        // stale colors and axes when the series
                                        // or month set changes — a different
                                        // selection is a different chart.
                                        key={`${pickedCategories.join("|") || "todas"}-${pickedMonths?.start ?? ""}-${pickedMonths?.end ?? ""}`}
                                        points={chartPoints}
                                        categoryColors={layerColors}
                                        onPick={handlePick}
                                        dimmed={dimmed}
                                        partial={partial}
                                        ariaLabel={finding ?? undefined}
                                    />
                                </RangeBrush>
                                </div>
                                <p className={cn("text-label", v2 ? "text-graphite" : "text-ash")}>
                                    Haz clic en una capa para ver sus movimientos, o
                                    arrastra sobre los meses para acotar un rango.
                                    {untouched.length > 0 &&
                                        ` · Sin gasto: ${untouched.join(" · ")}`}
                                </p>
                            </>
                        )}
                    </ChartCard>

                    <section className="min-w-0 rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                            <h2 className="text-title-sm font-normal text-ink">
                                Movimientos
                                {filtered && (
                                    <span className="ml-2 text-body-sm text-graphite">
                                        {filtered.length}
                                    </span>
                                )}
                            </h2>
                            {filtered && filtered.length > 0 && (
                                <span className="tabular text-body-sm text-graphite">
                                    {mxn(filteredTotal)}
                                </span>
                            )}
                        </div>

                        <div className="mt-3">
                            <CategoryFilterBar
                                chips={chips}
                                picked={pickedCategories}
                                onPick={pickCategory}
                                month={pickedMonths?.start ?? null}
                                monthLabel={pickedMonthLabel}
                                onClearMonth={() => setPickedMonths(null)}
                                onHover={v2 ? setHovered : undefined}
                            />
                        </div>

                        {txError && (
                            <p className="mt-3 text-body-sm text-graphite">
                                No pudimos cargar los movimientos ({txError}).
                            </p>
                        )}

                        <div className="mt-4">
                            {filtered === null ? (
                                <div className="space-y-2">
                                    {Array.from({ length: 6 }).map((_, i) => (
                                        <Skeleton key={i} className="h-11" />
                                    ))}
                                </div>
                            ) : filtered.length === 0 ? (
                                <p className="py-6 text-body text-graphite">
                                    {pickedCategories.length || pickedMonths
                                        ? "Ningún movimiento con este filtro."
                                        : "Sin movimientos en este periodo."}
                                </p>
                            ) : (
                                <TransactionsList
                                    items={filtered}
                                    visibleCount={visibleCount}
                                    onShowMore={() => setVisibleCount((c) => c + PAGE)}
                                    selectedId={selectedId}
                                    onSelect={setSelectedId}
                                    editing={{
                                        onPatch: async (t, patch) => {
                                            await patchItem(t.id, patch);
                                            // Recategorizing from here moves a
                                            // peso between two columns above;
                                            // ask the cube again.
                                            if ("category_id" in patch) {
                                                setEdits((e) => e + 1);
                                            }
                                        },
                                        onBulkApplied: () => {
                                            reload();
                                            setEdits((e) => e + 1);
                                        },
                                    }}
                                />
                            )}
                        </div>
                    </section>
                </>
            )}

            {pickedCategories.length > 0 && (
                <LecturaDock
                    summary={
                        pickedCategories.length === 1
                            ? `1 categoría · ${pickedCategories[0]}`
                            : `${pickedCategories.length} categorías`
                    }
                    chips={pickedCategories}
                    busy={opening}
                    onRead={() => {
                        const clauses = pickedCategories
                            .map((name) => {
                                const category_id = categoryIdByName(categories, name);
                                return category_id ? { category_id } : null;
                            })
                            .filter((c): c is { category_id: string } => c !== null);
                        const draft = draftFromClauses(
                            clauses,
                            [],
                            pickedCategories.join(" + ")
                        );
                        if (draft) void openDraft(draft);
                    }}
                    onClear={() => setPickedCategories([])}
                />
            )}
        </div>
    );
}
