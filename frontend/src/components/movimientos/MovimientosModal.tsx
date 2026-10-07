"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Inbox, Search, SearchX, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import { useSettings } from "@/components/settings/SettingsProvider";
import { resolveWindow } from "@/lib/window";
import { parseAnchor } from "@/lib/fechaCriterio";
import { useBankScope } from "@/lib/banks";
import { categoryName, useCategories } from "@/lib/categories";
import { track } from "@/lib/telemetry";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { useOverlay } from "@/components/ui/useOverlay";
import { usePortal } from "@/components/ui/usePortal";
import {
    EMPTY_QUERY,
    applyQuery,
    categoryLens,
    clearChip,
    periodChipLabel,
    queryChips,
    queryIsActive,
    type MovimientosQuery,
} from "@/lib/movimientosQuery";
import { useMovimientosSearch } from "./MovimientosSearchProvider";
import { CriteriosRail } from "./CriteriosRail";
import { ReclasificacionPanel } from "./ReclasificacionPanel";
import { TransactionsList } from "./TransactionsList";
import { useTransactions } from "./useTransactions";

const PAGE = 50;
type Phase = "enter" | "open" | "leave";

/**
 * Whether the criterios rail is folded. Per browser, not per session: someone
 * who works with it closed should not have to close it again tomorrow.
 */
const RAIL_KEY = "carguito.criterios.abierto";

function storedRailOpen(): boolean {
    try {
        return localStorage.getItem(RAIL_KEY) !== "0";
    } catch {
        // Storage blocked: open, which is the state that shows everything.
        return true;
    }
}

/**
 * The list, as a dialog. Grows from the header field; Escape commits and
 * collapses. Date is edited here and written to the TimeWindow only on close,
 * so the face underneath does not refetch while the user is still choosing.
 */
