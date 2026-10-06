"use client";

import { useState, type KeyboardEvent } from "react";
import { chart, colors } from "@/design/tokens";
import { cn } from "@/lib/cn";
import { mxn } from "@/lib/format";
import { DECILE_LABELS, ENIGH_MONTHLY, ENIGH_YEAR, decileIndex } from "@/lib/enigh";
import { TIER_LABELS, TIER_ORDER, type Leaf, type Tier, type TierSlice } from "@/lib/lecturaEstado";
import { monthKeyToDate, type MonthKey } from "@/lib/porMes";
import { useChartTip } from "./useChartTip";

/*
 * The eight charts of the Lectura face. Each one draws one claim and marks the
 * thing the claim is about in Signal; everything else is the stone ramp. They
 * are hand-drawn SVG rather than Apex because each is a single bespoke shape
 * (a decile strip, a day grid, a split bar) and each animates in its own way
 * on first sight — see `.lx-*` in globals.css. The parent card passes `play`.
 */

export const MONTH_SHORT = new Intl.DateTimeFormat("es-MX", { month: "short" });
export const monthShort = (key: MonthKey) => MONTH_SHORT.format(monthKeyToDate(key)).replace(".", "");
export const k = (n: number) => `$${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
// `--lx-fs` is set by useChartTip in «Gráficas v2» only, so v1 renders 11 as before.
export const TEXT = { fontSize: "calc(11px * var(--lx-fs, 1))", fill: colors.graphite } as const;

/** v2: a shortfall drawn in HTML — Negative hatched over Paper with a Negative
 *  edge. Negative is a text color and never a chart fill (tokens.ts), so the
 *  red rides on thin stripes and the outline, not on a solid block. */
export const NEGATIVE_HATCH = {
    background: `repeating-linear-gradient(45deg, ${colors.negative} 0 1.5px, ${colors.paper} 1.5px 5px)`,
    boxShadow: `inset 0 0 0 1px ${colors.negative}`,
} as const;

/** The latest month when the record stops before its last day: drawn apart and labelled «al {day}» in v2. */
export type PartialMonth = { key: MonthKey; day: number } | null;
/** A month's axis label, with «al {day}» on the partial one. */
export const monthAxis = (key: MonthKey, partial: PartialMonth) =>
    partial?.key === key ? `${monthShort(key)} · al ${partial.day}` : monthShort(key);

/* ------------------------------------------------------------------ 1 · Decil */

/**
 * The ENIGH itself, decile by decile: what a household spends a month (the
 * bar) and what it takes in (under the bar), with the user's own monthly
 * spend drawn across all ten. Where that line meets the bars is the claim in
 * the title — the decile is read off the survey, not asserted beside it.
 * With an income, its decile is marked under the axis, so the two readings
 * of "where am I" sit on the same chart.
 */
export function DecilChart({ spend, spendP, income, incomeP }: {
    spend: number;
    spendP: number;
    income: number | null;
    incomeP: number | null;
}) {
    const { box, bind, node, v2, accent } = useChartTip();
    const spendD = decileIndex(spendP);
    const incomeD = incomeP === null ? null : decileIndex(incomeP);
    const base = 168, top = 24;
    const max = Math.max(spend, ...ENIGH_MONTHLY.gasto) * 1.1;
    const y = (v: number) => base - ((base - top) * Math.min(v, max)) / max;
    // A gutter at the left names the two rows of figures once, so each column
    // carries only its numbers.
    const left = 46, slot = (600 - left) / 10, bw = 32;
    const cx = (i: number) => left + i * slot + slot / 2;
    const ys = y(spend);
    return (
        <div ref={box} className="relative">
            <p className="mb-2 text-label text-ash">Gasto al mes por hogar, por decil de ingreso · ENIGH {ENIGH_YEAR}</p>
            <svg viewBox="0 0 600 228" className="w-full overflow-visible" role="img" aria-label={`Tu gasto de ${mxn(spend)} al mes cae en el decil ${DECILE_LABELS[spendD]}`}>
                {DECILE_LABELS.map((label, i) => {
                    const gasto = ENIGH_MONTHLY.gasto[i]!;
                    const ingreso = ENIGH_MONTHLY.ingreso[i]!;
                    const on = i === spendD;
                    const x = cx(i) - bw / 2;
                    return (
                        <g key={label} {...bind(`Decil ${label} · gasta ${mxn(gasto)} al mes · ingresa ${mxn(ingreso)} al mes`)}>
                            <rect x={cx(i) - slot / 2} y={top} width={slot} height={base - top} fill="transparent" />
                            <rect className="lx-grow" style={{ transitionDelay: `${i * 60}ms` }} x={x} y={y(gasto)} width={bw} height={base - y(gasto)} rx={2} fill={on ? colors.signal : colors.muted} />
                            {incomeD === i && <circle cx={cx(i)} cy={base + 8} r={2.5} fill={colors.soot} />}
                            {/* v2: the income decile is named on its column, not
                                only a dot under the axis the eye skips. */}
                            {v2 && incomeD === i && (
                                <text x={cx(i)} y={y(gasto) - 6} textAnchor="middle" style={{ ...TEXT, fill: colors.ink, fontWeight: 500 }}>Ingresas aquí</text>
                            )}
                            <text x={cx(i)} y={base + 24} textAnchor="middle" style={{ ...TEXT, fill: on ? accent : colors.graphite, fontWeight: on ? 500 : 400 }}>{label}</text>
                            <text x={cx(i)} y={base + 39} textAnchor="middle" style={{ ...TEXT, fill: on ? accent : colors.graphite }}>{k(gasto)}</text>
                            <text x={cx(i)} y={base + 54} textAnchor="middle" style={{ ...TEXT, fill: colors.ash }}>{k(ingreso)}</text>
                        </g>
                    );
                })}
                <text x={0} y={base + 24} style={{ ...TEXT, fill: colors.ash }}>Decil</text>
                <text x={0} y={base + 39} style={{ ...TEXT, fill: colors.ash }}>Gasta</text>
                <text x={0} y={base + 54} style={{ ...TEXT, fill: colors.ash }}>Gana</text>
                {/* The figures sit under the axis, not on the bars: the user's
                    line crosses the bars near their decile's top, and would run
                    through a figure there. Its own label is at the left, where
                    the bars are short. */}
                <g className="lx-fade" style={{ transitionDelay: "800ms" }}>
                    <line x1={left} x2={600} y1={ys} y2={ys} stroke={colors.signal} strokeDasharray="4 3" />
                    <text x={left} y={ys - 6} style={{ ...TEXT, fill: accent, fontWeight: 500 }}>
                        Tú gastas {mxn(spend)}
                    </text>
                </g>
            </svg>
            {incomeD !== null && income !== null && (
                <p className="mt-1 flex items-center gap-1.5 text-label text-graphite">
                    <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-soot" />
                    Tu ingreso de {mxn(income)} cae en el decil {DECILE_LABELS[incomeD]}
                </p>
            )}
            {node}
        </div>
    );
}

/* ---------------------------------------------------------------- 2 · Balance */

export function BalanceChart({ months, income, partial = null }: {
    months: { key: MonthKey; amount: number; count: number }[];
    income: number;
    partial?: PartialMonth;
}) {
    const { box, bind, node, v2 } = useChartTip();
    // v2: what spills over the income is a shortfall, not "you": it leaves
    // Signal for a Negative hatch and outline (Negative is never a solid chart
    // fill) and carries its own figure.
    const overFill = v2 ? "url(#lx-hatch-negative)" : colors.signal;
    const base = 170, top = 18;
    const max = Math.max(income, ...months.map((m) => m.amount)) * 1.12 || 1;
    const y = (v: number) => base - ((base - top) * v) / max;
    const bw = 58, gap = (560 - bw * months.length) / Math.max(1, months.length - 1);
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 200" className="w-full overflow-visible" role="img" aria-label="Gasto por mes contra tu ingreso">
                {v2 && (
                    <defs>
                        <pattern id="lx-hatch-negative" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                            <rect width="5" height="5" fill={colors.paper} />
                            <line x1="0" y1="0" x2="0" y2="5" stroke={colors.negative} strokeWidth="1.5" />
                        </pattern>
                    </defs>
                )}
                {months.map((m, i) => {
                    const x = 20 + i * (bw + gap);
                    const under = Math.min(m.amount, income), over = Math.max(0, m.amount - income);
                    const part = v2 && partial?.key === m.key;
                    const tip = m.count === 0
                        ? `${monthShort(m.key)} · sin cargos en el registro`
                        : `${monthShort(m.key)} · gasto ${mxn(m.amount)} · ${over > 0 ? `${mxn(over)} arriba de tu ingreso` : `${mxn(income - m.amount)} por debajo`}`;
                    return (
                        <g key={m.key} {...bind(tip)}>
                            <rect x={x} y={top} width={bw} height={base - top} fill="transparent" />
                            <g opacity={part ? 0.45 : 1}>
                                <rect className="lx-grow" style={{ transitionDelay: `${i * 80}ms` }} x={x} y={y(under)} width={bw} height={base - y(under)} rx={2} fill={colors.graphite} />
                                {over > 0 && (
                                    <rect className="lx-fade" style={{ transitionDelay: `${800 + i * 90}ms` }} x={x} y={y(m.amount)} width={bw} height={y(under) - y(m.amount)} rx={2} fill={overFill} {...(v2 && { stroke: colors.negative, strokeWidth: 1 })} />
                                )}
                            </g>
                            {m.count > 0 && !v2 && (
                                <text className="lx-fade" style={{ ...TEXT, fill: over > 0 ? colors.edge : colors.graphite, transitionDelay: `${600 + i * 80}ms` }} x={x + bw / 2} y={y(m.amount) - 6} textAnchor="middle">
                                    {Math.round(m.amount).toLocaleString("en-US")}
                                </text>
                            )}
                            {m.count > 0 && v2 && (
                                <text className="lx-fade" style={{ ...TEXT, transitionDelay: `${600 + i * 80}ms` }} x={x + bw / 2} y={y(m.amount) - 6} textAnchor="middle">
                                    {over > 0 && <tspan x={x + bw / 2} dy="-1.2em" fill={colors.negative} fontWeight={500}>+{k(over)}</tspan>}
                                    <tspan x={x + bw / 2} dy={over > 0 ? "1.2em" : 0}>{k(m.amount)}</tspan>
                                </text>
                            )}
                            <text x={x + bw / 2} y={base + 18} textAnchor="middle" style={TEXT}>{v2 ? monthAxis(m.key, partial) : monthShort(m.key)}</text>
                        </g>
                    );
                })}
                <line className="lx-fade" style={{ transitionDelay: "500ms" }} x1={10} x2={590} y1={y(income)} y2={y(income)} stroke={colors.ash} strokeDasharray="4 4" />
                <text className="lx-fade" style={{ ...TEXT, transitionDelay: "500ms" }} x={590} y={y(income) - 6} textAnchor="end">Ingreso {mxn(income)}</text>
            </svg>
            {node}
        </div>
    );
}

/* ------------------------------------------------------------- 3 · Día del mes */

const STRETCHES = [
    { from: 1, to: 10 },
    { from: 11, to: 20 },
    { from: 21, to: 31 },
] as const;

/**
 * A histogram of the month: one bar per day of the month, summed over the
 * span, in the three stretches the title reads. The days the title is about
 * are Signal — after the 10th when it says "la segunda mitad", up to it when
 * it says "al inicio" — and with no lean, only the heaviest day is. The
 * heaviest day carries its figure.
 */
export function DiasChart({ byDay, shares, focus }: {
    byDay: number[];
    shares: [number, number, number];
    focus: "early" | "late" | null;
}) {
    const { box, bind, node, accent } = useChartTip();
    const max = Math.max(...byDay) || 1;
    const peak = byDay.indexOf(max);
    const base = 128, top = 18;
    const slot = 580 / byDay.length, bw = slot * 0.7;
    const x = (i: number) => 10 + i * slot;
    const h = (v: number) => ((base - top) * v) / max;
    const on = (i: number) => (focus === "late" ? i >= 10 : focus === "early" ? i < 10 : i === peak);
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 176" className="w-full overflow-visible" role="img" aria-label={`Gasto por día del mes: ${STRETCHES.map((s, i) => `días ${s.from} a ${s.to}, ${Math.round(shares[i]! * 100)}%`).join("; ")}`}>
                {/* The stretch boundaries, so the three shares under the axis
                    read against the bars they sum. */}
                {[10, 20].map((d) => (
                    <line key={d} x1={x(d) - (slot - bw) / 2} x2={x(d) - (slot - bw) / 2} y1={top - 6} y2={base} stroke={colors.mist} strokeDasharray="3 3" />
                ))}
                <line x1={10} x2={590} y1={base} y2={base} stroke={colors.mist} />
                {byDay.map((v, i) => (
                    <g key={i} {...bind(`Día ${i + 1} · ${mxn(v)}`)}>
                        <rect x={x(i)} y={top} width={slot} height={base - top} fill="transparent" />
                        <rect
                            className="lx-grow"
                            style={{ transitionDelay: `${i * 20}ms` }}
                            x={x(i) + (slot - bw) / 2}
                            y={base - h(v)}
                            width={bw}
                            height={h(v)}
                            rx={1.5}
                            fill={on(i) ? colors.signal : colors.muted}
                        />
                        {i === peak && v > 0 && (
                            <text className="lx-fade" style={{ ...TEXT, fill: accent, transitionDelay: "700ms" }} x={x(i) + slot / 2} y={base - h(v) - 6} textAnchor="middle">
                                {k(v)}
                            </text>
                        )}
                        {[0, 4, 9, 14, 19, 24, byDay.length - 1].includes(i) && (
                            <text x={x(i) + slot / 2} y={base + 14} textAnchor="middle" style={{ ...TEXT, fill: colors.ash }}>{i + 1}</text>
                        )}
                    </g>
                ))}
                {STRETCHES.map((s, i) => {
                    const mid = (x(s.from - 1) + x(Math.min(s.to, byDay.length))) / 2;
                    const lit = focus === "late" ? i > 0 : focus === "early" ? i === 0 : false;
                    return (
                        <text key={s.from} x={mid} y={base + 38} textAnchor="middle" style={{ ...TEXT, fill: lit ? accent : colors.graphite, fontWeight: lit ? 500 : 400 }}>
                            Días {s.from}–{s.to} · {Math.round(shares[i]! * 100)}%
                        </text>
                    );
                })}
            </svg>
            {node}
        </div>
    );
}

/* -------------------------------------------------------- 4 · Fin de semana */

const WEEKDAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];

export function SemanaChart({ byWeekday, share }: { byWeekday: { amount: number; count: number }[]; share: number }) {
    const { box, bind, node, v2, accent } = useChartTip();
    const max = Math.max(...byWeekday.map((d) => d.amount)) || 1;
    return (
        <div ref={box} className="relative">
            {/* v2: the fair share — two of seven days — marked on the strip,
                so "more than its days" reads off the bar, not the foot. */}
            {v2 && (
                <div className="relative mb-1 h-4 text-label tabular text-graphite">
                    <span className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${(2 / 7) * 100}%` }}>2 de 7 días · 29%</span>
                </div>
            )}
            <div className="relative">
                <div className="flex h-3 overflow-hidden rounded-full bg-mist">
                    <div className="lx-growx h-full bg-signal" style={{ width: `${share * 100}%` }} />
                </div>
                {v2 && <span aria-hidden className="absolute -top-1 h-5 w-px bg-ink" style={{ left: `${(2 / 7) * 100}%` }} />}
            </div>
            <div className="mt-2 flex justify-between text-label tabular">
                <span className={v2 ? "text-signalDeep" : "text-edge"}>Fin de semana · {Math.round(share * 100)}%</span>
                <span className="text-graphite">Entre semana · {Math.round((1 - share) * 100)}%</span>
            </div>
            <svg viewBox="0 0 600 110" className="mt-4 w-full overflow-visible" role="img" aria-label="Gasto por día de la semana">
                {byWeekday.map((d, i) => {
                    const bw = 60, x = 10 + i * ((580 - bw) / 6), h = (80 * d.amount) / max, we = i >= 5;
                    return (
                        <g key={i} {...bind(`${WEEKDAYS[i]} · ${mxn(d.amount)} · ${d.count} cargos`)}>
                            <rect x={x} y={0} width={bw} height={84} fill="transparent" />
                            <rect className="lx-grow" style={{ transitionDelay: `${300 + i * 60}ms` }} x={x} y={84 - h} width={bw} height={h} rx={2} fill={we ? colors.signal : colors.ash} />
                            <text x={x + bw / 2} y={102} textAnchor="middle" style={{ ...TEXT, fill: we ? accent : colors.graphite }}>{WEEKDAYS[i]}</text>
                        </g>
                    );
                })}
            </svg>
            {node}
        </div>
    );
}

