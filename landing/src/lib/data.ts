import {
    CANASTA,
    DECILE_LABELS,
    ENIGH_ALIMENTOS,
    ENIGH_MONTHLY,
    INPC,
    decileIndex,
    percentileOf,
    valueAtPercentile,
} from "./pais";

/**
 * One example user, and every figure the landing quotes about "you". Made up,
 * and the page says so next to each one ("Ejemplo", "cifras de ejemplo"). The
 * country side of each comparison is real (`pais.ts`). Derived figures are
 * computed here with the dashboard's own rules, so a title, its chart and the
 * hero can never disagree. Sentences copy the dashboard's finding titles
 * (frontend/src/components/estado/EstadoView.tsx and each face) word for word.
 */

/* ---------------------------------------------------------------- format */

const MXN0 = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 0, maximumFractionDigits: 0 });
const MXN2 = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 });
/** Headlines and tooltips: "$9,140". */
export const mxn = (n: number) => MXN0.format(n);
/** Rows a user would reconcile by hand: "$1,412.60". */
export const mxn2 = (n: number) => MXN2.format(n);
export const pct = (v: number) => `${Math.round(v * 100)}%`;
/** Axis figures, as the Lectura charts: "$18.7k". */
export const k = (n: number) => `$${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;

const MONTH_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MONTH_NAME = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
export const monthShort = (key: string) => MONTH_SHORT[Number(key.slice(5, 7)) - 1]!;
const monthName = (key: string) => MONTH_NAME[Number(key.slice(5, 7)) - 1]!;

/* ------------------------------------------------------------ the record */

export type ExampleMonth = { key: string; amount: number; partialDay?: number };

/** Six months of cargos, abril to the 28th of septiembre: the last one is partial. */
export const MONTHS: ExampleMonth[] = [
    { key: "2026-04", amount: 18650 },
    { key: "2026-05", amount: 21300 },
    { key: "2026-06", amount: 17400 },
    { key: "2026-07", amount: 18100 },
    { key: "2026-08", amount: 17170 },
    { key: "2026-09", amount: 16800, partialDay: 28 },
];
const COMPLETE = MONTHS.filter((m) => !m.partialDay);
export const PARTIAL = MONTHS.find((m) => m.partialDay) ?? null;

/** What the example user said comes in a month: two quincenas of $8,250. */
export const INCOME = 16500;

/**
 * The fijos the example user pinned in Plan, biggest first. CFE is
 * bimestral, so it lands every other month; Renta was added by hand.
 */
export const FIJOS = [
    { label: "Renta", amount: 6500, every: 1, day: 1 },
    { label: "CFE", amount: 780, every: 2, day: 18 },
    { label: "Izzi", amount: 599, every: 1, day: 5 },
    { label: "Telcel", amount: 449, every: 1, day: 12 },
    { label: "Netflix", amount: 299, every: 1, day: 15 },
    { label: "Spotify", amount: 129, every: 1, day: 21 },
] as const;

/** The month's weight by day of the month, 1–31: light at the start, heavy after the 20th. */
const DAY_WEIGHTS = [5, 3, 4, 2, 6, 3, 4, 2, 3, 4, 4, 5, 3, 6, 4, 8, 5, 3, 6, 7, 6, 5, 9, 7, 6, 8, 12, 7, 6, 5, 4];

/* ------------------------------------------------------------ Lectura */

/** The Lectura's average: every month with cargos, the partial one included (`readEstado`). */
const average = MONTHS.reduce((s, m) => s + m.amount, 0) / MONTHS.length;
const spendP = percentileOf(average, ENIGH_MONTHLY.gasto);
const spendD = decileIndex(spendP);
const equivalent = valueAtPercentile(spendP, ENIGH_MONTHLY.ingreso);
const incomeP = percentileOf(INCOME, ENIGH_MONTHLY.ingreso);

function ratioWords(ratio: number): string {
    if (ratio >= 2.8) return `${ratio.toFixed(1)} veces lo que ganas`;
    if (ratio >= 2.4) return "casi el triple";
    if (ratio >= 1.8) return "el doble";
    if (ratio >= 1.4) return "la mitad más";
    return "un poco más";
}

/** Supermercado: the food bought to eat at home, per month. */
const food = 5400;
/** Comida & Supermercados as a share of the spend: the same slice Por categoría leads with. */
const COMIDA_SHARE = 0.34;
/** The median change of the example user's own products, abril to agosto, read off their tickets. */
const ticketDrift = 1.04;

const inpcBase = INPC[0]!;
const inpcPoints = INPC.map((p) => ({
    key: p.key,
    general: (p.general / inpcBase.general) * 100,
    alimentos: (p.alimentos / inpcBase.alimentos) * 100,
}));
const inpcLast = inpcPoints[inpcPoints.length - 1]!;
const inpcFood = inpcLast.alimentos / 100;
const moved = (ratio: number, plural = true) => {
    const d = ratio - 1;
    if (Math.abs(d) < 0.005) return plural ? "no se movieron" : "no se movió";
    return `${d > 0 ? (plural ? "subieron" : "subió") : plural ? "bajaron" : "bajó"} ${pct(Math.abs(d))}`;
};

const dayTotal = DAY_WEIGHTS.reduce((s, w) => s + w, 0);
const shares = [
    DAY_WEIGHTS.slice(0, 10).reduce((s, w) => s + w, 0) / dayTotal,
    DAY_WEIGHTS.slice(10, 20).reduce((s, w) => s + w, 0) / dayTotal,
    DAY_WEIGHTS.slice(20).reduce((s, w) => s + w, 0) / dayTotal,
] as const;
const completeAverage = COMPLETE.reduce((s, m) => s + m.amount, 0) / COMPLETE.length;
/** The average complete month, running total by day (`readPayday`). */
const curve = DAY_WEIGHTS.reduce<number[]>((acc, w) => [...acc, (acc[acc.length - 1] ?? 0) + (w / dayTotal) * completeAverage], []);
const crossDay = curve.findIndex((v) => v >= INCOME) + 1 || null;

export const LECTURA = {
    average,
    months: MONTHS.length,
    decil: {
        index: spendD,
        label: DECILE_LABELS[spendD]!,
        title: `Gastas como un hogar del decil ${DECILE_LABELS[spendD]}`,
        equivalent,
        spendShare: spendP / 100,
        foot: `Ganas más que ~${Math.round(incomeP)}% de los hogares. Tu gasto es el de alguien que gana ${ratioWords(equivalent / INCOME)}.`,
    },
    canasta: {
        food,
        foodPersons: food / CANASTA.alimentariaUrbana,
        totalPersons: average / CANASTA.completaUrbana,
        title: `Tu comida de casa alimentaría a ${(food / CANASTA.alimentariaUrbana).toFixed(1)} personas con la canasta alimentaria`,
        foot: `Canasta alimentaria urbana de ${monthName(CANASTA.key)}: ${mxn2(CANASTA.alimentariaUrbana)} por persona al mes; con lo no alimentario, ${mxn2(CANASTA.completaUrbana)}. ${CANASTA.source}.`,
    },
    inpc: {
        points: inpcPoints,
        user: { key: inpcLast.key, value: inpcLast.alimentos * (ticketDrift / inpcFood), label: `Tus tickets ${moved(ticketDrift)}` },
        title: `Tus productos ${moved(ticketDrift)}; el INPC de alimentos ${moved(inpcFood, false)} en los mismos meses`,
    },
    dias: {
        /** Summed over the span, as the chart draws it. */
        byDay: DAY_WEIGHTS.map((w) => (w / dayTotal) * average * MONTHS.length),
        shares,
        title: shares[0] < 0.25 ? "Gastas más en la segunda mitad del mes" : shares[0] > 0.45 ? "Gastas más al inicio del mes" : "Tu gasto se reparte a lo largo del mes",
        foot: `${Math.round((1 - shares[0]) * 100)}% de tu gasto cae después del día 10.`,
    },
    diaCero: {
        curve,
        crossDay,
        title: crossDay ? `El día ${crossDay} ya gastaste todo lo que entra` : `Tu ingreso alcanza todo el mes: al cierre te quedan ~${mxn(INCOME - curve[30]!)}`,
        foot: `Mes promedio sobre ${COMPLETE.length} meses completos, contra el ingreso de ${mxn(INCOME)} que escribiste una vez.`,
    },
    /** The rest of the face, by its own section headings, as one-line findings. */
    more: [
        { section: "Contra el país", title: `Sale $${(average / INCOME).toFixed(2)} por cada $1 que entra` },
        { section: "Contra el país", title: `Destinas ${pct(COMIDA_SHARE)} a alimentos y bebidas; el hogar del decil ${DECILE_LABELS[spendD]}, ${pct(ENIGH_ALIMENTOS[spendD]! / ENIGH_MONTHLY.gasto[spendD]!)}` },
        { section: "Con tu ingreso", title: `${mxn(FIJOS.reduce((s, f) => s + f.amount / f.every, 0))} de tus ${mxn(INCOME)} ya están apartados antes del día 1` },
        { section: "Con tu ingreso", title: "Restaurantes te costó 68 horas de trabajo" },
        { section: "En el tiempo", title: "Más de la mitad cae en fin de semana" },
        { section: "En el tiempo", title: "Tu mes más caro costó 1.2 veces tu mes más barato" },
        { section: "En qué y dónde", title: "3 lugares se llevan el 29% de tu gasto" },
        { section: "En qué y dónde", title: "38% de tus cargos son de $200 o menos y suman el 9% del dinero" },
        { section: "En qué y dónde", title: "81% de tu gasto va a lugares donde ya habías pagado" },
    ],
} as const;

/**
 * What the hero sets at 96px: the Lectura's first finding, the one that
 * opens the face. Labelled "Ejemplo" where it is shown.
 */
export const HERO = {
    amount: mxn(average),
    unit: "/mes",
    caption: `Gastas como un hogar que ingresa ~${mxn(equivalent)} al mes: el decil ${DECILE_LABELS[spendD]} de la ENIGH 2024. Es la primera lectura que te da Carguito.`,
} as const;

/** «Lo que no cuadra»: the attention flags, biggest first, with the reason the row prints. */
export const NO_CUADRA: ReadonlyArray<{ description: string; day: string; reason: string; flag: "inusual" | "duplicado" | "nuevo"; amount: number; warn: boolean }> = [
    { description: "LIVERPOOL POLANCO", day: "14 sep", reason: "3.4× lo que sueles gastar ahí (tu cargo típico es $1,432.00)", flag: "inusual", amount: 4870, warn: true },
    { description: "MERPAGO*TIENDAXYZ", day: "3 sep", reason: "Primera vez ahí, y arriba de tu gasto típico ($450.00)", flag: "nuevo", amount: 689.5, warn: false },
    { description: "SPOTIFY MEXICO", day: "21 ago", reason: "Mismo monto que otro cargo ahí el mismo día", flag: "duplicado", amount: 129, warn: true },
];

/* ------------------------------------------------------- the other faces */

/** Por mes: complete months only in the mean; the running month is drawn apart, «al 28». */
const peak = COMPLETE.reduce((b, m) => (m.amount > b.amount ? m : b), COMPLETE[0]!);
export const POR_MES = {
    months: MONTHS,
    average: completeAverage,
    peak: peak.key,
    title: `Gastaste ${mxn(peak.amount)} en ${monthName(peak.key)}: ${Math.round((peak.amount / completeAverage - 1) * 100)}% más que tu promedio de ${mxn(completeAverage)}`,
} as const;

/**
 * Por categoría: the root categories of the default taxonomy with their own
 * colors (backend/src/carguito/adapters/outbound/persistence/seed.py).
 * «Sin categoría» is Ash, as anywhere in the app.
 */
const CATEGORY_SLICES = [
    { name: "Comida & Supermercados", share: COMIDA_SHARE, color: "#a855f7" },
    { name: "Vivienda & Servicios", share: 0.21, color: "#3b82f6" },
    { name: "Transporte", share: 0.16, color: "#eab308" },
    { name: "Entretenimiento", share: 0.09, color: "#ec4899" },
    { name: "Gasto", share: 0.08, color: "#dc2626" },
    { name: "Sin categoría", share: 0.12, color: "#a8a29e", uncategorized: true },
] as const;
const named = CATEGORY_SLICES.filter((s) => !("uncategorized" in s));
export const POR_CATEGORIA = {
    slices: CATEGORY_SLICES,
    title: `${named[0]!.name} concentra ${pct(named[0]!.share)} de tu gasto; las 3 primeras, ${pct(named.slice(0, 3).reduce((s, x) => s + x.share, 0))}`,
} as const;

/** Julio to diciembre; octubre (today) is the first projected month. CFE lands in the even months. */
const TIMELINE_KEYS = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"];
const lands = (f: (typeof FIJOS)[number], key: string) => f.every === 1 || Number(key.slice(5, 7)) % 2 === 0;
const timeline = TIMELINE_KEYS.map((key) => ({ key, values: FIJOS.map((f): number => (lands(f, key) ? f.amount : 0)) }));
const monthlyRate = FIJOS.reduce((s, f) => s + f.amount / f.every, 0);
const projected = timeline.slice(3).reduce((s, m) => s + m.values.reduce((a, b) => a + b, 0), 0);
export const LO_QUE_SE_VA = {
    timeline,
    firstFuture: 3,
    monthlyRate,
    title: `Tus fijos suman ${mxn(monthlyRate)} al mes; de aquí a Dic 2026, ${mxn(projected)}`,
} as const;

/** Plan · Lo que entra: nómina (two quincenas) and one extra against the fijos, mayo to octubre. */
const CONTRAST_KEYS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"];
const contrast = CONTRAST_KEYS.map((key) => ({
    key,
    nomina: INCOME,
    extra: key === "2026-06" ? 2400 : 0,
    fijos: FIJOS.reduce((s, f) => s + (lands(f, key) ? f.amount : 0), 0),
}));
const measured = contrast.slice(0, 5);
const covered = measured.filter((m) => m.nomina + m.extra >= m.fijos).length;
const gap = measured.reduce((s, m) => s + m.nomina + m.extra - m.fijos, 0) / measured.length;
export const LO_QUE_ENTRA = {
    months: contrast,
    firstFuture: 5,
    title: `Tus ingresos cubren tus fijos en ${covered} de ${measured.length} meses; en promedio ${gap >= 0 ? "sobran" : "faltan"} ${mxn(Math.abs(gap))} al mes`,
} as const;

/** Pagos: the card payment as the statement prints it, then the month's charges. */
export const PAGOS = {
    card: { bank: "Banamex", amount: 8412.3, due: "22 oct", minimum: 412 },
    /** Octubre 2026 starts on a Thursday; today is the 6th. */
    monthStartsOn: 3,
    days: 31,
    today: 6,
    picked: 12,
    upcoming: FIJOS.filter((f) => lands(f, "2026-10") && f.day >= 6)
        .map((f) => ({ label: f.label, day: f.day, amount: f.amount }))
        .sort((a, b) => a.day - b.day),
    charged: FIJOS.filter((f) => lands(f, "2026-10")).map((f) => f.day),
} as const;

/** Precios: one ticket and the product whose price moved, with the price book's own sentence. */
export const PRECIOS = {
    store: "SORIANA",
    total: "1,412.60",
    rows: [
        ["Huevo 18", "62.00", false],
        ["Leche 1L", "28.50", true],
        ["Tortillas 1kg", "24.00", false],
        ["Jitomate", "31.80", false],
    ] as ReadonlyArray<readonly [string, string, boolean]>,
    product: "Leche",
    /** Price per litre on each ticket, oldest first. */
    history: [23.5, 23.9, 24.2, 23.95, 25.4, 28.5],
    median: 23.95,
    delta: "+19%",
    title: "Leche: hoy $28.50 por litro, 19% sobre lo típico",
} as const;

/**
 * What the backend can read today, by how well it reads it. Mirrors
 * `backend/src/carguito/adapters/outbound/extraction/classifier.py` and
 * `parsing/factory.py`: two banks have a parser written for their layout;
 * the rest are recognised by name and read with the generic parser; the SAT
 * XML has its own reader. Keep this list honest — it is the one place the
 * landing makes a checkable claim.
 */
export const BANKS = {
    dedicated: ["Banamex", "Banco Azteca"],
    generic: ["Nu", "BBVA", "Santander", "Banorte", "HSBC"],
    sat: "XML del SAT (CFDI)",
} as const;
