"use client";

import { colors } from "@/design/tokens";
import { cn } from "@/lib/cn";
import { mxn, mxn2 } from "@/lib/format";
import { RUBRO_LABELS, type Rubro } from "@/lib/enighRubros";
import type { CanastaReading, InpcPoint, RubroRow } from "@/lib/lecturaPais";
import { rubroPesos } from "@/lib/lecturaPais";
import { TEXT, monthShort } from "./EstadoCharts";
import { pct } from "./HabitosCharts";
import { useChartTip } from "./useChartTip";

/*
 * The three charts that put the statement next to a published table. The
 * user's figure is Signal; the country's is the stone ramp, as everywhere
 * else on the face.
 */

/* ----------------------------------------------------------------- Rubros */

export function RubrosChart({ rows, decile, decileLabel, highlight }: {
    rows: RubroRow[];
    decile: number;
    decileLabel: string;
    highlight: Rubro | null;
}) {
    const { box, bind, node } = useChartTip();
    const max = Math.max(...rows.flatMap((r) => [r.share, r.decileShare])) || 1;
    return (
        <div ref={box} className="relative">
            <div className="mb-3 flex gap-4 text-label text-graphite">
                <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.signal }} />Tú</span>
                <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.graphite }} />Hogar del decil {decileLabel}</span>
            </div>
            {/* Two columns when the card has the row to itself: ranked top to
                bottom, then on to the second column. */}
            <div className="lg:columns-2 lg:gap-x-10">
                {rows.map((r, i) => {
                    const on = r.rubro === highlight;
                    return (
                        <div key={r.rubro} className="mb-2 break-inside-avoid" {...bind(`${RUBRO_LABELS[r.rubro]} · tú ${mxn(r.amount)} al mes · decil ${decileLabel} ${mxn(rubroPesos(r.rubro, decile))} al mes`)}>
                            <div className="flex items-baseline justify-between gap-3 text-label">
                                <span className={cn("min-w-0 truncate", on ? "font-medium text-ink" : "text-graphite")}>{RUBRO_LABELS[r.rubro]}</span>
                                <span className="shrink-0 tabular">
                                    <span className={on ? "text-edge" : "text-graphite"}>{pct(r.share)}</span>
                                    <span className="text-ash"> · {pct(r.decileShare)}</span>
                                </span>
                            </div>
                            <div className="mt-1 space-y-0.5">
                                <div className="h-1.5 overflow-hidden rounded-full bg-fog">
                                    <div className="lx-growx h-full rounded-full" style={{ width: `${(r.share / max) * 100}%`, background: colors.signal, transitionDelay: `${i * 60}ms` }} />
                                </div>
                                <div className="h-1.5 overflow-hidden rounded-full bg-fog">
                                    <div className="lx-growx h-full rounded-full" style={{ width: `${(r.decileShare / max) * 100}%`, background: colors.graphite, transitionDelay: `${i * 60 + 200}ms` }} />
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
            {node}
        </div>
    );
}

/* ---------------------------------------------------------------- Canasta */

function Persons({ value, label, tip, on }: { value: number; label: string; tip: string; on: boolean }) {
    const { box, bind, node } = useChartTip();
    const whole = Math.floor(value);
    const part = value - whole;
    const shown = Math.min(whole, 12);
    return (
        <div ref={box} className="relative" {...bind(tip)}>
            <div className="flex items-baseline justify-between text-body-sm">
                <span className={on ? "text-ink" : "text-graphite"}>{label}</span>
                <span className={cn("tabular", on ? "text-edge" : "text-graphite")}>{value.toFixed(1)} personas</span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1">
                {Array.from({ length: shown }, (_, i) => (
                    <span key={i} className="lx-fade h-5 w-5 rounded-[3px]" style={{ background: on ? colors.signal : colors.graphite, transitionDelay: `${i * 90}ms` }} />
                ))}
                {whole > shown && <span className="self-center text-label text-graphite">+{whole - shown}</span>}
                {part > 0.05 && (
                    <span className="lx-fade relative h-5 w-5 overflow-hidden rounded-[3px] bg-fog" style={{ transitionDelay: `${shown * 90}ms` }}>
                        <span className="absolute inset-y-0 left-0" style={{ width: `${part * 100}%`, background: on ? colors.signal : colors.graphite }} />
                    </span>
                )}
            </div>
            {node}
        </div>
    );
}

export function CanastaChart({ reading, average }: { reading: CanastaReading; average: number }) {
    return (
        <div className="space-y-4">
            <Persons
                on
                value={reading.foodPersons}
                label={`Tu comida de casa, ${mxn(reading.food)} al mes`}
                tip={`Canasta alimentaria urbana · ${mxn2(reading.line.alimentariaUrbana)} por persona al mes`}
            />
            <Persons
                on={false}
                value={reading.totalPersons}
                label={`Todo tu mes, ${mxn(average)}`}
                tip={`Canasta alimentaria + no alimentaria urbana · ${mxn2(reading.line.completaUrbana)} por persona al mes`}
            />
            <p className="text-label text-graphite">Cada cuadro es una persona a precio de la canasta urbana.</p>
        </div>
    );
}

/* ------------------------------------------------------------------- INPC */

export function InpcChart({ points, user }: {
    points: InpcPoint[];
    /** The user's own index at a month, on the same 100 base; null without tickets. */
    user: { key: string; value: number; label: string } | null;
}) {
    const { box, bind, node } = useChartTip();
    const base = 130, top = 20;
    const values = points.flatMap((p) => [p.general, p.alimentos]).concat(user ? [user.value] : []);
    const lo = Math.min(100, ...values), hi = Math.max(100, ...values);
    const pad = Math.max(1, (hi - lo) * 0.15);
    const y = (v: number) => base - ((base - top) * (v - (lo - pad))) / (hi + pad - (lo - pad));
    const step = 560 / Math.max(1, points.length - 1);
    const x = (i: number) => 20 + i * step;
    const path = (pick: (p: InpcPoint) => number) => points.map((p, i) => `${i ? "L" : "M"}${x(i)} ${y(pick(p))}`).join(" ");
    const ui = user ? points.findIndex((p) => p.key === user.key) : -1;
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 160" className="w-full overflow-visible" role="img" aria-label="Índice de precios, mes a mes, con base 100 en el primer mes">
                <line x1={10} x2={590} y1={y(100)} y2={y(100)} stroke={colors.mist} strokeDasharray="3 4" />
                <text x={10} y={y(100) - 5} style={{ ...TEXT, fill: colors.ash }}>100 · {points[0] ? monthShort(points[0].key) : ""}</text>
                <path d={path((p) => p.general)} pathLength={1} className="lx-draw" fill="none" stroke={colors.graphite} strokeWidth={2} strokeDasharray="1" />
                <path d={path((p) => p.alimentos)} pathLength={1} className="lx-draw" style={{ transitionDelay: "200ms" }} fill="none" stroke={colors.signal} strokeWidth={2.5} strokeDasharray="1" />
                {points.map((p, i) => (
                    <g key={p.key} {...bind(`${monthShort(p.key)} · alimentos ${p.alimentos.toFixed(1)} · general ${p.general.toFixed(1)}`)}>
                        <rect x={x(i) - step / 2} y={top - 10} width={step} height={base - top + 10} fill="transparent" />
                        <circle className="lx-fade" style={{ transitionDelay: `${300 + i * 100}ms` }} cx={x(i)} cy={y(p.alimentos)} r={4} fill={colors.paper} stroke={colors.signal} strokeWidth={2} />
                        <text x={x(i)} y={base + 18} textAnchor="middle" style={TEXT}>{monthShort(p.key)}</text>
                    </g>
                ))}
                {user && ui >= 0 && (
                    <g className="lx-fade" style={{ transitionDelay: "1000ms" }} {...bind(`${user.label} · ${user.value.toFixed(1)}`)}>
                        <circle cx={x(ui)} cy={y(user.value)} r={7} fill={colors.ink} />
                        <text x={x(ui)} y={y(user.value) - 14} textAnchor={ui === points.length - 1 ? "end" : "middle"} style={{ ...TEXT, fill: colors.ink, fontWeight: 500 }}>{user.label}</text>
                    </g>
                )}
            </svg>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-label text-graphite">
                <span className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-4" style={{ background: colors.signal }} />INPC alimentos, bebidas y tabaco</span>
                <span className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-4" style={{ background: colors.graphite }} />INPC general</span>
                {user && <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: colors.ink }} />Tus tickets</span>}
            </div>
            {node}
        </div>
    );
}