/* ------------------------------------------------------------- 5 · Necesidad */

const TIER_FILL: Record<Tier, string> = {
    primera: colors.soot,
    segunda: "#57534e",
    tercera: colors.ash,
    deuda: colors.signal,
    sin: "url(#lx-hatch)",
};

// v2: Signal goes to the level the card's title names (primera), and the rest
// take separated steps of the stone ramp instead of two neighbouring greys.
const TIER_FILL_V2: Record<Tier, string> = {
    primera: colors.signal,
    segunda: chart.neutral[0],
    tercera: chart.neutral[2],
    deuda: chart.neutral[4],
    sin: "url(#lx-hatch)",
};

export function NecesidadChart({ tiers }: { tiers: TierSlice[] }) {
    const { box, bind, node, v2 } = useChartTip();
    const fills = v2 ? TIER_FILL_V2 : TIER_FILL;
    const [open, setOpen] = useState<Tier | null>(null);
    const toggle = (tier: Tier) => setOpen((cur) => (cur === tier ? null : tier));
    let x = 0;
    // The bar's segments, laid out once so the selection outline can be drawn
    // over them as its own element.
    const segments = TIER_ORDER.flatMap((tier) => {
        const t = tiers.find((s) => s.tier === tier)!;
        const w = t.share * 600;
        const at = x;
        x += w;
        return w > 0 ? [{ tier, t, at, w }] : [];
    });
    const picked = segments.find((s) => s.tier === open);
    return (
        <div ref={box} className="relative">
            {/* Two units of room above and below the bar: the selection ring
                is drawn *outside* the segment, and a viewBox cut flush to the
                bar clipped its top and bottom edges away. */}
            <svg viewBox="-2 -2 604 26" className="w-full overflow-visible" role="img" aria-label="Tu gasto por nivel de necesidad">
                <defs>
                    <pattern id="lx-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                        <rect width="6" height="6" fill={colors.fog} />
                        <line x1="0" y1="0" x2="0" y2="6" stroke={colors.muted} strokeWidth="2" />
                    </pattern>
                </defs>
                {segments.map(({ tier, t, at, w }, i) => (
                    <rect
                        key={tier}
                        className="lx-growx cursor-pointer"
                        style={{ transitionDelay: `${i * 160}ms` }}
                        x={at}
                        y={0}
                        width={Math.max(1, w - 2)}
                        height={22}
                        rx={2}
                        fill={fills[tier]}
                        // The others step back instead of the picked one
                        // growing a border: the segment keeps its size, and
                        // the eye lands on the one still at full strength.
                        opacity={open && open !== tier ? 0.35 : 1}
                        onClick={() => toggle(tier)}
                        {...bind(`${TIER_LABELS[tier]} · ${mxn(t.amount)} · ${Math.round(t.share * 100)}%`)}
                        {...(v2 && {
                            role: "button",
                            "aria-pressed": open === tier,
                            "aria-label": `${TIER_LABELS[tier]}, ${Math.round(t.share * 100)}%`,
                            onKeyDown: (e: KeyboardEvent) => {
                                if (e.key !== "Enter" && e.key !== " ") return;
                                e.preventDefault();
                                toggle(tier);
                            },
                        })}
                    />
                ))}
                {picked && (
                    <rect
                        aria-hidden
                        pointerEvents="none"
                        x={picked.at - 1}
                        y={-1}
                        width={Math.max(1, picked.w - 2) + 2}
                        height={24}
                        rx={3}
                        fill="none"
                        stroke={v2 ? colors.ink : colors.signal}
                        strokeWidth={2}
                    />
                )}
            </svg>
            <ul className="mt-4 divide-y divide-mist">
                {TIER_ORDER.map((tier) => {
                    const t = tiers.find((s) => s.tier === tier)!;
                    const on = open === tier;
                    return (
                        <li key={tier}>
                            <button
                                type="button"
                                onClick={() => toggle(tier)}
                                className={cn(
                                    "-mx-2 flex w-[calc(100%+1rem)] items-center gap-2.5 rounded-input px-2 py-2 text-left text-body-sm transition-colors duration-100",
                                    on ? "bg-fog" : "hover:bg-fog/60"
                                )}
                                aria-expanded={on}
                            >
                                <svg width="10" height="10" aria-hidden className="shrink-0"><rect width="10" height="10" rx="2" fill={tier === "sin" ? colors.mist : fills[tier]} /></svg>
                                <span className={cn("flex-1", tier === "sin" ? "text-graphite" : "text-ink", on && "font-medium")}>{TIER_LABELS[tier]}</span>
                                <span className="tabular text-graphite">{Math.round(t.share * 100)}%</span>
                                <span className="w-20 text-right tabular text-ink">{mxn(t.amount)}</span>
                            </button>
                            {/* The categories behind a level, under its own row:
                                the panel used to open below the whole list,
                                a pill-rounded box far from the row it explained. */}
                            {on && (
                                <div className="mb-2 mt-1 rounded-input border border-mist bg-paper px-3 py-1.5">
                                    {t.leaves.length === 0 ? (
                                        <p className="py-1 text-label text-graphite">Sin cargos en este nivel.</p>
                                    ) : (
                                        t.leaves.slice(0, 8).map((l: Leaf) => (
                                            <div key={l.name} className="flex items-baseline justify-between gap-3 border-b border-mist py-1.5 text-label last:border-0">
                                                <span className="min-w-0 truncate text-ink">
                                                    {l.name} <span className="text-graphite">· {l.count} {l.count === 1 ? "cargo" : "cargos"}</span>
                                                </span>
                                                <span className="tabular shrink-0 text-ink">{mxn(l.amount)}</span>
                                            </div>
                                        ))
                                    )}
                                </div>
                            )}
                        </li>
                    );
                })}
            </ul>
            {node}
        </div>
    );
}

