"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SearchX, Inbox } from "lucide-react";
import { cn } from "@/lib/cn";
import { useAppData } from "@/components/AppChrome";
import { useSearchParams } from "next/navigation";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import { msToIso } from "@/lib/window";
import { useChartsV2 } from "@/lib/chartsV2";
import { track } from "@/lib/telemetry";
import { draftFromClauses, draftFromNeedle } from "@/lib/lectura";
import {
    EMPTY_QUERY,
    UNCATEGORIZED,
    applyQuery,
    categoryLens,
    queryIsActive,
} from "@/lib/movimientosQuery";
import { useMovimientosSearch } from "./MovimientosSearchProvider";
import { PanelSettingsToggle } from "@/components/settings/PanelSettingsToggle";
import { BackendNotice, Button, ChartSkeleton, EmptyState, Skeleton, Switch } from "@/components/ui";
import { ChartCard } from "@/components/ChartCard";
import { LecturaDock } from "@/components/lectura/LecturaDock";
import { useLectura } from "@/components/lectura/LecturaProvider";
import {
    PanelChoice,
    PanelControl,
    PanelControls,
    PanelNumber,
} from "@/components/settings/PanelControls";
import { usePanelSettings } from "@/components/settings/usePanelSettings";
import {
    CHART_MODE_LABELS,
    CHART_MODES,
    COLOR_MODE_LABELS,
    COLOR_MODES,
    TransactionsChart,
    dateToMs,
    medianAmount,
    type ChartMode,
    type ColorMode,
} from "@/components/charts/TransactionsChart";
import { categoryName, useCategories } from "@/lib/categories";
import { useBankScope } from "@/lib/banks";
import { dayLabel, mxn, mxn2 } from "@/lib/format";
import {
    ChartLens,
    LensChips,
    LENS_KIND_LABELS,
    type Lectura,
    type LensFocus,
    type LensGroup,
} from "@/components/charts/lens";
import { FETCH_CAP, useTransactions } from "./useTransactions";
import { useAttention } from "./useAttention";
import { TransactionsList } from "./TransactionsList";

/** Rows revealed per "show more" step, and the initial page — a list setting.
 *  Any size in range is valid; the cap is the fetch cap, since asking for more
 *  rows than the app ever loads is not a setting. */
const DEFAULT_PAGE = 50;
const MIN_PAGE = 1;
const MAX_PAGE = FETCH_CAP;

/**
 * The Movimientos view: the window's transactions as a scatter (outlier
 * hunting) over the same rows as a list (detail reading). One dataset feeds
 * both, so they cannot disagree; selection travels in both directions.
 */
