"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type RecurringItem, type Transaction } from "@/lib/api";
import { useBankScope } from "@/lib/banks";
import { cn } from "@/lib/cn";
import { type Frequency, type ManualFijo, type RestMark, restMarkFromTransaction, restMonthlyFromTransactions, seriesKeyFromDescription, transactionMatchesRest } from "@/lib/fijos";
import { dayLabel, mxn, mxn2 } from "@/lib/format";
import { parsePeriodKey } from "@/lib/metrics";
import { Button, SearchInput, Sheet } from "@/components/ui";

const FREQUENCY_LABELS: Record<Frequency, string> = {
    weekly: "Semanal",
    biweekly: "Quincenal",
    monthly: "Mensual",
    bimonthly: "Bimestral",
    semiannual: "Semestral",
    yearly: "Anual",
};

/**
 * Search the ledger for a charge detection missed. Intent `fijo` names a
 * cadence and pins it. Intent `resto` groups the merchant (Walmart, not one
 * ticket) and smears the typical month — no fake landing date.
 */
export function AddFijoSheet({
    open,
    onClose,
    intent = "fijo",
    detected,
    dataVersion,
    onPin,
    onAddManual,
    onAddRest,
    onPinRest,
}: {
    open: boolean;
    onClose: () => void;
    intent?: "fijo" | "resto";
    detected: RecurringItem[];
    dataVersion: number;
    onPin: (key: string) => void;
    onAddManual: (manual: ManualFijo) => void;
    onAddRest?: (mark: RestMark) => void;
    onPinRest?: (mark: RestMark) => void;
}) {
    const { statementIds } = useBankScope(dataVersion);
    const [items, setItems] = useState<Transaction[] | null>(null);
    const [query, setQuery] = useState("");
    const [picked, setPicked] = useState<Transaction | null>(null);
    const [frequency, setFrequency] = useState<Frequency>("monthly");

    useEffect(() => {
        if (!open) return;
        let stale = false;
        const params = new URLSearchParams();
        params.set("limit", "10000");
        for (const id of statementIds ?? []) params.append("statement_id", id);
        api.transactions(`?${params}`)
            .then((page) => {
                if (stale) return;
                setItems(page.items.filter((t) => t.type === "expense" && !t.is_transfer && !t.excluded_from_stats));
            })
            .catch(() => {
                if (!stale) setItems([]);
            });
        return () => {
            stale = true;
        };
    }, [open, dataVersion, statementIds]);

    useEffect(() => {
        if (!open) {
            setQuery("");
            setPicked(null);
            setFrequency("monthly");
        }
    }, [open]);

    const matchFor = (t: Transaction): RecurringItem | undefined => {
        const raw = t.raw_description || t.description;
        const key = seriesKeyFromDescription(raw);
        const byKey = detected.find((i) => i.key === key);
        if (byKey) return byKey;
        return detected.find((i) =>
            (i.charges ?? []).some(
                (c) => c.date === t.date && Math.abs(c.amount - Math.abs(t.amount)) < 0.01
            )
        );
    };

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        const pool = items ?? [];
        if (!q) return pool.slice(0, 40);
        return pool
            .filter((t) => t.description.toLowerCase().includes(q) || (t.raw_description ?? "").toLowerCase().includes(q))
            .slice(0, 40);
    }, [items, query]);

    const existing = picked ? matchFor(picked) : undefined;
    const restMark = picked ? restMarkFromTransaction(picked) : null;
    const restCluster = useMemo(() => {
        if (!restMark || !items) return [];
        return items.filter((t) => transactionMatchesRest(t, restMark));
    }, [restMark, items]);
    const restPreview = restCluster.length
        ? restMonthlyFromTransactions(restCluster)
        : null;
    const irregular =
        !!restMark && (restMark.merchant !== null || restCluster.length >= 2);

    function confirm() {
        if (!picked) return;
        if (intent === "resto") {
            if (existing) {
                onClose();
                return;
            }
            if (restMark) onAddRest?.(restMark);
            onClose();
            return;
        }
        if (existing) {
            onPin(existing.key);
            onClose();
            return;
        }
        if (irregular && restMark) {
            onPinRest?.(restMark);
            onClose();
            return;
        }
        const raw = picked.raw_description || picked.description;
        const key = seriesKeyFromDescription(raw) || `manual:${picked.id}`;
        onAddManual({
            key,
            label: picked.description,
            amount: Math.abs(picked.amount),
            frequency,
            lastDate: picked.date,
            categoryId: picked.category_id,
        });
        onClose();
    }

    return (
        <Sheet
            open={open}
            onClose={onClose}
            title={intent === "resto" ? "Sumar al resto" : "Añadir un cargo"}
            description={
                intent === "resto"
                    ? "Un gasto que haces seguido, sin día fijo. Carguito agrupa el comercio y su mes típico entra en la línea; no inventa una fecha."
                    : "Uno detectado se fija solo. Un comercio sin ritmo (Walmart) se fija por su mes típico, no por un día."
            }
            footer={
                <Button
                    onClick={confirm}
                    disabled={!picked || (intent === "resto" && (!!existing || !restMark))}
                >
                    {intent === "resto"
                        ? "Sumar al resto"
                        : existing
                          ? "Fijar este cobro"
                          : irregular
                            ? "Fijar (mes típico)"
                            : "Añadir como fijo"}
                </Button>
            }
        >
            <SearchInput
                onSearch={setQuery}
                placeholder="Buscar un movimiento"
                aria-label="Buscar un movimiento"
            />

            {picked && (
                <div className="mt-4 rounded-card border border-mist bg-fog/60 p-3">
                    <p className="text-body text-ink">{picked.description}</p>
                    <p className="mt-0.5 text-body-sm text-graphite">
                        {isoToLabel(picked.date)} · {mxn2(Math.abs(picked.amount))}
                    </p>
                    {intent === "resto" ? (
                        existing ? (
                            <p className="mt-2 text-body-sm text-graphite">
                                Ya es el cobro fijo «{existing.label}». Quítalo de fijos
                                si quieres que viva en el resto.
                            </p>
                        ) : restPreview ? (
                            <p className="mt-2 text-body-sm text-graphite">
                                {restMark?.label}: {restCluster.length} visita
                                {restCluster.length === 1 ? "" : "s"} · ~
                                {mxn(restPreview.monthly)}/mes (mediana, no un día fijo)
                            </p>
                        ) : null
                    ) : existing ? (
                        <p className="mt-2 text-body-sm text-graphite">
                            Ya es el cobro «{existing.label}». Se fija, no se duplica.
                        </p>
                    ) : irregular && restPreview ? (
                        <p className="mt-2 text-body-sm text-graphite">
                            {restMark?.label}: {restCluster.length} visita
                            {restCluster.length === 1 ? "" : "s"} · ~
                            {mxn(restPreview.monthly)}/mes: se fija el mes típico, no
                            un día en el calendario.
                        </p>
                    ) : (
                        <div className="mt-3">
                            <p className="mb-1.5 text-label text-graphite">Cada</p>
                            <div
                                role="radiogroup"
                                aria-label="Cadencia"
                                className="inline-flex rounded-control border border-mist bg-paper p-0.5"
                            >
                                {(Object.keys(FREQUENCY_LABELS) as Frequency[]).map((key) => {
                                    const selected = frequency === key;
                                    return (
                                        <button
                                            key={key}
                                            type="button"
                                            role="radio"
                                            aria-checked={selected}
                                            onClick={() => setFrequency(key)}
                                            className={cn(
                                                "rounded-control px-3 py-1 text-body-sm",
                                                "transition-colors duration-100",
                                                selected
                                                    ? "bg-fog font-medium text-ink"
                                                    : "text-graphite hover:text-ink"
                                            )}
                                        >
                                            {FREQUENCY_LABELS[key]}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>
            )}

            <ul className="mt-4 space-y-0.5">
                {items === null ? (
                    <li className="py-4 text-body-sm text-graphite">Cargando movimientos…</li>
                ) : filtered.length === 0 ? (
                    <li className="py-4 text-body-sm text-graphite">Nada coincide.</li>
                ) : (
                    filtered.map((t) => {
                        const on = picked?.id === t.id;
                        return (
                            <li key={t.id}>
                                <button
                                    type="button"
                                    onClick={() => setPicked(t)}
                                    className={cn(
                                        "flex w-full items-baseline justify-between gap-3 rounded-control px-2 py-2 text-left",
                                        "transition-colors duration-100",
                                        on ? "bg-fog" : "hover:bg-fog/60"
                                    )}
                                >
                                    <span className="min-w-0">
                                        <span className="block truncate text-body text-ink">{t.description}</span>
                                        <span className="text-body-sm text-graphite">{isoToLabel(t.date)}</span>
                                    </span>
                                    <span className="shrink-0 tabular text-body-sm text-ink">
                                        {mxn2(Math.abs(t.amount))}
                                    </span>
                                </button>
                            </li>
                        );
                    })
                )}
            </ul>
        </Sheet>
    );
}

function isoToLabel(iso: string): string {
    const d = parsePeriodKey(iso);
    return d ? dayLabel(d) : iso;
}