export function MovimientosModal({
    dataVersion,
    refresh,
}: {
    dataVersion: number;
    refresh: () => void;
}) {
    const {
        open,
        closeModal,
        query,
        setQuery,
        seedGen,
        transient,
        openingSeed,
        searchInputRef,
    } = useMovimientosSearch();
    const {
        bounds: windowBounds,
        window: timeWindow,
        selectCustom,
        selectPreset,
        clearCustom,
        anchor,
    } = useTimeWindow();
    const { settings } = useSettings();
    const { statementIds } = useBankScope(dataVersion);
    const categories = useCategories();
    const mounted = usePortal();

    const [render, setRender] = useState(false);
    const [phase, setPhase] = useState<Phase>("enter");
    const [draft, setDraft] = useState<MovimientosQuery>(query);
    const [start, setStart] = useState(windowBounds.start ?? "");
    const [end, setEnd] = useState(windowBounds.end ?? "");
    const [datesDirty, setDatesDirty] = useState(false);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [railOpen, setRailOpen] = useState(storedRailOpen);
    const [visibleCount, setVisibleCount] = useState(PAGE);
    const patched = useRef(false);
    const panelRef = useRef<HTMLDivElement>(null);

    const toggleRail = useCallback(() => {
        setRailOpen((cur) => {
            const next = !cur;
            try {
                localStorage.setItem(RAIL_KEY, next ? "1" : "0");
            } catch {
                // Nothing to remember it with; the session still honours it.
            }
            track("movimientos.criterios_rail", { open: next });
            return next;
        });
    }, []);
    const appliedGen = useRef(-1);

    if (open && !render) {
        setRender(true);
        setPhase("enter");
    }

    // Same render as `open`/`seedGen` — an effect can still see the previous
    // draft if React splits the context update.
    if (open && appliedGen.current !== seedGen) {
        appliedGen.current = seedGen;
        setDraft(openingSeed ?? query);
        setStart(windowBounds.start ?? "");
        setEnd(windowBounds.end ?? "");
        setDatesDirty(false);
        setSelectedId(null);
        setVisibleCount(PAGE);
        patched.current = false;
    }
    if (!open) appliedGen.current = -1;

    useLayoutEffect(() => {
        if (!render) return;
        if (open) {
            const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            if (reduce) {
                setPhase("open");
                return;
            }
            const force = window.setTimeout(() => setPhase("open"), 280);
            return () => window.clearTimeout(force);
        }
        setPhase("leave");
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const t = window.setTimeout(() => setRender(false), reduce ? 80 : 200);
        return () => window.clearTimeout(t);
    }, [open, render]);

    const fetchBounds = useMemo(() => {
        if (start && end) return start <= end ? { start, end } : { start: end, end: start };
        if (start) return { start, end: start };
        if (end) return { start: end, end };
        return {};
    }, [start, end]);

    const { items, total, error, reload, patchItem, loading } = useTransactions(
        fetchBounds,
        dataVersion,
        statementIds
    );

    /**
     * The rows the criterios select — plus the one whose panel is open.
     *
     * Reclassifying from inside the modal moves a row out of its own criterio:
     * filter by «Sin categoría», file a charge under Comida, and it stops
     * matching the instant the patch lands. Left to itself the list dropped it
     * mid-edit and the panel it was being edited in unmounted with it, so the
     * answer to "what did I just do" was an empty space where the row had been.
     *
     * So while a row is open it keeps its place, in its original position —
     * rebuilt off `items` rather than by appending, so the list does not
     * reshuffle under the cursor. Closing the panel is what lets it go, which
     * is also the moment the user has said they are done with it.
     */
    const view = useMemo(() => {
        if (items === null) return null;
        const matched = new Set(
            applyQuery(items, draft, categoryLens(categories)).map((t) => t.id)
        );
        // `held` is the open row surviving its own edit. Kept as a flag rather
        // than inferred later, because every count on this screen has to be
        // about the criterios — the row is on screen, but it is no longer one
        // of the answers, and a total that quietly included it would be wrong.
        // ...as long as it is still a row we have. A selection left over from
        // before a reload points at nothing, and holding a ghost would take a
        // row off the count for a row that is not drawn.
        const held =
            selectedId !== null &&
            !matched.has(selectedId) &&
            items.some((t) => t.id === selectedId);
        if (held) matched.add(selectedId!);
        return { rows: items.filter((t) => matched.has(t.id)), held };
    }, [items, draft, categories, selectedId]);

    const listed = view?.rows ?? null;
    const held = view?.held ?? false;

    useEffect(() => {
        setSelectedId(null);
        setVisibleCount(PAGE);
    }, [draft, start, end]);

    const commitAndClose = useCallback(() => {
        // Opened on a category from a chart: the criterios were the modal's
        // own, and the charts go back to what they showed before.
        if (!transient) setQuery(draft);
        if (datesDirty) {
            if (start && end) {
                const a = start <= end ? start : end;
                const b = start <= end ? end : start;
                selectCustom(a, b, "modal");
            } else {
                selectPreset("all");
            }
        }
        if (patched.current) refresh();
        track("movimientos.modal_close", {
            needle: Boolean(draft.needle.trim()),
            merchants: draft.merchantSlugs.length,
            categories: draft.categoryIds.length,
            amount: draft.amountBucket ?? "",
            kind: draft.kind,
            date_changed: datesDirty,
            transient,
        });
        closeModal();
    }, [
        draft,
        transient,
        datesDirty,
        start,
        end,
        setQuery,
        selectCustom,
        selectPreset,
        refresh,
        closeModal,
    ]);

    /**
     * «Quitar criterios» quits *every* criterio, the date included. The date
     * is the one the modal writes into the app's window on close, so clearing
     * only the draft left a custom range standing — and the faces outside kept
     * reading one month while the header said the criterios were gone. The
     * window goes back to the preset the user was on before the range, and
     * the modal's own dates follow it, so closing afterwards writes nothing.
     */
    const clearAll = useCallback(() => {
        const dateCleared = datesDirty || timeWindow.kind === "custom";
        setDraft(EMPTY_QUERY);
        if (timeWindow.kind === "custom") clearCustom();
        const fallback = resolveWindow(settings.lastWindow, parseAnchor(anchor));
        setStart(fallback.start ?? "");
        setEnd(fallback.end ?? "");
        setDatesDirty(false);
        track("movimientos.clear_criterios", { date_cleared: dateCleared });
    }, [datesDirty, timeWindow.kind, clearCustom, settings.lastWindow, anchor]);

    const selectedIdRef = useRef(selectedId);
    selectedIdRef.current = selectedId;
    const onEscape = useCallback(() => {
        if (selectedIdRef.current) {
            setSelectedId(null);
            return;
        }
        commitAndClose();
    }, [commitAndClose]);

    useOverlay(render, onEscape, panelRef);

    const selected = listed?.find((t) => t.id === selectedId) ?? null;

    const chips = queryChips(draft, (id) => categoryName(categories, id));
    const extra = queryIsActive(draft);
    // The date counts as a criterio to quit, even though it is not one the
    // empty state names: a range narrows the list exactly as a chip does.
    const clearable = extra || datesDirty || timeWindow.kind === "custom";
    const periodLabel = periodChipLabel(fetchBounds.start, fetchBounds.end);
    const shortcut = isApple() ? "⌘K" : "Ctrl K";

    if (!mounted || !render) return null;

    // What the criterios answer, which is one less than what is drawn while
    // a reclassified row is being held open.
    const count = (listed?.length ?? 0) - (held ? 1 : 0);

    return createPortal(
        <div className="fixed inset-0 z-modal flex items-center justify-center p-0 sm:p-6">
            <div
                onClick={commitAndClose}
                aria-hidden
                className={cn(
                    "movimientos-modal-scrim absolute inset-0 bg-soot/40",
                    phase === "enter" && "modal-enter",
                    phase === "leave" && "modal-leave",
                    phase === "open" && "is-open"
                )}
            />
            <div
                ref={panelRef}
                role="dialog"
                aria-modal="true"
                aria-label="Buscar un movimiento"
                tabIndex={-1}
                className={cn(
                    "movimientos-modal-panel relative flex h-dvh w-full flex-col overflow-hidden",
                    "bg-paper outline-none sm:h-[min(860px,90dvh)] sm:max-w-[min(1280px,94vw)] sm:rounded-panel sm:border sm:border-mist sm:shadow-float",
                    phase === "enter" && "modal-enter",
                    phase === "leave" && "modal-leave",
                    phase === "open" && "is-open"
                )}
            >
                <header className="shrink-0 border-b border-mist px-4 py-3 sm:px-5">
                    <div className="flex items-center gap-3">
                        <label
                            className={cn(
                                "flex h-11 min-w-0 flex-1 items-center gap-2.5 rounded-control border bg-paper px-4",
                                draft.needle.trim() ? "border-ink" : "border-muted",
                                "focus-within:border-ink"
                            )}
                        >
                            <Search size={18} aria-hidden className="shrink-0 text-graphite" />
                            <input
                                ref={searchInputRef}
                                type="search"
                                value={draft.needle}
                                onChange={(e) => {
                                    if (!draft.needle && e.target.value) track("movimientos.search");
                                    setDraft({ ...draft, needle: e.target.value });
                                }}
                                placeholder="Buscar un movimiento"
                                aria-label="Buscar un movimiento"
                                className={cn(
                                    "w-full bg-transparent text-body text-ink outline-none placeholder:text-ash",
                                    "[&::-webkit-search-cancel-button]:hidden"
                                )}
                            />
                            {draft.needle && (
                                <button
                                    type="button"
                                    aria-label="Limpiar búsqueda"
                                    onClick={() => setDraft({ ...draft, needle: "" })}
                                    className="-mr-1 rounded-full p-1 text-ash hover:text-ink"
                                >
                                    <X size={16} aria-hidden />
                                </button>
                            )}
                        </label>
                        <kbd className="hidden rounded-[4px] border border-mist bg-fog px-1.5 py-0.5 font-sans text-label font-medium text-graphite sm:inline">
                            {shortcut}
                        </kbd>
                        <span className="hidden text-label text-ash sm:inline">Esc cierra</span>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-graphite">
                        <span className="font-medium text-ink">La fecha tiene prioridad</span>
                        <span aria-hidden>·</span>
                        <span>
                            {loading && listed === null
                                ? "Leyendo el periodo…"
                                : `${count.toLocaleString("es-MX")} movimiento${count === 1 ? "" : "s"} en el periodo`}
                        </span>
                        {clearable && (
                            <button
                                type="button"
                                onClick={clearAll}
                                className="ml-auto underline decoration-mist underline-offset-4 hover:text-ink"
                            >
                                Quitar criterios
                            </button>
                        )}
                    </div>
                </header>

                <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
                    <div className="max-h-64 shrink-0 overflow-y-auto border-b border-mist lg:max-h-none lg:border-b-0">
                        <CriteriosRail
                            items={items}
                            query={draft}
                            onQuery={setDraft}
                            start={start}
                            end={end}
                            onDates={(a, b) => {
                                setStart(a);
                                setEnd(b);
                                setDatesDirty(true);
                            }}
                            categories={categories}
                            calendarResetKey={open}
                            dateAnchor={anchor}
                            open={railOpen}
                            onToggle={toggleRail}
                        />
                    </div>

                    <section className="flex min-h-0 min-w-0 flex-1 flex-col">
                        <div className="flex flex-wrap items-center gap-1.5 px-5 pt-4">
                            <Chip
                                label={periodLabel}
                                onClear={
                                    datesDirty
                                        ? () => {
                                              setStart(windowBounds.start ?? "");
                                              setEnd(windowBounds.end ?? "");
                                              setDatesDirty(false);
                                          }
                                        : undefined
                                }
                            />
                            {chips.map((chip) => (
                                <Chip
                                    key={chip.key}
                                    label={chip.label}
                                    onClear={() => setDraft(clearChip(draft, chip))}
                                />
                            ))}
                        </div>

                        <div className="mt-3 flex items-baseline justify-between px-5">
                            <h2 className="flex items-baseline gap-2 text-title-sm font-normal text-ink">
                                Movimientos
                                {listed && (
                                    <span className="tabular font-sans text-body-sm text-graphite">
                                        {count.toLocaleString("es-MX")}
                                    </span>
                                )}
                                {selectedId && (
                                    <span className="font-sans text-body-sm text-ash">
                                        · 1 en edición
                                        {held && ", ya fuera de estos criterios"}
                                    </span>
                                )}
                            </h2>
                            <p className="text-label text-ash">
                                {selected
                                    ? "Reclasificación abierta"
                                    : "Elige un movimiento para reclasificar"}
                            </p>
                        </div>

                        {error && (
                            <p className="px-5 pt-3 text-body-sm text-negative">{error}</p>
                        )}

                        {items !== null && total > items.length && (
                            <p className="px-5 pt-2 text-label text-graphite">
                                Mostrando los {items.length.toLocaleString("es-MX")} más recientes
                                de {total.toLocaleString("es-MX")}.
                            </p>
                        )}

                        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
                            {listed === null ? (
                                <ListSkeleton />
                            ) : listed.length === 0 ? (
                                <EmptyState
                                    icon={extra ? SearchX : Inbox}
                                    title={
                                        extra
                                            ? "Nada coincide con estos criterios"
                                            : "Sin movimientos en este periodo"
                                    }
                                    action={
                                        clearable ? (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={clearAll}
                                            >
                                                Quitar criterios
                                            </Button>
                                        ) : undefined
                                    }
                                >
                                    {extra
                                        ? "Los criterios están reduciendo lo que se lista."
                                        : "Prueba con un periodo más amplio, o sube un estado de cuenta que lo cubra."}
                                </EmptyState>
                            ) : (
                                <TransactionsList
                                    items={listed}
                                    visibleCount={visibleCount}
                                    onShowMore={() => setVisibleCount((c) => c + PAGE)}
                                    selectedId={selectedId}
                                    onSelect={(id) => {
                                        if (id) track("movimientos.row_select", { source: "modal" });
                                        setSelectedId(id);
                                    }}
                                    expandEditor={false}
                                    editing={{
                                        onPatch: (t, patch) => {
                                            patched.current = true;
                                            void patchItem(t.id, patch);
                                        },
                                        onBulkApplied: () => {
                                            patched.current = true;
                                            reload();
                                        },
                                    }}
                                />
                            )}
                        </div>
                    </section>

                    {selected && (
                        <div className="absolute inset-0 z-10 flex justify-end lg:static lg:z-auto lg:w-[380px] lg:shrink-0 lg:border-l lg:border-mist">
                            <button
                                type="button"
                                aria-label="Cerrar reclasificación"
                                onClick={() => setSelectedId(null)}
                                className="absolute inset-0 bg-soot/20 lg:hidden"
                            />
                            <div className="relative h-full w-full max-w-md border-l border-mist bg-paper lg:max-w-none lg:border-l-0">
                                <ReclasificacionPanel
                                    key={selected.id}
                                    transaction={selected}
                                    onPatch={(patch) => {
                                        patched.current = true;
                                        void patchItem(selected.id, patch);
                                    }}
                                    onBulkApplied={() => {
                                        patched.current = true;
                                        reload();
                                    }}
                                    onClose={() => setSelectedId(null)}
                                />
                            </div>
                        </div>
                    )}
                </div>

                <footer className="shrink-0 border-t border-mist px-5 py-2.5 text-label text-ash">
                    Al cerrar, el periodo se aplica a la vista. El resto de criterios vive
                    dentro de esa fecha.
                </footer>
            </div>
        </div>,
        document.body
    );
}