/* ---------------------------------------------------------- 6 · Horas de vida */

export function HorasChart({ rows, hourValue, highlight }: {
    rows: Leaf[];
    hourValue: number;
    highlight: string | null;
}) {
    const { box, bind, node, v2 } = useChartTip();
    const max = Math.max(...rows.map((r) => r.amount)) || 1;
    return (
        <div ref={box} className="relative space-y-3">
            {rows.map((r, i) => {
                const hours = Math.round(r.amount / hourValue);
                const on = r.name === highlight;
                return (
                    <div key={r.name} {...bind(`${r.name} · ${mxn(r.amount)} · ${Math.round(hours / 8)} jornadas de 8 h`)}>
                        <div className="flex justify-between text-body-sm">
                            <span className={on ? "text-ink" : "text-graphite"}>{r.name}</span>
                            <span className={cn("tabular", on ? (v2 ? "text-signalDeep" : "text-edge") : "text-graphite")}>{hours} h</span>
                        </div>
                        <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-fog">
                            <div className="lx-growx h-full rounded-full" style={{ width: `${(r.amount / max) * 100}%`, background: on ? colors.signal : colors.graphite, transitionDelay: `${i * 90}ms` }} />
                        </div>
                    </div>
                );
            })}
            {node}
        </div>
    );
}

