/**
 * INEGI · INPC nacional mensual, base 2ª quincena de julio 2018 = 100, by
 * objeto del gasto (canasta y ponderadores 2024). Two series:
 *
 * - `general`: índice general (INEGI series 865586).
 * - `alimentos`: objeto del gasto 1, «Alimentos, bebidas y tabaco» (series
 *   865587). This is the one that matches the ENIGH rubro: it includes fruit,
 *   vegetables and meat. The «Alimentos, bebidas y tabaco» in the bulletin's
 *   headline is a subyacente subindex of processed goods only — not this.
 *
 * Source: https://www.inegi.org.mx/app/indicesdeprecios/Estructura.aspx?idEstructura=112001700030
 * (export as CSV, series 865586 and 865587). Last month: August 2026,
 * published 2026-09-09.
 */

export const INPC_SOURCE = "INEGI · INPC por objeto del gasto";

/** "YYYY-MM" → index. */
export const INPC_MONTHLY: Record<string, { general: number; alimentos: number }> = {
    "2025-01": { general: 138.343, alimentos: 156.201 },
    "2025-02": { general: 138.726, alimentos: 155.75 },
    "2025-03": { general: 139.161, alimentos: 156.639 },
    "2025-04": { general: 139.62, alimentos: 158.128 },
    "2025-05": { general: 140.012, alimentos: 160.43 },
    "2025-06": { general: 140.405, alimentos: 160.775 },
    "2025-07": { general: 140.78, alimentos: 161.291 },
    "2025-08": { general: 140.867, alimentos: 160.956 },
    "2025-09": { general: 141.197, alimentos: 161.115 },
    "2025-10": { general: 141.708, alimentos: 160.86 },
    "2025-11": { general: 142.645, alimentos: 161.756 },
    "2025-12": { general: 143.042, alimentos: 161.947 },
    "2026-01": { general: 143.588, alimentos: 163.117 },
    "2026-02": { general: 144.307, alimentos: 164.439 },
    "2026-03": { general: 145.544, alimentos: 167.396 },
    "2026-04": { general: 145.831, alimentos: 168.115 },
    "2026-05": { general: 145.527, alimentos: 167.329 },
    "2026-06": { general: 145.131, alimentos: 164.876 },
    "2026-07": { general: 145.169, alimentos: 164.209 },
    "2026-08": { general: 145.462, alimentos: 164.814 },
};

export const INPC_LAST_MONTH = Object.keys(INPC_MONTHLY).sort().at(-1)!;

/**
 * How much each index moved between two months, as a ratio (1.04 = +4%).
 * Null when either month is outside the table: no extrapolating inflation.
 */
export function inpcChange(from: string, to: string): { general: number; alimentos: number } | null {
    const a = INPC_MONTHLY[from], b = INPC_MONTHLY[to];
    if (!a || !b) return null;
    return { general: b.general / a.general, alimentos: b.alimentos / a.alimentos };
}
