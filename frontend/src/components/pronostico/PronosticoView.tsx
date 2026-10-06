"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Plus, Scale, X } from "lucide-react";
import { api, type RecurringItem, type Transaction } from "@/lib/api";
import { useBankScope } from "@/lib/banks";
import { cn } from "@/lib/cn";
import { colors } from "@/design/tokens";
import {
    HORIZONS,
    pinnedItems,
    reconcileFijos,
    restMonthlyFromTransactions,
    type Horizon,
} from "@/lib/fijos";
import { dayLabel, mxn, mxn2 } from "@/lib/format";
import {
    clusterIncome,
    labeledIncomeItems,
    type IncomeCluster,
    type IncomeKind,
} from "@/lib/ingresos";
import { parsePeriodKey } from "@/lib/metrics";
import { track } from "@/lib/telemetry";
import { useAppData } from "@/components/AppChrome";
import { ChartCard } from "@/components/ChartCard";
import { useFijos } from "@/components/fijos/useFijos";
import { buildTimeline, type Timeline } from "@/components/recurrentes/projection";
import { BackendNotice, Button, Checkbox, EmptyState, Skeleton } from "@/components/ui";
import { LecturaDock } from "@/components/lectura/LecturaDock";
import { useLectura } from "@/components/lectura/LecturaProvider";
import { draftFromClauses, MAX_LECTURA_CLAUSES } from "@/lib/lectura";
import { AddIngresoSheet } from "./AddIngresoSheet";
import { ContrastChart, CONTRAST_COLORS, contrastFinding } from "./ContrastChart";
import { useChartsV2 } from "@/lib/chartsV2";
import { useIngresos } from "./useIngresos";

const MONTHS_BACK = 12;

const FREQUENCY_LABELS: Record<RecurringItem["frequency"], string> = {
    weekly: "Semanal",
    biweekly: "Quincenal",
    monthly: "Mensual",
    bimonthly: "Bimestral",
    semiannual: "Semestral",
    yearly: "Anual",
};

/**
 * Labeled income against the fijos need, on the same 6/12 horizon.
 * Nothing is guessed: a deposit counts only after you name it.
 */
