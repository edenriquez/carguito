"use client";

import { useEffect, useMemo, useState } from "react";
import { FaceTabs } from "@/components/ui";
import { useAppData } from "@/components/AppChrome";
import { useBankScope } from "@/lib/banks";
import { periodChipLabel } from "@/lib/movimientosQuery";
import { SPAN_MONTHS } from "@/lib/porMes";
import { track } from "@/lib/telemetry";
import { WINDOW_LABELS } from "@/lib/window";
import { MovimientosContent } from "./MovimientosContent";

export const FACES = ["lectura", "mes", "categoria", "recurrentes", "precios"] as const;
export type MovimientosFace = (typeof FACES)[number];

const FACE_LABELS: Record<MovimientosFace, string> = {
    lectura: "Lectura",
    mes: "Por mes",
    categoria: "Por categoría",
    recurrentes: "Cargos recurrentes",
    precios: "Precios",
};

/**
 * The unified Movimientos reading: one container, five faces.
 *
 * The container is this component — the eyebrow that names the period being
 * read and the strip of tabs that picks the face — and it is rendered once.
 * Switching faces changes one prop on the content below it; nothing above
 * that line is remounted, which is what lets the selected mark in the strip
 * *travel* from one tab to the next instead of being redrawn under the new
 * one. The faces used to draw the strip themselves, each inside its own
 * card, and a switch swapped five copies of it.
 *
 * The face is component state and nothing else: `/` always opens on the
 * Lectura, and the URL does not follow the tabs. A click flips the face in
 * the same frame, and which data the content fetches is decided by that one
 * prop.
 */
export function MovimientosHome() {
    const [face, setFace] = useState<MovimientosFace>("lectura");

    useEffect(() => {
        track("movimientos.face", { face, source: "arrive" });
    }, [face]);

    function pick(next: MovimientosFace) {
        if (next === face) return;
        track("movimientos.face", { face: next, source: "switch" });
        setFace(next);
    }

    // Precios is always a tab: a ticket can be uploaded from this page, so the
    // empty face is where that starts, not an empty room.
    const tabs = useMemo(() => FACES.map((f) => ({ key: f, label: FACE_LABELS[f] })), []);

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3 px-1">
                <FaceEyebrow face={face} />
                <FaceTabs tabs={tabs} value={face} onChange={pick} label="Cara de movimientos" />
            </div>
            <MovimientosContent face={face} />
        </div>
    );
}

/**
 * "PERIODO · 6 MESES · BANAMEX, NU" — the scope the face's reading is true
 * under. Each face reads a different span: Lectura and Por mes always read
 * the last six months, Por categoría and Cargos recurrentes read the window
 * the rail selects, and Precios reads every ticket regardless. Banks appear
 * only when a filter is on; "todos" would be a word for the default.
 *
 * Its own component so that when the window or the bank filter moves, the
 * container re-renders this line and only this line.
 */
function FaceEyebrow({ face }: { face: MovimientosFace }) {
    const { dataVersion, window: timeWindow } = useAppData();
    const { labels: banks } = useBankScope(dataVersion);

    const period = useMemo(() => {
        if (face === "precios") return "todos los tickets";
        if (face === "lectura" || face === "mes") return `${SPAN_MONTHS} meses`;
        if (timeWindow.kind === "preset") return WINDOW_LABELS[timeWindow.id];
        return periodChipLabel(timeWindow.start, timeWindow.end).replace(/^Periodo · /, "");
    }, [face, timeWindow]);

    const scope =
        face === "precios" || banks.length === 0 ? period : `${period} · ${banks.join(", ")}`;
    return <p className="eyebrow">Periodo · {scope}</p>;
}
