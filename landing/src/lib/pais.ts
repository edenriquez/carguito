/**
 * The published tables the dashboard's Lectura reads a statement against,
 * copied — the landing cannot import from frontend/. These are real figures,
 * not examples: only the user's side of every comparison on the landing is
 * made up. Keep them in step with the frontend files named on each block.
 */

/** frontend/src/lib/enigh.ts · INEGI · ENIGH 2024, per household, per month, deciles I–X. */
export const ENIGH_YEAR = 2024;
export const DECILE_LABELS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"] as const;
export const ENIGH_MONTHLY = {
    ingreso: [5598, 9432, 12282, 15082, 18103, 21533, 25817, 31764, 41237, 78698],
    gasto: [5652, 7778, 9443, 10939, 12490, 14342, 16281, 19163, 23497, 39329],
} as const;

/** frontend/src/lib/enighRubros.ts · Cuadro 4.2: «Alimentos y bebidas», pesos per household per month. */
export const ENIGH_ALIMENTOS = [2889, 3721, 4348, 4857, 5357, 5920, 6385, 7119, 8047, 11296] as const;

/** frontend/src/lib/canasta.ts · INEGI · Líneas de Pobreza por Ingresos, agosto de 2026, per person per month. */
export const CANASTA = {
    key: "2026-08",
    alimentariaUrbana: 2562.58,
    completaUrbana: 4905.33,
    source: "INEGI · Líneas de Pobreza por Ingresos",
} as const;

/** frontend/src/lib/inpc.ts · INEGI · INPC por objeto del gasto. September 2026 is not published yet. */
export const INPC: ReadonlyArray<{ key: string; general: number; alimentos: number }> = [
    { key: "2026-04", general: 145.831, alimentos: 168.115 },
    { key: "2026-05", general: 145.527, alimentos: 167.329 },
    { key: "2026-06", general: 145.131, alimentos: 164.876 },
    { key: "2026-07", general: 145.169, alimentos: 164.209 },
    { key: "2026-08", general: 145.462, alimentos: 164.814 },
];
export const INPC_SOURCE = "INEGI · INPC por objeto del gasto";

/**
 * Where a monthly amount falls, 0–100, reading each decile's mean as the
 * middle of its decile — the same approximation as `percentileOf` in
 * frontend/src/lib/enigh.ts.
 */
export function percentileOf(value: number, series: readonly number[]): number {
    if (value <= series[0]!) return Math.max(0.5, (value / series[0]!) * 5);
    for (let i = 0; i < series.length - 1; i++) {
        const lo = series[i]!, hi = series[i + 1]!;
        if (value <= hi) return 5 + 10 * (i + (value - lo) / (hi - lo));
    }
    const top = series[series.length - 1]!;
    return Math.min(99.5, 95 + 4.5 * Math.min(1, (value - top) / top));
}

export function valueAtPercentile(p: number, series: readonly number[]): number {
    if (p <= 5) return (p / 5) * series[0]!;
    if (p >= 95) return series[series.length - 1]!;
    const i = Math.floor((p - 5) / 10);
    const f = (p - 5) / 10 - i;
    return series[i]! + f * (series[i + 1]! - series[i]!);
}

export function decileIndex(p: number): number {
    return Math.max(0, Math.min(9, Math.floor(p / 10)));
}
