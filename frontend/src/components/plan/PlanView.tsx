"use client";

import { useEffect } from "react";
import { ArrowDownToLine, ArrowUpFromLine, HardDrive } from "lucide-react";
import { FaceTabs } from "@/components/ui";
import { track } from "@/lib/telemetry";
import { useFace } from "@/lib/useFace";
import { FijosView } from "@/components/fijos/FijosView";
import { PronosticoView } from "@/components/pronostico/PronosticoView";

/**
 * Plan: Fijos and Pronóstico under one roof.
 *
 * They were two tabs that shared everything — the same two API calls, the same
 * pinned set (`useFijos`), the same 6/12-month horizon, the same projection
 * engine — and split one question ("¿me alcanza?") into two halves that could
 * not see each other. Here they are two faces of one view: what leaves, and
 * what comes in against it. The horizon you pick on one face is the horizon
 * of the other, because it always was.
 *
 * The face lives in the URL so a link to "ingresos" is a link, and the
 * retired `/pronostico` can land on it — but it is state first (`useFace`):
 * clicking a tab must not cost an RSC round trip and a remount of everything
 * under it.
 */
export const FACES = ["fijos", "ingresos"] as const;
export type Face = (typeof FACES)[number];

const FACE_LABELS: Record<Face, { label: string; hint: string }> = {
    fijos: { label: "Gastos fijos", hint: "Lo que pagas sí o sí, y lo que viene" },
    ingresos: { label: "Ingresos", hint: "Nómina y extra, contra tus gastos fijos" },
};

export function faceFromParam(value: string | null): Face {
    return value === "ingresos" ? "ingresos" : "fijos";
}

export function planHref(face: Face): string {
    return face === "fijos" ? "/plan" : "/plan?cara=ingresos";
}

export function PlanView() {
    const [face, setFace] = useFace(faceFromParam, planHref);

    useEffect(() => {
        track("plan.face", { face, source: "arrive" });
    }, [face]);

    function pick(next: Face) {
        if (next === face) return;
        track("plan.face", { face: next, source: "switch" });
        setFace(next);
    }

    return (
        <div className="space-y-4 sm:space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <FaceTabs
                    tabs={FACES.map((f) => ({
                        key: f,
                        title: FACE_LABELS[f].hint,
                        label: (
                            <>
                                {f === "fijos" ? (
                                    <ArrowUpFromLine size={15} aria-hidden />
                                ) : (
                                    <ArrowDownToLine size={15} aria-hidden />
                                )}
                                {FACE_LABELS[f].label}
                            </>
                        ),
                    }))}
                    value={face}
                    onChange={pick}
                    label="Cara del plan"
                    tone="light"
                    size="md"
                />

                {/* Said once, quietly: the pins and the income labels are the
                    user's work, and today they live in this browser only. A
                    device change loses them and nothing else in the app would
                    have warned. */}
                <p
                    className="inline-flex items-center gap-1.5 text-label text-ash"
                    title="Los fijos que fijas y los abonos que etiquetas se guardan en este navegador. En otro navegador o celular empiezas de cero."
                >
                    <HardDrive size={12} aria-hidden />
                    Tus fijos y etiquetas se guardan en este navegador
                </p>
            </div>

            {face === "fijos" ? (
                <FijosView onGoToIngresos={() => pick("ingresos")} />
            ) : (
                <PronosticoView onGoToFijos={() => pick("fijos")} />
            )}
        </div>
    );
}
