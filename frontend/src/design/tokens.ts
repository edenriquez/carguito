/**
 * Carguito design tokens — the single source of truth.
 *
 * Imported by `tailwind.config.ts` (Tailwind 3.4 compiles TS configs natively)
 * and by the ApexCharts theme, so CSS and charts cannot drift apart.
 *
 * The system is "quiet analyst's desk on warm paper": a warm-stone canvas, a
 * single cyan accent, and 1px hairlines as the primary structural device.
 * Every contrast ratio below is the WCAG 2.1 relative-luminance formula,
 * measured against Canvas `#fafaf9` unless stated otherwise, because Canvas —
 * not white — is what most text actually sits on.
 */

/* -------------------------------------------------------------------------- */
/* Colour                                                                      */
/* -------------------------------------------------------------------------- */

export const colors = {
    /** Surfaces */
    /** The page. Warm off-white that reads as paper, not screen-white. */
    canvas: "#fafaf9",
    /** Card surfaces, nav, input fills — one elevation step above Canvas. */
    paper: "#ffffff",
    /** Subtle raised/inset surface. Rows on hover, nav active, inert chips. */
    fog: "#f5f4f2",
    /** Hairlines and gridlines — 1.31:1. The structure of the whole UI.
     *  Never a data mark, never text. */
    mist: "#e8e6e5",
    /** Heavier hairline: input borders, decorative separators — 1.60:1. */
    muted: "#d6d3d1",

    /** Text — darkest to lightest */
    /** Headings, metrics, and the label on a Signal button. 19.3:1 on Canvas. */
    ink: "#0c0a09",
    /** Deepest surface: toasts, dark panels, the active tab pill. */
    soot: "#1c1917",
    /**
     * Body copy, labels, captions. 4.62:1 on Canvas, 4.80:1 on Paper — the one
     * secondary text colour. The old three-step grey ramp (graphite/pewter/
     * steel) collapsed to this plus Ash: the reference system uses exactly two
     * recessive text values and a third only invites 3:1 captions.
     */
    graphite: "#78716c",
    /** Tertiary/disabled/icon strokes. 2.42:1 — decorative and disabled only,
     *  never text a user has to read. */
    ash: "#a8a29e",

    /**
     * The one accent. 2.36:1 on Canvas: correct for fills, icons and borders,
     * NOT for text on a light surface. Button labels on Signal are Ink (5.60:1)
     * — white would be 2.36:1 and fails AA at every size.
     */
    signal: "#3ba6f1",
    /** The accent as *text*: 3.16:1 on Canvas, 4.51:1 on Wash. Only ever used
     *  on a Wash pill (the highlight span) or as a 1px outlined border. */
    edge: "#3398e1",
    /**
     * Signal with enough weight under it to carry white: Paper on this is
     * 5.04:1, where Paper on Signal is 2.36:1 and fails at every size. Two
     * steps down the tint ramp from Signal, same hue.
     *
     * For the one control on a page that has to lead it, and nothing else —
     * a second filled blue would make both of them furniture. Everywhere else
     * the accent is still Signal as a fill with an Ink label, or Edge as text.
     */
    signalDeep: "#1c73b5",
    /** The same fill, pressed on. Hover on a flat control is a step of the
     *  same colour, not a lift and not a filter: Paper on this is 6.68:1, so
     *  the label gets *more* readable as the surface darkens. */
    signalDeeper: "#17618f",
    /** The pill behind a highlight span. Carries Edge text at 4.51:1. */
    wash: "#c1e1f7",

    /**
     * Semantic, narrowly scoped: deltas and amounts at text scale.
     * Never a chart fill, never a background.
     *
     * A deliberate deviation from the reference guide's "one accent only" rule.
     * In a ledger, the sign of a number is information, not decoration —
     * rendering a loss in the same grey as a gain would cost the user more than
     * the restraint buys. Both are warm-shifted to sit inside the stone palette.
     */
    positive: "#15704a", // 5.72:1 on Canvas
    negative: "#a8322a", // 6.02:1 on Canvas
} as const;

/**
 * Chart palettes.
 *
 * Hue is NOT the categorical channel here — the brand permits one accent.
 * Nominal categories use the warm stone ramp ordered by value with Signal
 * marking the series the widget is *about*; quantitative encodings (treemap,
 * heatmap) use the Signal tint ramp.
 */
export const chart = {
    /** Nominal categories. Six steps, each >=3:1 on Canvas, adjacent steps ~1.3x apart. */
    neutral: ["#1c1917", "#3b3532", "#57504b", "#78716c", "#918a84", "#a8a29e"],
    /** Continuous magnitude. One colour, the brand colour. Tile text flips to Ink below step 3. */
    signalTint: ["#1f7fc7", "#3ba6f1", "#7cc4f6", "#a8d8fa", "#c1e1f7"],
    /** Two-series comparison uses texture, not hue. */
    grid: colors.mist,
    axisLabel: colors.graphite,
} as const;

/* -------------------------------------------------------------------------- */
/* Type                                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Tres reglas van cosidas a la escala para que sean mecánicas y no memoria:
 *
 * 1. Display es una serif de texto (Instrument Serif), siempre 400 y nunca
 *    bajo 24 px. La opinión sale de las palabras, del contraste y del tamaño,
 *    nunca del peso. Tracking 0: el tracking negativo es hábito de grotesca y
 *    en una serif condensada choca las letras.
 * 2. Los números no tienen opinión. Toda cifra, label, celda y título de
 *    contenedor va en Inter (`tabular`); los tokens `metric-*` son de Inter y
 *    los números nunca toman tokens de palabras.
 * 3. El cuerpo 14/1.64 es el ritmo dominante; no romperlo.
 */
