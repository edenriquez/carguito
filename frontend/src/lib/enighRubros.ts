/**
 * INEGI · ENIGH 2024 (published 2025-07-30), Tabulados básicos, Cuadro 4.2:
 * gasto corriente monetario trimestral by gran rubro and household decile,
 * divided by the households of each decile (3,883,023; 38,830,230 national)
 * and then by three. 2024 pesos, per household, per month.
 *
 * The totals reproduce `ENIGH_MONTHLY.gasto` in `enigh.ts` exactly, and the
 * rubros add up to each decile's total within a peso of rounding.
 *
 * Source: https://www.inegi.org.mx/contenidos/programas/enigh/nc/2024/tabulados/enigh2024_ns_basicos_tabulados.xlsx
 */

export type Rubro =
    | "alimentos"
    | "vestido"
    | "vivienda"
    | "casa"
    | "salud"
    | "transporte"
    | "educacion"
    | "personales"
    | "transferencias";

export const RUBRO_ORDER: Rubro[] = [
    "alimentos",
    "transporte",
    "educacion",
    "vivienda",
    "personales",
    "casa",
    "vestido",
    "salud",
    "transferencias",
];

/** Short names for a chart row; the cuadro's full names are far longer. */
export const RUBRO_LABELS: Record<Rubro, string> = {
    alimentos: "Alimentos y bebidas",
    vestido: "Vestido y calzado",
    vivienda: "Vivienda y servicios",
    casa: "Artículos para la casa",
    salud: "Salud",
    transporte: "Transporte y comunicaciones",
    educacion: "Educación y esparcimiento",
    personales: "Cuidados personales",
    transferencias: "Transferencias de gasto",
};

/** Pesos per household per month, deciles I–X. */
export const ENIGH_RUBRO_MONTHLY: Record<Rubro, readonly number[]> = {
    alimentos: [2889, 3721, 4348, 4857, 5357, 5920, 6385, 7119, 8047, 11296],
    vestido: [161, 247, 310, 380, 444, 532, 630, 786, 977, 1632],
    vivienda: [586, 830, 969, 1103, 1191, 1307, 1490, 1673, 2101, 3236],
    casa: [366, 461, 547, 625, 737, 805, 921, 1152, 1470, 2963],
    salud: [217, 258, 286, 315, 389, 437, 440, 582, 796, 1629],
    transporte: [720, 1148, 1559, 1897, 2230, 2751, 3335, 3985, 4988, 8450],
    educacion: [235, 426, 572, 764, 932, 1202, 1386, 1827, 2493, 5472],
    personales: [391, 568, 677, 797, 932, 1073, 1257, 1530, 1897, 3241],
    transferencias: [86, 119, 175, 201, 277, 314, 436, 508, 728, 1410],
};

/** The national household, pesos per month. */
export const ENIGH_RUBRO_NATIONAL: Record<Rubro, number> = {
    alimentos: 5994,
    vestido: 610,
    vivienda: 1449,
    casa: 1005,
    salud: 535,
    transporte: 3106,
    educacion: 1531,
    personales: 1236,
    transferencias: 425,
};

/** A decile's spend on a rubro as a share of its gasto corriente monetario. */
export function rubroShare(rubro: Rubro, decile: number): number {
    const total = RUBRO_ORDER.reduce((s, r) => s + ENIGH_RUBRO_MONTHLY[r][decile]!, 0);
    return total > 0 ? ENIGH_RUBRO_MONTHLY[rubro][decile]! / total : 0;
}