export function PronosticoView({ onGoToFijos }: { onGoToFijos?: () => void } = {}) {
    const { dataVersion } = useAppData();
    const [items, setItems] = useState<RecurringItem[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [ledger, setLedger] = useState<Transaction[] | null>(null);
    const [adding, setAdding] = useState(false);
    const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
    const { openDraft, opening } = useLectura();

    const fijos = useFijos();
    const ingresos = useIngresos();
    // Labelling a deposit is the one act this face asks for; how often it
    // happens, and how often it is undone, is the measure of the face.
    const labelIncome = useCallback(
        (key: string, kind: IncomeKind) => {
            track("plan.ingreso_label", { kind });
            ingresos.label(key, kind);
        },
        [ingresos]
    );
    const unlabelIncome = useCallback(
        (key: string) => {
            track("plan.ingreso_unlabel");
            ingresos.unlabel(key);
        },
        [ingresos]
    );
    const setHorizon = useCallback(
        (h: Horizon) => {
            track("plan.horizon", { horizon: h, face: "ingresos" });
            fijos.setHorizon(h);
        },
        [fijos]
    );
    const { statementIds } = useBankScope(dataVersion);
    const scopeQuery = statementIds
        ? `?${statementIds.map((id) => `statement_id=${id}`).join("&")}`
        : "";

    useEffect(() => {
        let stale = false;
        api.recurring(scopeQuery)
            .then((res) => {
                if (stale) return;
                setItems(res.items.map((i) => ({ ...i, key: i.key || i.label })));
                setError(null);
            })
            .catch((e) => {
                if (stale) return;
                setError((e as Error).message);
                setItems([]);
            });
        return () => {
            stale = true;
        };
    }, [dataVersion, scopeQuery]);

    useEffect(() => {
        let stale = false;
        const params = new URLSearchParams();
        params.set("limit", "10000");
        for (const id of statementIds ?? []) params.append("statement_id", id);
        api.transactions(`?${params}`)
            .then((page) => {
                if (!stale) setLedger(page.items);
            })
            .catch(() => {
                if (!stale) setLedger([]);
            });
        return () => {
            stale = true;
        };
    }, [dataVersion, statementIds]);

    useEffect(() => {
        if (!fijos.hydrated || !items) return;
        const next = reconcileFijos(fijos.state, items);
        if (next !== fijos.state) fijos.replace(next);
    }, [fijos.hydrated, fijos.state, fijos.replace, items]);

    const loading = items === null || ledger === null || !fijos.hydrated || !ingresos.hydrated;
    const detected = items ?? [];
    const txs = ledger ?? [];
    const horizon = fijos.state.horizon;

    const clusters = useMemo(() => clusterIncome(txs), [txs]);
    const labeledKeys = useMemo(
        () => new Set(ingresos.state.labeled.map((l) => l.key)),
        [ingresos.state.labeled]
    );
    const kindOf = useMemo(() => {
        const m = new Map<string, IncomeKind>();
        for (const l of ingresos.state.labeled) m.set(l.key, l.kind);
        return m;
    }, [ingresos.state.labeled]);

    const { nomina: nominaItems, extra: extraItems } = useMemo(
        () => labeledIncomeItems(ingresos.state, clusters),
        [ingresos.state, clusters]
    );

    const fijosPinned = useMemo(
        () => pinnedItems(fijos.state, detected, txs),
        [fijos.state, detected, txs]
    );

    const fijosTl = useMemo(
        () => buildTimeline(fijosPinned, MONTHS_BACK, horizon),
        [fijosPinned, horizon]
    );
    const nominaTl = useMemo(
        () => buildTimeline(nominaItems, MONTHS_BACK, horizon),
        [nominaItems, horizon]
    );
    const extraTl = useMemo(
        () => buildTimeline(extraItems, MONTHS_BACK, horizon),
        [extraItems, horizon]
    );

    const contrast = useMemo(
        () => ({
            months: fijosTl.months,
            firstFutureIndex: fijosTl.firstFutureIndex,
            nomina: monthTotals(nominaTl, fijosTl.months),
            extra: monthTotals(extraTl, fijosTl.months),
            fijos: monthTotals(fijosTl, fijosTl.months),
        }),
        [fijosTl, nominaTl, extraTl]
    );

    // v2: the chart's title states its finding; the metric's name moves under it.
    const v2 = useChartsV2();
    const contrastTitle = v2 ? contrastFinding(contrast)?.title : undefined;

    const income = nominaTl.totals.projected + extraTl.totals.projected;
    const need = fijosTl.totals.projected;
    const nominaNeed = nominaTl.totals.projected;
    const extraNeed = extraTl.totals.projected;

    const nominaClusters = clusters.filter((c) => kindOf.get(c.key) === "nomina");
    const extraClusters = clusters.filter((c) => kindOf.get(c.key) === "extra");
    const unlabeled = clusters.filter((c) => !labeledKeys.has(c.key));

    const emptyLedger = !loading && clusters.length === 0 && fijosPinned.length === 0;

    // The deposit most likely to be the salary, offered by name. "Hay 10 sin
    // etiquetar" is honest; "¿VECH SOLUCIONES es tu nómina?" is actionable.
    const candidate = useMemo(() => {
        let best: { cluster: IncomeCluster; monthly: number; count: number } | null = null;
        for (const c of unlabeled) {
            const monthly = restMonthlyFromTransactions(c.txs).monthly;
            if (!best || monthly > best.monthly) best = { cluster: c, monthly, count: c.txs.length };
        }
        return best;
    }, [unlabeled]);

    function toggleIncome(key: string, on: boolean) {
        setSelectedKeys((cur) => {
            const next = new Set(cur);
            if (on) next.add(key);
            else next.delete(key);
            return next;
        });
    }

    const selectedClusters = clusters.filter((c) => selectedKeys.has(c.key));

    return (
        <div className="space-y-4 sm:space-y-6">
            {error && <BackendNotice what="tus ingresos" detail={error} />}

            {emptyLedger ? (
                <EmptyState
                    icon={Scale}
                    title="Aún no hay abonos que etiquetar"
                    action={
                        onGoToFijos && (
                            <Button variant="ghost" size="sm" onClick={onGoToFijos}>
                                Ir a gastos fijos
                            </Button>
                        )
                    }
                >
                    Sube un estado de cuenta con abonos, o fija cargos en «Lo que se
                    va» para contrastarlos.
                </EmptyState>
            ) : (
                <>
                    <Headline
                        income={income}
                        nomina={nominaNeed}
                        extra={extraNeed}
                        need={need}
                        horizon={horizon}
                        loading={loading}
                        onHorizon={setHorizon}
                        labeledCount={nominaClusters.length + extraClusters.length}
                        unlabeledCount={unlabeled.length}
                        candidate={candidate}
                        onLabelCandidate={(key) => labelIncome(key, "nomina")}
                        pinnedCount={fijosPinned.length}
                        onGoToFijos={onGoToFijos}
                    />

                    <ChartCard
                        title={contrastTitle ?? "Ingresos contra fijos"}
                        subtitle={contrastTitle ? "Ingresos contra fijos" : undefined}
                    >
                        {loading ? (
                            <Skeleton className="h-[300px]" />
                        ) : (
                            <ContrastChart data={contrast} />
                        )}
                    </ChartCard>

                    <IncomeSection
                        title="Nómina"
                        hint="Ingresos con ritmo. Si hay quincena o mes, abono a abono."
                        clusters={nominaClusters}
                        itemsByKey={byClusterKey(nominaItems)}
                        loading={loading}
                        empty="Etiqueta un abono como nómina para que entre al número."
                        onRelabel={labelIncome}
                        onUnlabel={unlabelIncome}
                        kind="nomina"
                        selectedKeys={selectedKeys}
                        onSelect={toggleIncome}
                        action={
                            <Button
                                variant="ghost"
                                size="sm"
                                icon={<Plus size={14} />}
                                onClick={() => setAdding(true)}
                            >
                                Etiquetar
                            </Button>
                        }
                    />

                    <IncomeSection
                        title="Extra"
                        hint="Ingresos sin promesa de fecha. Entra el mes típico de cada uno."
                        clusters={extraClusters}
                        itemsByKey={byClusterKey(extraItems)}
                        loading={loading}
                        empty="Un extra etiquetado aparece aquí."
                        onRelabel={labelIncome}
                        onUnlabel={unlabelIncome}
                        kind="extra"
                        selectedKeys={selectedKeys}
                        onSelect={toggleIncome}
                    />

                    <IncomeSection
                        title="Sin etiquetar"
                        hint="Están en tus movimientos. Hasta que los nombras, no cuentan."
                        clusters={unlabeled}
                        itemsByKey={new Map()}
                        loading={loading}
                        empty="Todos tus ingresos ya tienen nombre."
                        onRelabel={labelIncome}
                        kind="unlabeled"
                    />
                </>
            )}

            {selectedClusters.length > 0 && (
                <LecturaDock
                    summary={
                        selectedClusters.length === 1
                            ? "1 ingreso"
                            : `${selectedClusters.length} ingresos`
                    }
                    chips={selectedClusters.slice(0, MAX_LECTURA_CLAUSES).map((c) => c.label)}
                    busy={opening}
                    onRead={() => {
                        const draft = draftFromClauses(
                            selectedClusters.map((c) => ({
                                description_contains: c.label,
                            })),
                            [],
                            selectedClusters.map((c) => c.label).join(" + ")
                        );
                        if (draft) void openDraft(draft);
                    }}
                    onClear={() => setSelectedKeys(new Set())}
                />
            )}

            <AddIngresoSheet
                open={adding}
                onClose={() => setAdding(false)}
                ledger={txs}
                labeledKeys={labeledKeys}
                onLabel={labelIncome}
            />
        </div>
    );
}

function Headline({
    income,
    nomina,
    extra,
    need,
    horizon,
    loading,
    onHorizon,
    labeledCount,
    unlabeledCount,
    pinnedCount,
    onGoToFijos,
    candidate,
    onLabelCandidate,
}: {
    income: number;
    nomina: number;
    extra: number;
    need: number;
    horizon: Horizon;
    loading: boolean;
    onHorizon: (h: Horizon) => void;
    /** Deposit clusters the user has named nómina or extra. */
    labeledCount: number;
    /** Deposit clusters still waiting for a name. */
    unlabeledCount: number;
    /** Fijos pinned on the other face — the thing income is measured against. */
    pinnedCount: number;
    onGoToFijos?: () => void;
    /** The largest unlabeled deposit series, to be offered as the salary. */
    candidate?: { cluster: IncomeCluster; monthly: number; count: number } | null;
    onLabelCandidate?: (key: string) => void;
}) {
    const gap = income - need;
    const gapWord = gap > 0.5 ? "Sobra" : gap < -0.5 ? "Faltan" : "Tablas";
    // Nothing labelled is an absence, not an income of zero pesos. The
    // headline says what is missing and how much of it there is to do.
    const unknown = !loading && labeledCount === 0;
    // The gap is a comparison, so it needs both sides to exist.
    const comparable = !loading && labeledCount > 0 && pinnedCount > 0;

    return (
        <section className="min-w-0 rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                    <p className="eyebrow">Ingresos</p>
                    {loading ? (
                        <Skeleton className="mt-1 h-9 w-48" />
                    ) : unknown ? (
                        <p className="mt-0.5 font-display text-title-md font-normal text-ink">
                            Tomin no adivina
                        </p>
                    ) : (
                        <p className="tabular mt-0.5 text-metric font-normal text-ink">
                            {mxn(income)}
                        </p>
                    )}
                    <p className="mt-1 text-body text-graphite">
                        {unknown
                            ? unlabeledCount > 0
                                ? `Sin una nómina etiquetada no hay número. Hay ${unlabeledCount} abono${unlabeledCount === 1 ? "" : "s"} sin etiquetar.`
                                : "Sin una nómina etiquetada no hay número. Sube un estado de cuenta con abonos y etiqueta tu nómina."
                            : `en los próximos ${horizon} meses`}
                    </p>
                    {!loading && !unknown && (
                        <p className="mt-2 text-body-sm text-graphite">
                            {nomina > 0 && <>Nómina {mxn(nomina)}</>}
                            {nomina > 0 && extra > 0 && <span className="text-ash"> · </span>}
                            {extra > 0 && <>Extra {mxn(extra)}</>}
                            <span className="text-ash"> · </span>
                            {pinnedCount > 0 ? (
                                <>Fijos {mxn(need)}</>
                            ) : onGoToFijos ? (
                                <button
                                    type="button"
                                    onClick={onGoToFijos}
                                    className="underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                                >
                                    Fija tus cargos para saber si alcanza
                                </button>
                            ) : (
                                <>Sin fijos fijados</>
                            )}
                            {comparable && (
                                <>
                                    <span className="text-ash"> · </span>
                                    <span className={gap < -0.5 ? "text-negative" : gap > 0.5 ? "text-positive" : undefined}>
                                        {gapWord} {mxn(Math.abs(gap))}
                                    </span>
                                </>
                            )}
                        </p>
                    )}
                    {unknown && candidate && onLabelCandidate && (
                        <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-body-sm text-graphite">
                            <span>
                                El mayor: <span className="text-ink">{candidate.cluster.label}</span>,{" "}
                                ~{mxn(candidate.monthly)}/mes en {candidate.count} abono
                                {candidate.count === 1 ? "" : "s"}. ¿Es tu nómina?
                            </span>
                            <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => onLabelCandidate(candidate.cluster.key)}
                            >
                                Sí, es mi nómina
                            </Button>
                        </p>
                    )}
                    {unknown && pinnedCount > 0 && (
                        <p className="mt-2 text-body-sm text-graphite">
                            Fijos comprometidos: {mxn(need)} en los próximos {horizon} meses.
                        </p>
                    )}
                </div>

                <div className="flex flex-col items-end gap-3">
                    {onGoToFijos && !loading && (
                        <button
                            type="button"
                            onClick={onGoToFijos}
                            className="text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                        >
                            ← Ver gastos fijos
                        </button>
                    )}
                    <div
                        role="radiogroup"
                        aria-label="Horizonte"
                        className="inline-flex rounded-control border border-mist bg-paper p-0.5"
                    >
                        {HORIZONS.map((h) => {
                            const selected = horizon === h;
                            return (
                                <button
                                    key={h}
                                    type="button"
                                    role="radio"
                                    aria-checked={selected}
                                    onClick={() => onHorizon(h)}
                                    className={cn(
                                        "rounded-control px-3 py-1 text-body-sm",
                                        "transition-colors duration-100",
                                        selected
                                            ? "bg-fog font-medium text-ink"
                                            : "text-graphite hover:text-ink"
                                    )}
                                >
                                    {h} meses
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>
        </section>
    );
}

function IncomeSection({
    title,
    hint,
    clusters,
    itemsByKey,
    loading,
    empty,
    onRelabel,
    onUnlabel,
    kind,
    action,
    selectedKeys,
    onSelect,
}: {
    title: string;
    hint: string;
    clusters: IncomeCluster[];
    itemsByKey: Map<string, RecurringItem>;
    loading: boolean;
    empty: string;
    onRelabel: (key: string, kind: IncomeKind) => void;
    onUnlabel?: (key: string) => void;
    kind: IncomeKind | "unlabeled";
    action?: ReactNode;
    selectedKeys?: Set<string>;
    onSelect?: (key: string, on: boolean) => void;
}) {
    return (
        <section className="min-w-0 rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-title-sm font-normal text-ink">
                    {title}
                    {clusters.length > 0 && (
                        <span className="ml-2 font-sans text-body-sm text-graphite">
                            {clusters.length}
                        </span>
                    )}
                </h2>
                {action}
            </div>
            <p className="mt-1 text-body-sm text-graphite">{hint}</p>
            <div className="mt-4">
                {loading ? (
                    <div className="space-y-2">
                        {[0, 1].map((i) => (
                            <Skeleton key={i} className="h-12" />
                        ))}
                    </div>
                ) : clusters.length === 0 ? (
                    <p className="py-6 text-body text-graphite">{empty}</p>
                ) : (
                    <ul className="divide-y divide-mist">
                        {clusters.map((c) => (
                            <IncomeRow
                                key={c.key}
                                cluster={c}
                                item={itemsByKey.get(c.key)}
                                kind={kind}
                                onRelabel={onRelabel}
                                onUnlabel={onUnlabel}
                                selected={selectedKeys?.has(c.key)}
                                onSelect={onSelect}
                            />
                        ))}
                    </ul>
                )}
            </div>
        </section>
    );
}

function IncomeRow({
    cluster,
    item,
    kind,
    onRelabel,
    onUnlabel,
    selected,
    onSelect,
}: {
    cluster: IncomeCluster;
    item?: RecurringItem;
    kind: IncomeKind | "unlabeled";
    onRelabel: (key: string, k: IncomeKind) => void;
    onUnlabel?: (key: string) => void;
    selected?: boolean;
    onSelect?: (key: string, on: boolean) => void;
}) {
    const [open, setOpen] = useState(false);
    const preview = restMonthlyFromTransactions(cluster.txs);
    const last = cluster.txs[0];
    const smear = item?.key.startsWith("ingreso:smear:");
    const swatch =
        kind === "nomina"
            ? CONTRAST_COLORS.nomina
            : kind === "extra"
              ? CONTRAST_COLORS.extra
              : colors.ash;

    return (
        <li>
            <div className="flex items-start gap-2 py-2.5">
                {onSelect && selected !== undefined && (
                    <span className="pt-1">
                        <Checkbox
                            checked={selected}
                            onChange={(on) => onSelect(cluster.key, on)}
                            aria-label={`Incluir ${cluster.label} en la lectura`}
                        />
                    </span>
                )}
                <button
                    type="button"
                    onClick={() => setOpen((v) => !v)}
                    aria-expanded={open}
                    className="min-w-0 flex-1 text-left"
                >
                    <div className="flex items-center justify-between gap-3">
                        <span className="flex min-w-0 items-center gap-2">
                            <span
                                aria-hidden
                                className="h-2 w-2 shrink-0 rounded-full"
                                style={{ background: swatch }}
                            />
                            <span className="truncate text-body text-ink">{cluster.label}</span>
                        </span>
                        <span className="tabular shrink-0 whitespace-nowrap text-body-sm text-ink">
                            {item && !item.amount_stable ? "~" : ""}
                            {mxn2(item?.typical_amount ?? Math.abs(last?.amount ?? 0))}
                        </span>
                    </div>
                    <div className="mt-0.5 pl-4 text-body-sm text-graphite">
                        {item
                            ? smear
                                ? `Sin fecha fija · ${mxn(item.monthly_equivalent)}/mes`
                                : `${FREQUENCY_LABELS[item.frequency]} · ${mxn(item.monthly_equivalent)}/mes`
                            : `${cluster.txs.length} abono${cluster.txs.length === 1 ? "" : "s"} · ~${mxn(preview.monthly)}/mes`}
                    </div>
                </button>
                {kind === "unlabeled" ? (
                    <span className="flex shrink-0 items-center gap-1">
                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => onRelabel(cluster.key, "nomina")}
                        >
                            Nómina
                        </Button>
                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => onRelabel(cluster.key, "extra")}
                        >
                            Extra
                        </Button>
                    </span>
                ) : (
                    <span className="flex shrink-0 items-center gap-1">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                                onRelabel(cluster.key, kind === "nomina" ? "extra" : "nomina")
                            }
                        >
                            {kind === "nomina" ? "Extra" : "Nómina"}
                        </Button>
                        <button
                            type="button"
                            onClick={() => onUnlabel?.(cluster.key)}
                            aria-label={`Quitar etiqueta de ${cluster.label}`}
                            title="Quitar etiqueta"
                            className="rounded-control p-1.5 text-graphite hover:bg-fog hover:text-ink"
                        >
                            <X size={14} aria-hidden />
                        </button>
                    </span>
                )}
            </div>
            {open && (
                <ul className="space-y-1 pb-3 pl-4">
                    {cluster.txs.slice(0, 6).map((t) => (
                        <li
                            key={t.id}
                            className="flex items-baseline justify-between gap-3 text-body-sm"
                        >
                            <span className="min-w-0 truncate text-graphite">
                                {isoToLabel(t.date)}
                                <span className="text-ash"> · </span>
                                {t.description}
                            </span>
                            <span className="tabular shrink-0 text-ink">{mxn2(Math.abs(t.amount))}</span>
                        </li>
                    ))}
                </ul>
            )}
        </li>
    );
}

function monthTotals(timeline: Timeline, months: string[]): number[] {
    return months.map((m) => {
        const at = timeline.months.indexOf(m);
        if (at < 0) return 0;
        return timeline.series.reduce((sum, s) => sum + (s.values[at] ?? 0), 0);
    });
}

function byClusterKey(items: RecurringItem[]): Map<string, RecurringItem> {
    const m = new Map<string, RecurringItem>();
    for (const i of items) {
        const key = i.key.replace(/^ingreso:(smear:)?/, "");
        m.set(key, i);
    }
    return m;
}

function isoToLabel(iso: string): string {
    const d = parsePeriodKey(iso);
    return d ? dayLabel(d) : iso;
}