function Chip({ label, onClear }: { label: string; onClear?: () => void }) {
    return (
        <span className="inline-flex items-center gap-1 rounded-tag bg-fog py-0.5 pl-2 pr-1 text-label text-ink ring-1 ring-inset ring-mist">
            {label}
            {onClear && (
                <button
                    type="button"
                    aria-label={`Quitar ${label}`}
                    onClick={onClear}
                    className="rounded-full p-0.5 text-ash hover:text-ink"
                >
                    <X size={12} aria-hidden />
                </button>
            )}
        </span>
    );
}

function ListSkeleton() {
    return (
        <div aria-hidden className="-mx-5 divide-y divide-mist border-t border-mist">
            {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3.5 px-5 py-3.5">
                    <Skeleton className="h-10 w-10 rounded-full" />
                    <div className="flex-1 space-y-2">
                        <Skeleton className="h-3.5 w-2/5" />
                        <Skeleton className="h-5 w-28 rounded-tag" />
                    </div>
                    <div className="space-y-2 text-right">
                        <Skeleton className="ml-auto h-3.5 w-20" />
                        <Skeleton className="ml-auto h-3 w-16" />
                    </div>
                </div>
            ))}
        </div>
    );
}

function isApple(): boolean {
    if (typeof navigator === "undefined") return true;
    return /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
}