/* ------------------------------------------------------- 7 · Segunda por mes */

export function SegundaChart({ months, partial = null }: { months: { key: MonthKey; segunda: number }[]; partial?: PartialMonth }) {
    const { box, bind, node, v2 } = useChartTip();
    const base = 130, top = 16;
    const max = Math.max(...months.map((m) => m.segunda)) * 1.15 || 1;
    const step = 560 / Math.max(1, months.length - 1);
    const pts = months.map((m, i) => [20 + i * step, base - ((base - top) * m.segunda) / max] as const);
    const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
    const peak = months.reduce((b, m, i) => (m.segunda > months[b]!.segunda ? i : b), 0);
    // v2 labels only the two points the title reads — where it started and
    // its peak — and lets the others step back.
    const start = Math.max(0, months.findIndex((m) => m.segunda > 0));
    const named = (i: number) => i === start || i === peak;
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 176" className="w-full overflow-visible" role="img" aria-label="Gasto de segunda necesidad por mes">
                {[0.33, 0.66].map((f) => (
                    <line key={f} x1={10} x2={590} y1={base - (base - top) * f} y2={base - (base - top) * f} stroke={colors.mist} strokeDasharray="3 4" />
                ))}
                <path d={`${d} L${pts[pts.length - 1]![0]} ${base} L${pts[0]![0]} ${base} Z`} className="lx-fade" style={{ transitionDelay: "900ms" }} fill={colors.wash} opacity={0.45} />
                <path d={d} pathLength={1} className="lx-draw" fill="none" stroke={colors.signal} strokeWidth={2.5} strokeDasharray="1" strokeDashoffset={0} />
                {months.map((m, i) =>
                    !v2 ? (
                        <g key={m.key} {...bind(`${monthShort(m.key)} · ${mxn(m.segunda)} de segunda necesidad`)}>
                            <circle className="lx-fade" style={{ transitionDelay: `${200 + i * 180}ms` }} cx={pts[i]![0]} cy={pts[i]![1]} r={5} fill={colors.paper} stroke={colors.signal} strokeWidth={2} />
                            <text x={pts[i]![0]} y={base + 20} textAnchor="middle" style={TEXT}>{monthShort(m.key)}</text>
                            <text x={pts[i]![0]} y={base + 36} textAnchor="middle" style={{ ...TEXT, fill: i === peak ? colors.ink : colors.ash }}>{k(m.segunda)}</text>
                        </g>
                    ) : (
                        <g key={m.key} {...bind(`${monthAxis(m.key, partial)} · ${mxn(m.segunda)} de segunda necesidad`)}>
                            <circle className="lx-fade" style={{ transitionDelay: `${200 + i * 180}ms` }} cx={pts[i]![0]} cy={pts[i]![1]} r={named(i) ? 5 : 3.5} fill={colors.paper} stroke={named(i) ? colors.signal : colors.ash} strokeWidth={2} opacity={partial?.key === m.key ? 0.45 : 1} />
                            <text x={pts[i]![0]} y={base + 20} textAnchor="middle" style={TEXT}>{monthAxis(m.key, partial)}</text>
                            {named(i) && <text x={pts[i]![0]} y={base + 36} textAnchor="middle" style={{ ...TEXT, fill: colors.ink, fontWeight: i === peak ? 500 : 400 }}>{k(m.segunda)}</text>}
                        </g>
                    )
                )}
            </svg>
            {node}
        </div>
    );
}
