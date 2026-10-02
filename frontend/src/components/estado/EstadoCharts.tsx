"use client";

import { useState, type CSSProperties } from "react";
import { colors } from "@/design/tokens";
import { cn } from "@/lib/cn";
import { mxn } from "@/lib/format";
import { DECILE_LABELS, ENIGH_MONTHLY, decileIndex } from "@/lib/enigh";
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
export const TEXT = { fontSize: 11, fill: colors.graphite } as const;

/* ------------------------------------------------------------------ 1 · Decil */

/** A 0–100 percentile on the strip's x axis. */
const stripX = (p: number) => 10 + (p / 100) * 580;

export function DecilChart({ income, spendP, incomeP, equivalent }: {
    income: number | null;
    spendP: number;
    incomeP: number | null;
    equivalent: number;
}) {
    const { box, bind, node } = useChartTip();
    const spendD = decileIndex(spendP);
    const xs = stripX(spendP);
    const xi = incomeP === null ? null : stripX(incomeP);
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 132" className="w-full overflow-visible" role="img" aria-label={`Tu gasto cae en el decil ${DECILE_LABELS[spendD]}`}>
                {DECILE_LABELS.map((label, i) => {
                    const a = stripX(i * 10) + 2, b = stripX(i * 10 + 10) - 2;
                    const on = i === spendD;
                    return (
                        <g key={label} {...bind(`Decil ${label} · ingreso ${mxn(ENIGH_MONTHLY.ingreso[i]!)}/mes · gasto ${mxn(ENIGH_MONTHLY.gasto[i]!)}/mes`)}>
                            <rect x={a} y={64} width={b - a} height={14} rx={2} fill={on ? colors.wash : colors.fog} />
                            <text x={(a + b) / 2} y={98} textAnchor="middle" style={{ ...TEXT, fill: on ? colors.edge : colors.graphite }}>{label}</text>
                            <text x={(a + b) / 2} y={114} textAnchor="middle" style={{ ...TEXT, fill: colors.ash }}>{k(ENIGH_MONTHLY.ingreso[i]!)}</text>
                        </g>
                    );
                })}
                {xi !== null && (
                    <>
                        <rect className="lx-growx lx-fade" style={{ transitionDelay: "900ms" }} x={Math.min(xi, xs)} y={64} width={Math.abs(xs - xi)} height={14} fill={colors.signal} opacity={0.3} />
                        <line x1={xi} x2={xi} y1={36} y2={62} stroke={colors.graphite} />
                        <circle cx={xi} cy={71} r={7} fill={colors.paper} stroke={colors.soot} strokeWidth={2} />
                        <text x={xi} y={28} textAnchor={xi > xs ? "start" : "end"} dx={xi > xs ? -8 : 8} style={{ ...TEXT, fill: colors.ink, fontWeight: 500 }}>
                            Ganas {mxn(income!)}
                        </text>
                    </>
                )}
                <g className="lx-slide" style={{ "--lx-from": `${(xi ?? xs) - xs}px` } as CSSProperties}>
                    <line x1={xs} x2={xs} y1={14} y2={62} stroke={colors.signal} />
                    <circle cx={xs} cy={71} r={7} fill={colors.signal} />
                    <text x={xs} y={8} textAnchor={xs > 420 ? "end" : "middle"} style={{ ...TEXT, fill: colors.edge, fontWeight: 500 }}>
                        Gastas como quien gana ~{mxn(equivalent)}
                    </text>
                </g>
            </svg>
            {node}
        </div>
    );
}

/* ---------------------------------------------------------------- 2 · Balance */