export function MovimientosView() {
    const { windowKey, window: timeWindow, bounds, grain, dataVersion } = useAppData();
    const { selectCustom, clearCustom } = useTimeWindow();
    const { statementIds } = useBankScope(dataVersion);
    const { items, total, error, reload, patchItem, loading: fetching } = useTransactions(
        bounds,
        dataVersion,
        statementIds
    );
    const categories = useCategories();
    // The rings: charges in this window worth a second look, judged by the
    // backend against the whole ledger. Same scope as the rows above, so a
    // ring always has its dot.
    const { items: attention, dismiss: dismissAttention } = useAttention(
        bounds,
        dataVersion,
        statementIds
    );
    const [lensFocus, setLensFocus] = useState<LensFocus>(null);
    const v2 = useChartsV2();

    // Each panel owns its settings, keyed by its own id: the chart's are the
    // chart's, the list's are the list's, and both outlive this mount.
    const [chartCfg, setChartCfg] = usePanelSettings("movimientos.scatter", {
        showIncome: false,
        mode: "scatter" as string,
        colorMode: "neutral" as string,
    });
    // Stored values are user data; one this build doesn't know (a future
    // mode, a hand-edited store) falls back rather than blanking the chart.
    const mode: ChartMode = (CHART_MODES as readonly string[]).includes(chartCfg.mode)
        ? (chartCfg.mode as ChartMode)
        : "scatter";
    const colorMode: ColorMode = (COLOR_MODES as readonly string[]).includes(chartCfg.colorMode)
        ? (chartCfg.colorMode as ColorMode)
        : "neutral";
    const [listCfg, setListCfg] = usePanelSettings("movimientos.lista", {
        pageSize: DEFAULT_PAGE,
    });
    // Clamp on read too: the stored value is user-entered and, once the store
    // is a backend, not necessarily written by this build of the app.
    const page = Number.isFinite(listCfg.pageSize)
        ? Math.min(MAX_PAGE, Math.max(MIN_PAGE, Math.round(listCfg.pageSize)))
        : DEFAULT_PAGE;

    // `?buscar=` seeds the needle once, so another view can hand over a
    // filtered ledger ("revisa las transferencias") as a link.
    const seeded = useSearchParams().get("buscar") ?? "";
    const { query, setQuery } = useMovimientosSearch();
    useEffect(() => {
        if (seeded) setQuery({ ...EMPTY_QUERY, needle: seeded });
        // Only the URL: a later edit of the needle must not be overwritten.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [seeded]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [visibleCount, setVisibleCount] = useState(page);
    const [excluded, setExcluded] = useState<Set<string>>(() => new Set());
    const { openDraft, opening } = useLectura();
    // v2: the default lens focus is offered once per reading. `defaulted` says
    // it was placed; `userTouched` says the user picked or dropped (Esc) one,
    // and from then on a refetch of the lecturas never overrides that choice.
    const lensDefaulted = useRef(false);
    const lensUserTouched = useRef(false);
    // A new window, search or page size is a new reading: selection and paging
    // reset.
    useEffect(() => {
        setSelectedId(null);
        setVisibleCount(page);
        setExcluded(new Set());
        setLensFocus(null);
        lensDefaulted.current = false;
        lensUserTouched.current = false;
    }, [windowKey, query, dataVersion, page, statementIds]);

    const filtered = useMemo(() => {
        if (items === null) return null;
        return applyQuery(items, query, categoryLens(categories));
    }, [items, query, categories]);

    // Lecturas for the scatter: one chip per kind, each a tour of its
    // charges. Anchored on the rows actually drawn — a flagged charge the
    // search filtered out has no dot, so it has no ring either. Only the
    // scatter has per-charge marks; the flujo aggregate shows none.
    const lensGroups: LensGroup[] = useMemo(() => {
        if (!filtered || mode !== "scatter") return [];
        const byId = new Map(filtered.map((t) => [t.id, t]));
        const byKind = new Map<string, Lectura[]>();
        for (const a of attention) {
            const t = byId.get(a.transaction_id);
            if (!t || t.type !== "expense") continue;
            const l: Lectura = {
                id: a.transaction_id,
                kind: a.kind,
                anchor: { x: dateToMs(t.date), y: t.amount },
                title: `${t.description} · ${mxn2(t.amount)} · ${dayLabel(new Date(dateToMs(t.date)))}`,
                detail: a.reason,
                severity: a.severity,
                ref: t.id,
            };
            byKind.set(a.kind, [...(byKind.get(a.kind) ?? []), l]);
        }
        return Array.from(byKind.entries()).map(([kind, lecturas]) => {
            const label = LENS_KIND_LABELS[lecturas[0]!.kind];
            // The chip shows the count itself; the label only pluralises.
            return { id: kind, label: lecturas.length === 1 ? label : plural(label), lecturas };
        });
    }, [filtered, attention, mode]);

    // v2: a new set of lecturas opens on its most serious one (warn before
    // info) instead of waiting for a click; a chip or Esc replaces it. Runs
    // after the reset above, so a new window lands focused, not cleared — and
    // only once per reading, so lecturas arriving late never undo a choice.
    useEffect(() => {
        if (!v2 || lensDefaulted.current || lensUserTouched.current) return;
        if (lensGroups.length === 0) return;
        lensDefaulted.current = true;
        setLensFocus(defaultFocus(lensGroups));
    }, [v2, lensGroups, windowKey, query, dataVersion, page, statementIds]);

    const attentionByRow = useMemo(
        () => new Map(attention.map((a) => [a.transaction_id, a.kind])),
        [attention]
    );

    const onLensFocus = useCallback((next: LensFocus) => {
        if (next) track("lens.open", { chart: "movimientos", kind: next.groupId, index: next.index });
        lensUserTouched.current = true;
        setLensFocus(next);
    }, []);

    // A range dragged over the chart is not a local zoom any more: it becomes
    // the app's time window. The list, the chart and every other view then
    // answer for the same days, and the header shows the dates it covers.
    const listed = filtered;

    // Chart → list: make sure the selected row is inside the visible page
    // before the list tries to scroll to it. Indexed against what the list
    // actually shows — a dot outside the dragged range has no row to reveal.
    function handleSelect(id: string | null) {
        setSelectedId(id);
        if (id && listed) {
            const index = listed.findIndex((t) => t.id === id);
            if (index >= visibleCount) {
                setVisibleCount(Math.ceil((index + 1) / page) * page);
            }
        }
    }

    const loading = filtered === null || listed === null;
    // A refetch with data already on screen: keep it, dim it, let the chart
    // tween into the new series when it arrives. Only the first load blanks.
    const refreshing = fetching && !loading;

    // One sentence before the dots: what left, in how many charges, over which
    // days. Built from the rows on screen so it cannot disagree with the chart
    // or the list, and absent while there are no rows — a total of $0 over an
    // empty window would be a claim, not a fact.
    const orientation = useMemo(() => {
        if (!filtered || filtered.length === 0) return null;
        const expenses = filtered.filter((t) => t.type === "expense");
        const spent = expenses.reduce((sum, t) => sum + Math.abs(t.amount), 0);
        const span =
            bounds.start && bounds.end
                ? `del ${dayLabel(fromIso(bounds.start))} al ${dayLabel(fromIso(bounds.end))}`
                : "en todo tu historial";
        const extra = queryIsActive(query);
        const needle = query.needle.trim()
            ? ` que contienen «${query.needle.trim()}»`
            : extra
              ? " con estos criterios"
              : "";
        if (expenses.length === 0) {
            return `Sin cargos ${span}${needle}; ${filtered.length.toLocaleString("es-MX")} abono${filtered.length === 1 ? "" : "s"}.`;
        }
        return `Salieron ${mxn(spent)} en ${expenses.length.toLocaleString("es-MX")} cargo${expenses.length === 1 ? "" : "s"} ${span}${needle}.`;
    }, [filtered, bounds.start, bounds.end, query]);
    const filtering = queryIsActive(query) && Boolean(listed && listed.length > 0);

    // v2: the orientation becomes the title, with the contrast that makes it
    // a finding — the biggest cargo against the typical one. The span and the
    // criteria move under it with the chart's name.
    const finding = useMemo(() => {
        if (!v2 || !filtered) return null;
        const expenses = filtered.filter((t) => t.type === "expense");
        if (expenses.length === 0) return null;
        const spent = expenses.reduce((sum, t) => sum + Math.abs(t.amount), 0);
        const head = `Salieron ${mxn(spent)} en ${expenses.length.toLocaleString("es-MX")} cargo${expenses.length === 1 ? "" : "s"}`;
        const median = medianAmount(filtered);
        if (expenses.length < 3 || !median) return head;
        const top = expenses.reduce((a, b) => (Math.abs(b.amount) > Math.abs(a.amount) ? b : a));
        const times = Math.abs(top.amount) / median;
        const x = times < 10 ? times.toFixed(1).replace(/\.0$/, "") : String(Math.round(times));
        return `${head}; el mayor, ${shorten(top.description)} ${mxn(Math.abs(top.amount))}, es ${x}× tu mediana`;
    }, [v2, filtered]);
    const findingSub = useMemo(() => {
        if (!finding || !orientation) return orientation;
        const span =
            bounds.start && bounds.end
                ? `del ${dayLabel(fromIso(bounds.start))} al ${dayLabel(fromIso(bounds.end))}`
                : "todo tu historial";
        const needle = query.needle.trim()
            ? ` · contiene «${query.needle.trim()}»`
            : queryIsActive(query)
              ? " · estos criterios"
              : "";
        return `Cada movimiento · ${span}${needle}`;
    }, [finding, orientation, bounds.start, bounds.end, query]);
    // v2: the category the reading is narrowed to keeps its color; the rest fade.
    const focusCategoryId =
        v2 && query.categoryIds.length === 1 && query.categoryIds[0] !== UNCATEGORIZED
            ? query.categoryIds[0]!
            : null;

    return (
        <div className="space-y-4 sm:space-y-6">
            {error && <BackendNotice what="tus movimientos" detail={error} />}

            <ChartCard
                title={finding ?? "Cada movimiento"}
                subtitle={finding ? findingSub : orientation}
                action={<PanelSettingsToggle />}
                controls={
                    <>
                        <PanelChoice<ChartMode>
                            label="Gráfica"
                            value={mode}
                            options={CHART_MODES.map((m) => ({
                                value: m,
                                label: CHART_MODE_LABELS[m],
                            }))}
                            onChange={(m) => {
                                track("movimientos.chart_mode", { mode: m });
                                setChartCfg({ mode: m });
                            }}
                        />
                        <PanelChoice<ColorMode>
                            label="Color"
                            value={colorMode}
                            options={COLOR_MODES.map((c) => ({
                                value: c,
                                label: COLOR_MODE_LABELS[c],
                            }))}
                            onChange={(c) => setChartCfg({ colorMode: c })}
                        />
                        <PanelControl label="Mostrar ingresos">
                            <Switch
                                aria-label="Mostrar ingresos en la gráfica"
                                checked={chartCfg.showIncome}
                                onChange={(showIncome) => setChartCfg({ showIncome })}
                            />
                        </PanelControl>
                    </>
                }
            >
                {loading ? (
                    <ChartSkeleton height={320} />
                ) : filtered.length === 0 ? (
                    <EmptyNote
                        narrowed={queryIsActive(query)}
                        onClear={() => setQuery(EMPTY_QUERY)}
                    />
                ) : (
                    <div className={cn("transition-opacity duration-300", refreshing && "opacity-50")}>
                    <LensChips
                        groups={lensGroups}
                        focus={lensFocus}
                        onFocus={onLensFocus}
                        className="mb-3"
                    />
                    <ChartLens
                        groups={lensGroups}
                        focus={lensFocus}
                        onFocus={onLensFocus}
                        actions={(l) => (
                            <>
                                <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() => {
                                        track("movimientos.row_select", { source: "lens" });
                                        handleSelect(l.ref ?? null);
                                    }}
                                >
                                    Ver
                                </Button>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => {
                                        track("lens.dismiss", { chart: "movimientos", kind: l.kind });
                                        if (l.ref) dismissAttention(l.ref);
                                        setLensFocus(null);
                                    }}
                                >
                                    Es mío
                                </Button>
                            </>
                        )}
                    >
                        <TransactionsChart
                            transactions={filtered}
                            mode={mode}
                            colorMode={colorMode}
                            categories={categories}
                            showIncome={chartCfg.showIncome}
                            grain={grain}
                            selectedId={selectedId}
                            onSelect={(id) => {
                                if (id) track("movimientos.row_select", { source: "chart" });
                                handleSelect(id);
                            }}
                            onRangeSelect={(r) =>
                                r && selectCustom(msToIso(r.start), msToIso(r.end), "drag:movimientos")
                            }
                            focusCategoryId={focusCategoryId}
                            ariaLabel={finding ?? undefined}
                        />
                    </ChartLens>
                    </div>
                )}
            </ChartCard>

            <div className="min-w-0 rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                <h2 className="flex items-baseline gap-2 text-title-sm font-normal text-ink">
                    Movimientos
                    {listed && (
                        <span className="tabular font-sans text-body-sm text-graphite">
                            {listed.length.toLocaleString("es-MX")}
                        </span>
                    )}
                </h2>

                {filtering && (
                    <p className="mt-2 text-label text-graphite">
                        El conjunto son estos criterios, no solo las filas visibles.
                        Destilda las excepciones.
                    </p>
                )}

                <PanelControls>
                    <PanelNumber
                        label="Mostrar"
                        unit="filas por página"
                        value={page}
                        min={MIN_PAGE}
                        max={MAX_PAGE}
                        onChange={(pageSize) => setListCfg({ pageSize })}
                    />
                </PanelControls>

                {items !== null && total > items.length && (
                    <p className="mt-2 text-label text-graphite">
                        Mostrando los {FETCH_CAP.toLocaleString("es-MX")} movimientos más
                        recientes de {total.toLocaleString("es-MX")}.
                    </p>
                )}

                <div className="mt-4">
                    {loading ? (
                        <div aria-hidden className="-mx-5 divide-y divide-mist border-t border-mist sm:-mx-6">
                            {Array.from({ length: 7 }).map((_, i) => (
                                <div key={i} className="flex items-center gap-3.5 px-5 py-3.5 sm:px-6">
                                    <Skeleton className="h-10 w-10 rounded-full" />
                                    <div className="flex-1 space-y-2">
                                        <Skeleton className="h-3.5 w-2/5" />
                                        <Skeleton className="h-3 w-16" />
                                    </div>
                                    <div className="flex flex-col items-end space-y-2">
                                        <Skeleton className="h-3.5 w-20" />
                                        <Skeleton className="h-3 w-28" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : listed.length === 0 ? (
                        <EmptyNote
                            narrowed={queryIsActive(query)}
                            ranged={timeWindow.kind === "custom"}
                            onClear={() => {
                                setQuery(EMPTY_QUERY);
                                clearCustom();
                            }}
                        />
                    ) : (
                        <TransactionsList
                            items={listed}
                            visibleCount={visibleCount}
                            onShowMore={() => {
                                track("movimientos.show_more", { visible: visibleCount + page });
                                setVisibleCount((c) => c + page);
                            }}
                            selectedId={selectedId}
                            onSelect={(id) => {
                                if (id) track("movimientos.row_select", { source: "list" });
                                handleSelect(id);
                            }}
                            attention={attentionByRow}
                            editing={{
                                onPatch: (t, patch) => patchItem(t.id, patch),
                                onBulkApplied: reload,
                            }}
                            membership={
                                filtering
                                    ? {
                                          excluded,
                                          onToggle: (id, inSet) => {
                                              setExcluded((cur) => {
                                                  const next = new Set(cur);
                                                  if (inSet) next.delete(id);
                                                  else next.add(id);
                                                  return next;
                                              });
                                          },
                                      }
                                    : undefined
                            }
                        />
                    )}
                </div>
            </div>

            {filtering && listed && (
                <LecturaDock
                    summary={`${(listed.length - excluded.size).toLocaleString("es-MX")} movimientos${
                        query.needle.trim() ? ` · contiene «${query.needle.trim()}»` : " · estos criterios"
                    }`}
                    chips={[
                        ...(query.needle.trim() ? [query.needle.trim()] : []),
                        ...(excluded.size
                            ? [
                                  excluded.size === 1
                                      ? "1 fuera"
                                      : `${excluded.size} fuera`,
                              ]
                            : []),
                    ]}
                    busy={opening}
                    onRead={() => {
                        const excludedIds = Array.from(excluded);
                        if (query.needle.trim()) {
                            const draft = draftFromNeedle(query.needle, excludedIds);
                            if (draft) void openDraft(draft);
                            return;
                        }
                        const ids = query.categoryIds.filter((id) => id !== UNCATEGORIZED);
                        if (ids.length === 0) return;
                        const draft = draftFromClauses(
                            ids.map((category_id) => ({ category_id })),
                            excludedIds,
                            ids.length === 1
                                ? categoryName(categories, ids[0]!)
                                : "Categorías"
                        );
                        if (draft) void openDraft(draft);
                    }}
                    onClear={() => {
                        setQuery(EMPTY_QUERY);
                        setExcluded(new Set());
                    }}
                />
            )}
        </div>
    );
}


function EmptyNote({
    narrowed = false,
    ranged = false,
    onClear,
}: {
    narrowed?: boolean;
    /** A chart-dragged range is on — the emptiness may be its doing. */
    ranged?: boolean;
    onClear: () => void;
}) {
    const empty = narrowed || ranged;
    return (
        <EmptyState
            icon={empty ? SearchX : Inbox}
            title={
                narrowed
                    ? "Nada coincide con estos criterios"
                    : ranged
                      ? "Sin movimientos en ese rango"
                      : "Sin movimientos en este periodo"
            }
            action={
                empty && (
                    <button
                        type="button"
                        onClick={onClear}
                        className="rounded-control px-3 py-1.5 text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                    >
                        Limpiar filtros
                    </button>
                )
            }
        >
            {empty
                ? "Los filtros están reduciendo lo que se dibuja."
                : "Prueba con un periodo más amplio, o sube un estado de cuenta que lo cubra."}
        </EmptyState>
    );
}

/** Local midnight, so the label is the day in the window and not the one before. */
function fromIso(day: string): Date {
    const [y, m, d] = day.split("-").map(Number);
    return new Date(y, m - 1, d);
}

/** v2: the lectura a fresh set opens on — the first warn, else the first. */
function defaultFocus(groups: LensGroup[]): LensFocus {
    for (const g of groups) {
        const index = g.lecturas.findIndex((l) => l.severity === "warn");
        if (index >= 0) return { groupId: g.id, index };
    }
    return groups[0]?.lecturas.length ? { groupId: groups[0].id, index: 0 } : null;
}

/** A merchant line short enough for a title. */
function shorten(description: string): string {
    const d = description.trim();
    return d.length > 28 ? `${d.slice(0, 27).trimEnd()}…` : d;
}

/** "Cargo inusual" → "Cargos inusuales"; the other labels pluralise by a plain s. */
function plural(label: string): string {
    const known: Record<string, string> = {
        "Cargo inusual": "Cargos inusuales",
        "Posible duplicado": "Posibles duplicados",
        "Comercio nuevo": "Comercios nuevos",
    };
    return known[label] ?? `${label}s`;
}
