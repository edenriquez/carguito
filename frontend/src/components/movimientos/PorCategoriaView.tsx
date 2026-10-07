"use client";

import { useMemo, useState } from "react";
import { Shapes } from "lucide-react";
import { useAppData } from "@/components/AppChrome";
import { BackendNotice, EmptyState, Skeleton } from "@/components/ui";
import { useBankScope } from "@/lib/banks";
import { useCategories } from "@/lib/categories";
import { composeCategories, repeatedCharges, sliceColor } from "@/lib/categoryComposition";
import { mxn2 } from "@/lib/format";
import { pct } from "@/lib/categoryComposition";
import { applyQuery, categoryLens, UNCATEGORIZED } from "@/lib/movimientosQuery";
import { track } from "@/lib/telemetry";
import { useMovimientosSearch } from "./MovimientosSearchProvider";
import { useAttention } from "./useAttention";
import { useTransactions } from "./useTransactions";
import { CompositionBar } from "./CompositionBar";
import { CategoryAccordion } from "./CategoryAccordion";

/**
 * Entender el conjunto, in two beats down the page: the same cargos as one
 * bar, then every category under it, openable all the way down to the charge.
 *
 * There used to be a third beat above both — a card stating the reading in a
 * sentence, with the period, the totals and a "por revisar" badge. It said
 * nothing the bar and the list below did not already say in their own terms,
 * and it pushed the actual reading a screenful down. The work it carried is
 * where the work is: "Sin categoría" is pinned at the top of the list with
 * its own Revisar button.
 *
 * Lista is still the modal — a group here opens it already filtered.
 */
export function PorCategoriaView({
}: {
} = {}) {
    const { bounds, dataVersion } = useAppData();
    const { statementIds } = useBankScope(dataVersion);
    const categories = useCategories();
    const { query, openModal } = useMovimientosSearch();
    const { items, error, loading } = useTransactions(bounds, dataVersion, statementIds);
    // The same rings the scatter draws, in the same scope: a charge flagged
    // here and flagged there is the one charge, not two opinions.
    const { items: attention } = useAttention(bounds, dataVersion, statementIds);
    const [openKey, setOpenKey] = useState<string | null>(null);

    const listed = useMemo(
        () =>
            items === null ? null : applyQuery(items, query, categoryLens(categories)),
        [items, query, categories]
    );
    const composition = useMemo(
        () => (listed ? composeCategories(listed, categories) : null),
        [listed, categories]
    );
    const repeats = useMemo(() => (listed ? repeatedCharges(listed) : new Set<string>()), [listed]);
    const attentionByRow = useMemo(
        () => new Map(attention.map((a) => [a.transaction_id, a.kind])),
        [attention]
    );

    // The title is the concentration of the spend, from the bar's own
    // ranking — the window's totals, biggest first.
    const finding = useMemo(() => {
        if (!composition) return null;
        const named = composition.bar.filter((s) => !s.uncategorized);
        const top = named[0];
        if (!top) return null;
        const head = `${top.name} concentra ${pct(top.share)}% de tu gasto`;
        const n = Math.min(3, named.length);
        if (n < 2) return head;
        const share = named.slice(0, n).reduce((s, x) => s + x.share, 0);
        return `${head}; las ${n === 3 ? "3" : "2"} primeras, ${pct(share)}%`;
    }, [composition]);

    function toggle(key: string) {
        setOpenKey((cur) => (cur === key ? null : key));
        track("movimientos.category_expand", { open: openKey !== key });
    }

    function verMas(key: string) {
        const next = {
            ...query,
            // `key` is already the canonical id — the accordion's
            // uncategorized slice is keyed UNCATEGORIZED, same as the rail's
            // option and the same as what applyQuery matches on.
            categoryIds: [key],
        };
        openModal("revisar", next);
    }

    if (error) {
        return (
            <div className="space-y-4">
                <BackendNotice what="tus categorías" detail={error} />
            </div>
        );
    }

    if (loading || listed === null || composition === null) {
        return <PorCategoriaSkeleton />;
    }

    if (composition.spendCount === 0 && composition.incomeCount === 0) {
        return (
            <div className="space-y-4">
                <EmptyState icon={Shapes} title="Ningún cargo en este periodo">
                    Prueba con un periodo más amplio, o quita criterios.
                </EmptyState>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <section className="card">
                <div className="mb-5 min-w-0">
                    {finding && <p className="eyebrow">Por categoría</p>}
                    <h2 className={finding ? "mt-1 text-title-sm font-normal text-ink" : "text-title-sm font-normal text-ink"}>
                        {finding ?? "Por categoría"}
                    </h2>
                    <p className="mt-1 text-body-sm text-graphite">
                        {composition.bar.length} categoría{composition.bar.length === 1 ? "" : "s"} ·{" "}
                        {composition.spendCount} cargo{composition.spendCount === 1 ? "" : "s"} ·{" "}
                        <span className="tabular text-ink">{mxn2(composition.spend)}</span> en el
                        periodo
                    </p>
                </div>
                <CompositionBar
                    slices={composition.bar}
                    activeKey={openKey}
                    onPick={toggle}
                    {...(finding && { label: finding })}
                    colorOf={(slice) => sliceColor(slice, categories)}
                />
                <p className="mt-3 text-label text-ash">
                    Base: cargos del periodo, sin «Entre mis cuentas» ni excluidos.
                </p>
            </section>

            <section className="min-w-0 overflow-hidden rounded-card border border-mist bg-paper shadow-card">
                <CategoryAccordion
                    slices={composition.slices}
                    openKey={openKey}
                    onToggle={toggle}
                    onVerMas={verMas}
                    attention={attentionByRow}
                    repeats={repeats}
                    spend={composition.spend}
                    movementCount={composition.movementCount}
                    aux={{
                        abonos: composition.abonos,
                        income: composition.income,
                        aparte: composition.aparte,
                        aparteTotal: composition.aparteTotal,
                    }}
                />
            </section>
        </div>
    );
}

/** The face's geometry before its data: the reading card (title, count line,
 *  the composition bar, the base note) and the category accordion under it. */
function PorCategoriaSkeleton() {
    return (
        <div className="space-y-5" aria-busy>
            <section className="card">
                <div className="mb-5 space-y-2">
                    <Skeleton className="h-6 w-36" />
                    <Skeleton className="h-4 w-64 max-w-full" />
                </div>
                <Skeleton className="h-10 w-full" />
                <Skeleton className="mt-3 h-3 w-72 max-w-full" />
            </section>
            <section className="rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                {Array.from({ length: 7 }).map((_, i) => (
                    <Skeleton key={i} className="my-3 h-11" />
                ))}
            </section>
        </div>
    );
}
