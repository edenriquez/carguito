"use client";

import { useState } from "react";
import { FileCheck2 } from "lucide-react";
import {
    ACCOUNT_KINDS,
    KIND_LABELS,
    SOURCE_LABELS,
    api,
    type AccountKind,
    type UploadResult,
} from "@/lib/api";
import { Button, Notice, Select, useToast } from "@/components/ui";
import { track } from "@/lib/telemetry";

/**
 * The OCR shows its work. After the first upload, the user sees what was
 * detected — bank, document type, period, movement count — and corrects the
 * two things the parser cannot know for sure: the bank name (the generic
 * template stores none) and the account kind (never inferred, by design —
 * a wrong guess would poison every metric that branches on it).
 *
 * "Confirmar" PATCHes only what changed; "Corregir después" skips straight
 * to the app — /documentos can fix it any time.
 */
export function ReviewStatement({
    result,
    onDone,
}: {
    result: UploadResult;
    /** Fires when the user confirms or skips; the caller enters the app. */
    onDone: () => void;
}) {
    const s = result.statement;
    const [bank, setBank] = useState(s.bank ?? "");
    const [kind, setKind] = useState<AccountKind | null>(s.account_kind);
    const [saving, setSaving] = useState(false);
    const { toast } = useToast();

    async function confirm() {
        const patch: Parameters<typeof api.updateStatement>[1] = {};
        const trimmed = bank.trim();
        if (trimmed !== (s.bank ?? "")) patch.bank = trimmed || null;
        if (kind !== s.account_kind) patch.account_kind = kind;

        track("onboarding.review", {
            decision: "confirm",
            changed: Object.keys(patch).join(",") || "nothing",
        });
        if (Object.keys(patch).length === 0) {
            onDone();
            return;
        }
        setSaving(true);
        try {
            await api.updateStatement(s.id, patch);
            onDone();
        } catch (e) {
            toast(`No se pudo guardar: ${(e as Error).message}`, "negative");
        } finally {
            setSaving(false);
        }
    }

    const period =
        s.period_start || s.period_end
            ? `${s.period_start ?? "?"} – ${s.period_end ?? "?"}`
            : "No detectado";
    // A parse that found nothing is the one outcome this screen must not
    // dress up as success: "0 movimientos" with a Confirmar button reads as
    // done. Say what happened and what to do.
    const skipped = result.transactions_skipped ?? 0;
    // Nothing new because everything was already there is a success, not an
    // empty parse: the same period was uploaded before.
    const empty = result.transactions_created === 0 && skipped === 0;
    // Banks without a dedicated parser (everything but Banamex and Banco
    // Azteca today) are read by the generic template, which takes the first
    // amount on each dated line. It works; it is also the one path where a
    // confident "90 movimientos" can hide a misread column.
    const generic = result.template === "generic_bank" && !empty;

    return (
        <div className="rounded-panel border border-mist bg-paper p-6 shadow-card sm:p-8">
            <div className="flex items-center gap-3">
                <div
                    aria-hidden
                    className="flex h-9 w-9 items-center justify-center rounded-input border border-mist bg-canvas text-signal"
                >
                    <FileCheck2 size={18} />
                </div>
                <div>
                    <p className="eyebrow">
                        {empty ? "Carguito leyó el archivo" : "Carguito leyó"}
                    </p>
                    <h2 className="text-title-sm font-normal text-ink">
                        {empty
                            ? "Sin movimientos legibles"
                            : skipped > 0
                              ? `${result.transactions_created} movimientos nuevos`
                              : `${result.transactions_created} movimientos`}
                    </h2>
                </div>
            </div>

            {empty && (
                <p className="mt-4 text-body-sm text-graphite">
                    El documento se guardó, pero Carguito no encontró movimientos en él. Suele
                    pasar con un PDF escaneado como imagen o con un resumen sin tabla de
                    cargos. Prueba con el estado de cuenta completo de tu banco.
                </p>
            )}

            {skipped > 0 && (
                <p className="mt-4 text-body-sm text-graphite">
                    {skipped.toLocaleString("es-MX")}{" "}
                    {skipped === 1 ? "movimiento ya estaba" : "movimientos ya estaban"} de una
                    subida anterior de esta cuenta y no se duplicaron; sólo se agregó lo que
                    faltaba.
                </p>
            )}

            {generic && (
                <Notice className="mt-4">
                    Leído con el lector genérico: {s.bank ?? "este banco"} todavía no tiene
                    lector dedicado. Revisa fechas y montos en Movimientos; si algo no cuadra,
                    corrígelo ahí.
                </Notice>
            )}

            <dl className="mt-6 space-y-1">
                <FactRow label="Documento">
                    {SOURCE_LABELS[s.source_type] ?? s.source_type}
                </FactRow>
                <FactRow label="Periodo">{period}</FactRow>
            </dl>

            {/* The two facts the parser can't be sure of are inputs, not rows. */}
            <div className="mt-4 space-y-4 border-t border-mist pt-5">
                <label className="block">
                    <span className="mb-1 block text-body-sm text-graphite">Banco</span>
                    <input
                        type="text"
                        value={bank}
                        onChange={(e) => setBank(e.target.value)}
                        placeholder="No identificado: escríbelo"
                        maxLength={120}
                        className="h-10 w-full rounded-input border border-muted bg-paper px-3 text-body text-ink outline-none placeholder:text-ash focus:border-signal"
                    />
                </label>

                <div>
                    <span className="mb-1 block text-body-sm text-graphite">
                        Tipo de cuenta
                    </span>
                    <Select<AccountKind>
                        aria-label="Tipo de cuenta"
                        value={kind}
                        placeholder="Sin etiqueta"
                        options={ACCOUNT_KINDS.map((k) => ({
                            value: k,
                            label: KIND_LABELS[k],
                        }))}
                        onChange={setKind}
                    />
                </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
                <Button loading={saving} onClick={confirm} className="text-ink">
                    Confirmar y continuar
                </Button>
                <Button
                    variant="ghost"
                    onClick={() => {
                        track("onboarding.review", { decision: "skip" });
                        onDone();
                    }}
                >
                    Corregir después
                </Button>
            </div>
        </div>
    );
}

function FactRow({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex items-baseline justify-between gap-4 py-1.5">
            <dt className="text-body-sm text-graphite">{label}</dt>
            <dd className="text-body text-ink">{children}</dd>
        </div>
    );
}
