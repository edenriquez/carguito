"use client";

import { EstadoView } from "@/components/estado/EstadoView";
import { PreciosView } from "@/components/precios/PreciosView";
import { RecurrentesView } from "@/components/recurrentes/RecurrentesView";
import type { MovimientosFace } from "./MovimientosHome";
import { PorCategoriaView } from "./PorCategoriaView";
import { PorMesView } from "./PorMesView";

/**
 * The content under the Movimientos container: whichever face `face` names.
 *
 * The prop decides what is fetched. Naming a face mounts it, and mounting is
 * its fetch; while the data is on its way the face draws its own placeholder
 * at the geometry of what is coming, so the switch reads as *the same page
 * filling in* rather than as a jump. That placeholder is the whole
 * transition — nothing slides, nothing is held from the previous face.
 *
 * Keyed on the face so a switch is a clean mount: the outgoing face's state
 * (open group, in-flight fetch) goes with it, and the incoming one starts at
 * its skeleton every time.
 */
export function MovimientosContent({ face }: { face: MovimientosFace }) {
    switch (face) {
        case "lectura":
            return <EstadoView key={face} />;
        case "mes":
            return <PorMesView key={face} />;
        case "categoria":
            return <PorCategoriaView key={face} />;
        case "recurrentes":
            return <RecurrentesView key={face} />;
        case "precios":
            return <PreciosView key={face} />;
    }
}