export const fontSize = {
    /** Words in the display face. >=24px is the floor for the serif. */
    "display-lg": ["72px", { lineHeight: "1.04", letterSpacing: "0" }],
    display: ["52px", { lineHeight: "1.08", letterSpacing: "0" }],
    "title-lg": ["32px", { lineHeight: "1.15", letterSpacing: "0" }],
    "title-md": ["24px", { lineHeight: "1.2", letterSpacing: "0" }],
    /** Below the serif floor: Inter 500. Card titles, container titles, sheet titles. */
    "title-sm": ["20px", { lineHeight: "1.2", letterSpacing: "-0.012em" }],
    "body-lg": ["16px", { lineHeight: "1.69", letterSpacing: "0.003em" }],
    body: ["14px", { lineHeight: "1.64", letterSpacing: "0.004em" }],
    "body-sm": ["13px", { lineHeight: "1.53", letterSpacing: "0.004em" }],
    label: ["12px", { lineHeight: "1.33", letterSpacing: "0.004em" }],
    /** All-caps eyebrows. The wide tracking is the point — it lives here, not in `.eyebrow`. */
    caption: ["10px", { lineHeight: "1.6", letterSpacing: "0.08em" }],
    /** Numbers that are the point of the card. Always Inter, always tabular, always weight 400. */
    metric: ["32px", { lineHeight: "1.15", letterSpacing: "-0.025em" }],
    "metric-sm": ["20px", { lineHeight: "1.2", letterSpacing: "-0.015em" }],
    /** La cifra del hero; los números nunca toman tokens de palabras. */
    "metric-lg": ["56px", { lineHeight: "1", letterSpacing: "-0.03em" }],
    "metric-xl": ["96px", { lineHeight: "1", letterSpacing: "-0.035em" }],
} as const;

/** Los únicos dos pesos del sistema. Set at `theme.fontWeight` (not `extend`) so `font-semibold` does not exist. */
export const fontWeight = { normal: "400", medium: "500" } as const;

export const fontFamily: Record<string, string[]> = {
    sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
    /**
     * Instrument Serif, 400 only, from next/font/google. Words at >=24px: the
     * hero, section H2s, onboarding, Plan headlines, empty-state titles, FAQ
     * questions. Never a number, a label or a container title — those are
     * Inter. Inter is deliberately absent from this chain: a serif that fell
     * back to a grotesque would hide a failed font load.
     */
    display: ["var(--font-display)", "Georgia", "Times New Roman", "serif"],
};

/* -------------------------------------------------------------------------- */
/* Shape                                                                       */
/* -------------------------------------------------------------------------- */

export const borderRadius = {
    none: "0",
    /** Inline tags and chips. Pills, like every other interactive affordance. */
    tag: "9999px",
    /** Buttons and interactive pills. The guide is explicit: fully round. */
    control: "9999px",
    /** Inputs stay rectangular-ish — a pill text field is a search box, not a form. */
    input: "6px",
    card: "10px",
    /** Feature cards, the dropzone, the floating preview. */
    panel: "16px",
    sheet: "16px",
    full: "9999px",
} as const;

/**
 * Elevation is expressed with hairlines first and shadow second. `card` is a
 * whisper — it lifts the surface off the warm canvas without reading as a
 * shadow. `float` is reserved for exactly one element per screen: the centred
 * Modal, or a hero product preview, which have nothing behind them to anchor to.
 */
export const boxShadow = {
    none: "none",
    subtle: "rgba(0, 0, 0, 0.05) 0px 1px 2px 0px",
    card: "rgba(0, 0, 0, 0.05) 0px 4px 16px 0px",
    chip: "rgba(0, 0, 0, 0.1) 0px 4px 6px -1px, rgba(0, 0, 0, 0.1) 0px 2px 4px -2px",
    float: "rgba(17, 12, 46, 0.12) 0px 12px 45px 0px",
    /**
     * A field that leads its header. Two layers and neither one visible on its
     * own: a 1px contact shadow that seats the bar on the canvas, and a wide
     * soft one that gives it height without drawing an edge.
     *
     * Large, diffuse and nearly transparent on purpose. The tight high-opacity
     * shadow is what reads as an old button; spread is what reads as depth.
     *
     * The leading layer is a halo at zero spread and zero alpha — invisible,
     * and there only so this value and {@link fieldFocus} have the same number
     * of shadows. CSS cannot interpolate `box-shadow` between two values with
     * different layer counts: it snaps. With the layer present at nothing, the
     * focus halo grows out of nothing instead.
     */
    field:
        "0 0 0 0 rgba(59, 166, 241, 0), 0 1px 2px rgba(12, 10, 9, 0.04), 0 10px 28px -12px rgba(12, 10, 9, 0.12)",
    /**
     * The same field with focus. Both depth layers grow, and the halo comes up
     * to 4px of the accent at 16% — the job a hard focus ring does, with far
     * less noise. Same three layers in the same order as {@link field}, which
     * is what lets it animate rather than snap.
     */
    fieldFocus:
        "0 0 0 4px rgba(59, 166, 241, 0.16), 0 2px 4px rgba(12, 10, 9, 0.05), 0 18px 44px -14px rgba(12, 10, 9, 0.18)",
} as const;

/**
 * Layout. `page` is the content measure inside the app shell — wide enough for
 * a 12-column widget grid, narrow enough that a table row doesn't become a
 * scan across a 27" monitor. `prose` is the measure for the onboarding hero,
 * where a 52px headline needs to break after ~3 words per line.
 */
export const maxWidth = {
    page: "1200px",
    prose: "640px",
} as const;

export const zIndex = {
    sheet: 40,
    modal: 50,
    toast: 60,
} as const;