export function BalanceChart({ months, income }: {
    months: { key: MonthKey; amount: number; count: number }[];
    income: number;
}) {
    const { box, bind, node } = useChartTip();
    const base = 170, top = 18;
    const max = Math.max(income, ...months.map((m) => m.amount)) * 1.12 || 1;
    const y = (v: number) => base - ((base - top) * v) / max;
    const bw = 58, gap = (560 - bw * months.length) / Math.max(1, months.length - 1);
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 200" className="w-full overflow-visible" role="img" aria-label="Gasto por mes contra tu ingreso">
                {months.map((m, i) => {
                    const x = 20 + i * (bw + gap);
                    const under = Math.min(m.amount, income), over = Math.max(0, m.amount - income);
                    const tip = m.count === 0
                        ? `${monthShort(m.key)} · sin cargos en el registro`
                        : `${monthShort(m.key)} · gasto ${mxn(m.amount)} · ${over > 0 ? `${mxn(over)} arriba de tu ingreso` : `${mxn(income - m.amount)} por debajo`}`;
                    return (
                        <g key={m.key} {...bind(tip)}>
                            <rect x={x} y={top} width={bw} height={base - top} fill="transparent" />
                            <rect className="lx-grow" style={{ transitionDelay: `${i * 80}ms` }} x={x} y={y(under)} width={bw} height={base - y(under)} rx={2} fill={colors.graphite} />
                            {over > 0 && (
                                <rect className="lx-fade" style={{ transitionDelay: `${800 + i * 90}ms` }} x={x} y={y(m.amount)} width={bw} height={y(under) - y(m.amount)} rx={2} fill={colors.signal} />
                            )}
                            {m.count > 0 && (
                                <text className="lx-fade" style={{ ...TEXT, fill: over > 0 ? colors.edge : colors.graphite, transitionDelay: `${600 + i * 80}ms` }} x={x + bw / 2} y={y(m.amount) - 6} textAnchor="middle">
                                    {Math.round(m.amount).toLocaleString("en-US")}
                                </text>
                            )}
                            <text x={x + bw / 2} y={base + 18} textAnchor="middle" style={TEXT}>{monthShort(m.key)}</text>
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

export function DiasChart({ byDay, shares }: { byDay: number[]; shares: [number, number, number] }) {
    const { box, bind, node } = useChartTip();
    const max = Math.max(...byDay) || 1;
    // Four steps of the stone ramp by how heavy the day was; the day with the
    // most spend takes the Signal edge.
    const step = (v: number) => (v === 0 ? colors.fog : v < max * 0.2 ? colors.mist : v < max * 0.45 ? colors.ash : colors.soot);
    const peak = byDay.indexOf(max);
    return (
        <div ref={box} className="relative">
            <div className="grid grid-cols-11 gap-1.5">
                {byDay.map((v, i) => (
                    <div
                        key={i}
                        {...bind(`Día ${i + 1} · ${mxn(v)}`)}
                        className={cn(
                            "lx-fade flex h-7 items-center justify-center rounded-[3px] text-label tabular",
                            i === peak && "ring-2 ring-signal ring-offset-1"
                        )}
                        style={{
                            background: step(v),
                            color: v >= max * 0.45 ? colors.paper : colors.graphite,
                            transitionDelay: `${i * 25}ms`,
                        }}
                    >
                        {i + 1}
                    </div>
                ))}
            </div>
            <div className="mt-3 flex flex-wrap justify-between gap-2 text-label text-graphite tabular">
                <span>Días 1–10 · {Math.round(shares[0] * 100)}%</span>
                <span>11–20 · {Math.round(shares[1] * 100)}%</span>
                <span>21–31 · {Math.round(shares[2] * 100)}%</span>
            </div>
            {node}
        </div>
    );
}

/* -------------------------------------------------------- 4 · Fin de semana */

const WEEKDAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];

export function SemanaChart({ byWeekday, share }: { byWeekday: { amount: number; count: number }[]; share: number }) {
    const { box, bind, node } = useChartTip();
    const max = Math.max(...byWeekday.map((d) => d.amount)) || 1;
    return (
        <div ref={box} className="relative">
            <div className="flex h-3 overflow-hidden rounded-full bg-mist">
                <div className="lx-growx h-full bg-signal" style={{ width: `${share * 100}%` }} />
            </div>
            <div className="mt-2 flex justify-between text-label tabular">
                <span className="text-edge">Fin de semana · {Math.round(share * 100)}%</span>
                <span className="text-graphite">Entre semana · {Math.round((1 - share) * 100)}%</span>
            </div>
            <svg viewBox="0 0 600 110" className="mt-4 w-full overflow-visible" role="img" aria-label="Gasto por día de la semana">
                {byWeekday.map((d, i) => {
                    const bw = 60, x = 10 + i * ((580 - bw) / 6), h = (80 * d.amount) / max, we = i >= 5;
                    return (
                        <g key={i} {...bind(`${WEEKDAYS[i]} · ${mxn(d.amount)} · ${d.count} cargos`)}>
                            <rect x={x} y={0} width={bw} height={84} fill="transparent" />
                            <rect className="lx-grow" style={{ transitionDelay: `${300 + i * 60}ms` }} x={x} y={84 - h} width={bw} height={h} rx={2} fill={we ? colors.signal : colors.ash} />
                            <text x={x + bw / 2} y={102} textAnchor="middle" style={{ ...TEXT, fill: we ? colors.edge : colors.graphite }}>{WEEKDAYS[i]}</text>
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

export function NecesidadChart({ tiers }: { tiers: TierSlice[] }) {
    const { box, bind, node } = useChartTip();
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
                        fill={TIER_FILL[tier]}
                        // The others step back instead of the picked one
                        // growing a border: the segment keeps its size, and
                        // the eye lands on the one still at full strength.
                        opacity={open && open !== tier ? 0.35 : 1}
                        onClick={() => toggle(tier)}
                        {...bind(`${TIER_LABELS[tier]} · ${mxn(t.amount)} · ${Math.round(t.share * 100)}%`)}
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
                        stroke={colors.signal}
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
                                <svg width="10" height="10" aria-hidden className="shrink-0"><rect width="10" height="10" rx="2" fill={tier === "sin" ? colors.mist : TIER_FILL[tier]} /></svg>
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
    const { box, bind, node } = useChartTip();
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
                            <span className={cn("tabular", on ? "text-edge" : "text-graphite")}>{hours} h</span>
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

export function SegundaChart({ months }: { months: { key: MonthKey; segunda: number }[] }) {
    const { box, bind, node } = useChartTip();
    const base = 130, top = 16;
    const max = Math.max(...months.map((m) => m.segunda)) * 1.15 || 1;
    const step = 560 / Math.max(1, months.length - 1);
    const pts = months.map((m, i) => [20 + i * step, base - ((base - top) * m.segunda) / max] as const);
    const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
    const peak = months.reduce((b, m, i) => (m.segunda > months[b]!.segunda ? i : b), 0);
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 176" className="w-full overflow-visible" role="img" aria-label="Gasto de segunda necesidad por mes">
                {[0.33, 0.66].map((f) => (
                    <line key={f} x1={10} x2={590} y1={base - (base - top) * f} y2={base - (base - top) * f} stroke={colors.mist} strokeDasharray="3 4" />
                ))}
                <path d={`${d} L${pts[pts.length - 1]![0]} ${base} L${pts[0]![0]} ${base} Z`} className="lx-fade" style={{ transitionDelay: "900ms" }} fill={colors.wash} opacity={0.45} />
                <path d={d} pathLength={1} className="lx-draw" fill="none" stroke={colors.signal} strokeWidth={2.5} strokeDasharray="1" strokeDashoffset={0} />
                {months.map((m, i) => (
                    <g key={m.key} {...bind(`${monthShort(m.key)} · ${mxn(m.segunda)} de segunda necesidad`)}>
                        <circle className="lx-fade" style={{ transitionDelay: `${200 + i * 180}ms` }} cx={pts[i]![0]} cy={pts[i]![1]} r={5} fill={colors.paper} stroke={colors.signal} strokeWidth={2} />
                        <text x={pts[i]![0]} y={base + 20} textAnchor="middle" style={TEXT}>{monthShort(m.key)}</text>
                        <text x={pts[i]![0]} y={base + 36} textAnchor="middle" style={{ ...TEXT, fill: i === peak ? colors.ink : colors.ash }}>{k(m.segunda)}</text>
                    </g>
                ))}
            </svg>
            {node}
        </div>
    );
}
