/**
 * Líneas de Pobreza por Ingresos: what the canasta alimentaria and the full
 * canasta (alimentaria + no alimentaria) cost per person per month, current
 * pesos. CONEVAL published the series through March 2025; INEGI has since
 * July 2025, same method (basket of August 2016, moved monthly by the INPC).
 *
 * Source (Cuadro 1, sheet updated 2026-09-14):
 * https://www.inegi.org.mx/contenidos/desarrollosocial/lp/tabulados/lp_2026.xlsx
 * Monthly bulletins: https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/lp/
 *
 * Rural = localities under 2,500 people; urbana = 2,500 and more.
 */

export type CanastaMonth = {
    /** Canasta alimentaria (Línea de Pobreza Extrema por Ingresos). */
    alimentariaRural: number;
    alimentariaUrbana: number;
    /** Alimentaria + no alimentaria (Línea de Pobreza por Ingresos). */
    completaRural: number;
    completaUrbana: number;
};

export const CANASTA_SOURCE = "INEGI · Líneas de Pobreza por Ingresos";

/** "YYYY-MM" → pesos per person per month. */
export const CANASTA_MONTHLY: Record<string, CanastaMonth> = {
    "2025-01": { alimentariaRural: 1795.77, alimentariaUrbana: 2366.33, completaRural: 3342.21, completaUrbana: 4660.52 },
    "2025-02": { alimentariaRural: 1787.36, alimentariaUrbana: 2364.01, completaRural: 3340.21, completaUrbana: 4666.65 },
    "2025-03": { alimentariaRural: 1797.48, alimentariaUrbana: 2379.47, completaRural: 3350.38, completaUrbana: 4680.15 },
    "2025-04": { alimentariaRural: 1814.57, alimentariaUrbana: 2400.01, completaRural: 3362.21, completaUrbana: 4685.49 },
    "2025-05": { alimentariaRural: 1844.87, alimentariaUrbana: 2429.8, completaRural: 3380.26, completaUrbana: 4690.04 },
    "2025-06": { alimentariaRural: 1850.82, alimentariaUrbana: 2441.49, completaRural: 3388.94, completaUrbana: 4703.8 },
    "2025-07": { alimentariaRural: 1856.91, alimentariaUrbana: 2453.34, completaRural: 3396.71, completaUrbana: 4718.55 },
    "2025-08": { alimentariaRural: 1850.73, alimentariaUrbana: 2452.05, completaRural: 3394.06, completaUrbana: 4722.01 },
    "2025-09": { alimentariaRural: 1850.65, alimentariaUrbana: 2454.74, completaRural: 3403.5, completaUrbana: 4740.84 },
    "2025-10": { alimentariaRural: 1844.15, alimentariaUrbana: 2450.01, completaRural: 3411.88, completaUrbana: 4759.91 },
    "2025-11": { alimentariaRural: 1854.63, alimentariaUrbana: 2462.71, completaRural: 3447.63, completaUrbana: 4809.1 },
    "2025-12": { alimentariaRural: 1854.39, alimentariaUrbana: 2467.15, completaRural: 3451.13, completaUrbana: 4818.14 },
    "2026-01": { alimentariaRural: 1863.17, alimentariaUrbana: 2486.4, completaRural: 3465.76, completaUrbana: 4843.11 },
    "2026-02": { alimentariaRural: 1887.58, alimentariaUrbana: 2516.97, completaRural: 3494.95, completaUrbana: 4877.87 },
    "2026-03": { alimentariaRural: 1940.37, alimentariaUrbana: 2571.18, completaRural: 3553.46, completaUrbana: 4940.45 },
    "2026-04": { alimentariaRural: 1966.06, alimentariaUrbana: 2598.99, completaRural: 3572.47, completaUrbana: 4954.23 },
    "2026-05": { alimentariaRural: 1960.23, alimentariaUrbana: 2597.37, completaRural: 3554.28, completaUrbana: 4929.96 },
    "2026-06": { alimentariaRural: 1907.63, alimentariaUrbana: 2553.37, completaRural: 3503.97, completaUrbana: 4888.22 },
    "2026-07": { alimentariaRural: 1894.69, alimentariaUrbana: 2545.72, completaRural: 3494.78, completaUrbana: 4884.09 },
    "2026-08": { alimentariaRural: 1910.78, alimentariaUrbana: 2562.58, completaRural: 3515.33, completaUrbana: 4905.33 },
};

/**
 * The latest published month at or before `monthKey` ("YYYY-MM"), so a
 * statement from a month INEGI has not priced yet reads against the last
 * one it has. Null before the series starts.
 */
export function canastaAt(monthKey: string): { key: string; value: CanastaMonth } | null {
    const keys = Object.keys(CANASTA_MONTHLY).sort();
    let pick: string | null = null;
    for (const k of keys) if (k <= monthKey) pick = k;
    return pick ? { key: pick, value: CANASTA_MONTHLY[pick]! } : null;
}
