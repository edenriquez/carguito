/**
 * INEGI · ENIGH 2024 (published 2025-07-30), by household decile, in 2024
 * pesos. The survey reports quarterly figures; these are divided by three.
 *
 * - `ingreso`: ingreso corriente promedio por hogar (reporte de resultados,
 *   cuadro 6).
 * - `gasto`: gasto corriente monetario promedio por hogar (presentación de
 *   resultados, "según deciles de ingreso por hogar").
 *
 * Both are *household* figures (3.4 people, 1.63 earners on average), so a
 * comparison against one person's statement is an approximation — the face
 * says "por hogar" once, where the source is cited.
 */

export const ENIGH_YEAR = 2024;

export const DECILE_LABELS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"] as const;

export const ENIGH_MONTHLY = {
    ingreso: [5598, 9432, 12282, 15082, 18103, 21533, 25817, 31764, 41237, 78698],
    gasto: [5652, 7778, 9443, 10939, 12490, 14342, 16281, 19163, 23497, 39329],
} as const;

/** What each decile's household spends of every peso it takes in. Decile I
 *  runs above one: the poorest households report spending more than they earn. */
export const ENIGH_SPEND_RATIO = ENIGH_MONTHLY.gasto.map((g, i) => g / ENIGH_MONTHLY.ingreso[i]!);

/** The national household spends this much of each peso it takes in. */
export const NATIONAL_SPEND_RATIO = 47674 / 77864;

type Series = readonly number[];

/**
 * Where a monthly amount falls, 0–100, reading each decile's mean as sitting
 * at the middle of its decile (5, 15 … 95) and interpolating in between. An
 * approximation of the percentile — the survey publishes means, not the
 * distribution — which is why the face speaks in deciles and "~".
 */
export function percentileOf(value: number, series: Series): number {
    if (value <= series[0]!) return Math.max(0.5, (value / series[0]!) * 5);
    for (let i = 0; i < series.length - 1; i++) {
        const lo = series[i]!, hi = series[i + 1]!;
        if (value <= hi) return 5 + 10 * (i + (value - lo) / (hi - lo));
    }
    const top = series[series.length - 1]!;
    return Math.min(99.5, 95 + 4.5 * Math.min(1, (value - top) / top));
}

/** The inverse of `percentileOf`: the amount at a percentile of the series. */
export function valueAtPercentile(p: number, series: Series): number {
    if (p <= 5) return (p / 5) * series[0]!;
    if (p >= 95) return series[series.length - 1]!;
    const i = Math.floor((p - 5) / 10);
    const f = (p - 5) / 10 - i;
    return series[i]! + f * (series[i + 1]! - series[i]!);
}

/** 0-based decile a percentile falls in. */
export function decileIndex(p: number): number {
    return Math.max(0, Math.min(9, Math.floor(p / 10)));
}
