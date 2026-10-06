"use client";

import { Switch } from "@/components/ui";
import { setChartsV2, useChartsV2 } from "@/lib/chartsV2";

/** The switch between the current charts and «Gráficas v2». Temporary: it
 *  goes away with the flag once one reading wins (see `lib/chartsV2.ts`). */
export function ChartsV2Toggle() {
    const on = useChartsV2();
    return (
        <label className="fixed bottom-4 left-4 z-40 flex items-center gap-2 rounded-full border border-mist bg-paper px-3 py-1.5 text-label text-graphite shadow-sm">
            <Switch checked={on} onChange={setChartsV2} aria-label="Gráficas v2" />
            Gráficas v2
        </label>
    );
}
