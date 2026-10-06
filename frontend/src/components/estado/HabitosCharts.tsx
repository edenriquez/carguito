"use client";

import { chart, colors } from "@/design/tokens";
import { cn } from "@/lib/cn";
import { mxn } from "@/lib/format";
import { DECILE_LABELS } from "@/lib/enigh";
import type {
    AmountBucket,
    CommittedReading,
    DaysReading,
    EstadoMonth,
    HabitMonth,
    MerchantSlice,
    PaydayReading,
} from "@/lib/lecturaEstado";
import { fromIso } from "@/lib/porMes";
import { NEGATIVE_HATCH, TEXT, k, monthAxis, monthShort, type PartialMonth } from "./EstadoCharts";
import { useChartTip } from "./useChartTip";

/*
 * The second batch of Lectura charts: where the money goes and when, and
 * three readings against the income. Same rules as the first batch — one
 * claim per chart, the thing the claim is about in Signal, the stone ramp
 * for everything else, `.lx-*` for the first-sight animation.
 */

export const pct = (v: number) => `${Math.round(v * 100)}%`;
const DAY = new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short" });
export const dayShort = (iso: string) => DAY.format(fromIso(iso)).replace(".", "");

/* ---------------------------------------------------------- Concentración */

export function ConcentracionChart({ merchants, highlight }: { merchants: MerchantSlice[]; highlight: number }) {
    const { box, bind, node, v2 } = useChartTip();
    const rows = merchants.slice(0, 6);
    const rest = merchants.slice(6);
    const max = rows[0]?.share || 1;
    return (
        <div ref={box} className="relative space-y-2.5">
            {rows.map((m, i) => {
                const on = i < highlight;
                return (
                    <div key={m.key} {...bind(`${m.name} · ${mxn(m.amount)} · ${m.count} ${m.count === 1 ? "cargo" : "cargos"}`)}>
                        <div className="flex justify-between gap-3 text-body-sm">
                            <span className={cn("min-w-0 truncate", on ? "text-ink" : "text-graphite")}>{m.name}</span>
                            <span className={cn("shrink-0 tabular", on ? (v2 ? "text-signalDeep" : "text-edge") : "text-graphite")}>{pct(m.share)}</span>
                        </div>
                        <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-fog">
                            <div
                                className="lx-growx h-full rounded-full"
                                style={{ width: `${(m.share / max) * 100}%`, background: on ? colors.signal : colors.graphite, transitionDelay: `${i * 90}ms` }}
                            />
                        </div>
                    </div>
                );
            })}
            {rest.length > 0 && (
                <p className="pt-1 text-label tabular text-graphite">
                    Otros {rest.length} lugares · {pct(rest.reduce((s, m) => s + m.share, 0))}
                </p>
            )}
            {node}
        </div>
    );
}

/* ---------------------------------------------------------------- Hormiga */

const BUCKET_FILL = [colors.signal, colors.soot, "#57534e", colors.graphite, colors.ash];
// v2: steps of the ramp far enough apart to tell side by side; the last,
// biggest-ticket bucket takes the lightest stone.
const BUCKET_FILL_V2 = [colors.signal, chart.neutral[0], chart.neutral[2], chart.neutral[4], colors.muted];

export function HormigaChart({ buckets }: { buckets: AmountBucket[] }) {
    const { box, bind, node, v2 } = useChartTip();
    const fills = v2 ? BUCKET_FILL_V2 : BUCKET_FILL;
    const counts = buckets.reduce((s, b) => s + b.count, 0) || 1;
    const amounts = buckets.reduce((s, b) => s + b.amount, 0) || 1;
    const rows = [
        { label: "De tus cargos", of: (b: AmountBucket) => b.count / counts },
        { label: "De tu dinero", of: (b: AmountBucket) => b.amount / amounts },
    ];
    return (
        <div ref={box} className="relative space-y-4">
            {rows.map((row, r) => (
                <div key={row.label}>
                    <div className="mb-1.5 flex justify-between text-label">
                        <span className="text-graphite">{row.label}</span>
                        <span className={cn("tabular", v2 ? "text-signalDeep" : "text-edge")}>{pct(row.of(buckets[0]!))} son {buckets[0]!.label}</span>
                    </div>
                    <div className="flex h-4 gap-px overflow-hidden rounded-[3px]">
                        {buckets.map((b, i) => {
                            const w = row.of(b);
                            if (w <= 0) return null;
                            return (
                                <div
                                    key={b.label}
                                    {...bind(`${b.label} · ${b.count} ${b.count === 1 ? "cargo" : "cargos"} · ${mxn(b.amount)}`)}
                                    className="lx-growx h-full"
                                    style={{ width: `${w * 100}%`, background: fills[i], transitionDelay: `${r * 200 + i * 80}ms` }}
                                />
                            );
                        })}
                    </div>
                </div>
            ))}
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-label text-graphite">
                {buckets.map((b, i) => (
                    <li key={b.label} className="flex items-center gap-1.5">
                        <svg width="10" height="10" aria-hidden><rect width="10" height="10" rx="2" fill={fills[i]} /></svg>
                        {b.label}
                    </li>
                ))}
            </ul>
            {node}
        </div>
    );
}

/* --------------------------------------------------------------- Efectivo */

export function EfectivoChart({ months, share, partial = null }: { months: EstadoMonth[]; share: number; partial?: PartialMonth }) {
    const { box, bind, node, v2, accent } = useChartTip();
    const base = 120, top = 18;
    const max = Math.max(...months.map((m) => m.amount)) * 1.1 || 1;
    const y = (v: number) => base - ((base - top) * v) / max;
    const bw = 58, gap = (560 - bw * months.length) / Math.max(1, months.length - 1);
    return (
        <div ref={box} className="relative">
            <div className="flex h-3 overflow-hidden rounded-full bg-mist">
                <div className="lx-growx h-full bg-signal" style={{ width: `${share * 100}%` }} />
            </div>
            <div className="mt-2 flex justify-between text-label tabular">
                <span className={v2 ? "text-signalDeep" : "text-edge"}>En efectivo · {pct(share)}</span>
                <span className="text-graphite">Con tarjeta o transferencia · {pct(1 - share)}</span>
            </div>
            <svg viewBox="0 0 600 150" className="mt-4 w-full overflow-visible" role="img" aria-label="Retiros de efectivo por mes">
                {months.map((m, i) => {
                    const x = 20 + i * (bw + gap);
                    const tip = m.count === 0
                        ? `${monthShort(m.key)} · sin cargos en el registro`
                        : `${monthShort(m.key)} · ${mxn(m.cash)} en cajero de ${mxn(m.amount)}`;
                    return (
                        <g key={m.key} {...bind(tip)}>
                            {/* v2: the month's total in Ash — Mist is a hairline
                                and the bar behind the cash all but vanished —
                                so the cash figure moves above it, off the grey. */}
                            <g opacity={v2 && partial?.key === m.key ? 0.45 : 1}>
                                <rect className="lx-grow" style={{ transitionDelay: `${i * 80}ms` }} x={x} y={y(m.amount)} width={bw} height={base - y(m.amount)} rx={2} fill={v2 ? colors.ash : colors.mist} />
                                {m.cash > 0 && (
                                    <rect className="lx-grow" style={{ transitionDelay: `${300 + i * 80}ms` }} x={x} y={y(m.cash)} width={bw} height={base - y(m.cash)} rx={2} fill={colors.signal} />
                                )}
                            </g>
                            {m.cash > 0 && (
                                <text className="lx-fade" style={{ ...TEXT, fill: accent, transitionDelay: `${700 + i * 80}ms` }} x={x + bw / 2} y={y(v2 ? m.amount : m.cash) - 5} textAnchor="middle">
                                    {k(m.cash)}
                                </text>
                            )}
                            <text x={x + bw / 2} y={base + 18} textAnchor="middle" style={TEXT}>{v2 ? monthAxis(m.key, partial) : monthShort(m.key)}</text>
                        </g>
                    );
                })}
            </svg>
            {node}
        </div>
    );
}

/* ------------------------------------------------------------- Calendario */

export function CalendarioChart({ days }: { days: DaysReading }) {
    const { box, bind, node, v2 } = useChartTip();
    const max = Math.max(1, ...days.rows.flatMap((r) => r.cells.map((c) => c ?? 0)));
    // v2: the steps cut at the median and the 80th percentile of the days
    // with gasto, so one huge day does not push every other day into Mist.
    const spent = days.rows.flatMap((r) => r.cells.filter((c): c is number => !!c && c > 0)).sort((a, b) => a - b);
    const q = (p: number) => spent[Math.min(spent.length - 1, Math.floor(p * spent.length))] ?? 0;
    const p50 = q(0.5), p80 = q(0.8);
    const gapDays = new Set<string>();
    if (days.gap) {
        for (let d = fromIso(days.gap.from); ; d.setDate(d.getDate() + 1)) {
            const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
            gapDays.add(iso);
            if (iso >= days.gap.to) break;
        }
    }
    const step = v2
        ? (v: number) => (v < p50 ? colors.mist : v < p80 ? colors.ash : colors.soot)
        : (v: number) => (v < max * 0.2 ? colors.mist : v < max * 0.45 ? colors.ash : colors.soot);
    const per30 = days.total > 0 ? Math.round((days.active / days.total) * 30) : 0;
    return (
        <div
            ref={box}
            className="relative space-y-1"
            {...(v2 && { role: "img", "aria-label": `Gastas en ${per30} de cada 30 días${days.gap ? `; tu racha más larga sin gastar fue de ${days.gap.days} ${days.gap.days === 1 ? "día" : "días"}` : ""}` })}
        >
            {days.rows.map((row, r) => {
                const [y, m] = row.key.split("-").map(Number);
                return (
                    <div key={row.key} className="grid items-center gap-px" style={{ gridTemplateColumns: "2.25rem repeat(31, minmax(0, 1fr))" }}>
                        <span className="pr-1 text-label text-graphite">{monthShort(row.key)}</span>
                        {Array.from({ length: 31 }, (_, i) => {
                            const v = row.cells[i];
                            const iso = `${y}-${String(m).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
                            if (v === undefined || v === null) return <span key={i} aria-hidden className="h-4" />;
                            const inGap = gapDays.has(iso);
                            return (
                                <span
                                    key={i}
                                    {...bind(v > 0 ? `${dayShort(iso)} · ${mxn(v)}` : `${dayShort(iso)} · sin gasto`, false)}
                                    className="lx-fade h-4 rounded-[2px]"
                                    style={{
                                        background: v > 0 ? step(v) : inGap ? colors.wash : colors.fog,
                                        // v2: a day without gasto is outlined, so it
                                        // does not read as the lightest step (Mist).
                                        boxShadow: v2 && v === 0 && !inGap ? `inset 0 0 0 1px ${colors.muted}` : undefined,
                                        transitionDelay: `${r * 120 + i * 12}ms`,
                                    }}
                                />
                            );
                        })}
                    </div>
                );
            })}
            {v2 ? (
                <div className="flex flex-wrap gap-x-4 gap-y-1 pt-2 text-label tabular text-graphite">
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.fog, boxShadow: `inset 0 0 0 1px ${colors.muted}` }} />Sin gasto</span>
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.wash }} />Tu racha más larga</span>
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.mist }} />Menos de {mxn(p50)}</span>
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.ash }} />{mxn(p50)} a {mxn(p80)}</span>
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.soot }} />{mxn(p80)} o más</span>
                </div>
            ) : (
                <div className="flex flex-wrap gap-x-4 gap-y-1 pt-2 text-label text-graphite">
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.fog }} />Sin gasto</span>
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.wash }} />Tu racha más larga</span>
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.soot }} />Día pesado</span>
                </div>
            )}
            {node}
        </div>
    );
}

/* --------------------------------------------------------------- Habitual */

export function HabitualChart({ months }: { months: HabitMonth[] }) {
    const { box, bind, node, accent } = useChartTip();
    const base = 150, top = 22;
    const max = Math.max(...months.map((m) => m.known + m.fresh)) * 1.12 || 1;
    const y = (v: number) => base - ((base - top) * v) / max;
    const bw = 58, gap = (560 - bw * months.length) / Math.max(1, months.length - 1);
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 180" className="w-full overflow-visible" role="img" aria-label="Gasto en lugares conocidos y nuevos, por mes">
                <defs>
                    <pattern id="lx-hatch-base" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                        <rect width="6" height="6" fill={colors.fog} />
                        <line x1="0" y1="0" x2="0" y2="6" stroke={colors.muted} strokeWidth="2" />
                    </pattern>
                </defs>
                {months.map((m, i) => {
                    const x = 20 + i * (bw + gap);
                    const total = m.known + m.fresh;
                    const tip = m.base
                        ? `${monthShort(m.key)} · mes base: desde aquí se cuenta qué lugar es nuevo`
                        : `${monthShort(m.key)} · ${mxn(m.fresh)} en ${m.freshMerchants} ${m.freshMerchants === 1 ? "lugar nuevo" : "lugares nuevos"} · ${mxn(m.known)} en conocidos`;
                    return (
                        <g key={m.key} {...bind(tip)}>
                            <rect x={x} y={top} width={bw} height={base - top} fill="transparent" />
                            <rect className="lx-grow" style={{ transitionDelay: `${i * 80}ms` }} x={x} y={y(m.known)} width={bw} height={base - y(m.known)} rx={2} fill={m.base ? "url(#lx-hatch-base)" : colors.graphite} />
                            {m.fresh > 0 && (
                                <rect className="lx-fade" style={{ transitionDelay: `${700 + i * 90}ms` }} x={x} y={y(total)} width={bw} height={y(m.known) - y(total) - 2} rx={2} fill={colors.signal} />
                            )}
                            {m.fresh > 0 && (
                                <text className="lx-fade" style={{ ...TEXT, fill: accent, transitionDelay: `${900 + i * 80}ms` }} x={x + bw / 2} y={y(total) - 6} textAnchor="middle">
                                    {k(m.fresh)}
                                </text>
                            )}
                            <text x={x + bw / 2} y={base + 18} textAnchor="middle" style={{ ...TEXT, fill: m.base ? colors.ash : colors.graphite }}>
                                {m.base ? `${monthShort(m.key)} · base` : monthShort(m.key)}
                            </text>
                        </g>
                    );
                })}
            </svg>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-label text-graphite">
                <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.graphite }} />Lugares donde ya habías pagado</span>
                <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.signal }} />Lugares nuevos ese mes</span>
            </div>
            {node}
        </div>
    );
}

/* -------------------------------------------------------------- Tendencia */

export function TendenciaChart({ months, slope }: { months: EstadoMonth[]; slope: number | null }) {
    const { box, bind, node, v2, accent } = useChartTip();
    const base = 150, top = 22;
    const max = Math.max(...months.map((m) => m.amount)) * 1.15 || 1;
    const y = (v: number) => base - ((base - top) * v) / max;
    const bw = 58, gap = (560 - bw * months.length) / Math.max(1, months.length - 1);
    const cx = (i: number) => 20 + i * (bw + gap) + bw / 2;
    const n = months.length;
    const mean = months.reduce((s, m) => s + m.amount, 0) / (n || 1);
    const fit = slope === null ? null : (i: number) => mean + slope * (i - (n - 1) / 2);
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 180" className="w-full overflow-visible" role="img" aria-label="Gasto por mes y su tendencia">
                {months.map((m, i) => (
                    <g key={m.key} {...bind(`${monthShort(m.key)} · ${mxn(m.amount)}`)}>
                        <rect className="lx-grow" style={{ transitionDelay: `${i * 80}ms` }} x={cx(i) - bw / 2} y={y(m.amount)} width={bw} height={base - y(m.amount)} rx={2} fill={colors.mist} />
                        <text className="lx-fade" style={{ ...TEXT, transitionDelay: `${500 + i * 80}ms` }} x={cx(i)} y={y(m.amount) - 6} textAnchor="middle">{k(m.amount)}</text>
                        <text x={cx(i)} y={base + 18} textAnchor="middle" style={TEXT}>{monthShort(m.key)}</text>
                    </g>
                ))}
                {fit && n > 1 && (
                    <line
                        className="lx-draw"
                        pathLength={1}
                        strokeDasharray="1"
                        x1={cx(0)}
                        y1={y(Math.max(0, fit(0)))}
                        x2={cx(n - 1)}
                        y2={y(Math.max(0, fit(n - 1)))}
                        stroke={colors.signal}
                        strokeWidth={2.5}
                        strokeLinecap="round"
                    />
                )}
                {/* v2: the slope the title states, written where the line
                    ends — above the last bar's own figure. */}
                {v2 && fit && slope !== null && n > 1 && (
                    <text
                        className="lx-fade"
                        style={{ ...TEXT, fill: accent, fontWeight: 500, transitionDelay: "1200ms" }}
                        x={cx(n - 1) + bw / 2}
                        y={Math.min(y(Math.max(0, fit(n - 1))), y(months[n - 1]!.amount)) - 6}
                        dy="-1.2em"
                        textAnchor="end"
                    >
                        {slope >= 0 ? "+" : "−"}{mxn(Math.abs(slope))} al mes
                    </text>
                )}
            </svg>
            {node}
        </div>
    );
}

/* --------------------------------------------------------------- Extremos */

export function ExtremosChart({ months, max, min, average }: {
    months: EstadoMonth[];
    max: EstadoMonth;
    min: EstadoMonth;
    average: number;
}) {
    const { box, bind, node, v2, accent } = useChartTip();
    const scale = max.amount * 1.08 || 1;
    const x = (v: number) => 20 + (v / scale) * 560;
    const mid = 60;
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 110" className="w-full overflow-visible" role="img" aria-label="Los meses del más barato al más caro">
                <line x1={20} x2={580} y1={mid} y2={mid} stroke={colors.mist} strokeWidth={2} />
                <line className="lx-fade" x1={x(average)} x2={x(average)} y1={mid - 22} y2={mid + 22} stroke={colors.ash} strokeDasharray="3 3" />
                {/* v2: one row below the cheapest month's label, in em, so the two
                    never meet whatever the text size. */}
                <text className="lx-fade" x={x(average)} y={v2 ? mid + 10 : mid + 38} dy={v2 ? "2.4em" : undefined} textAnchor="middle" style={{ ...TEXT, fill: v2 ? colors.graphite : colors.ash }}>promedio {k(average)}</text>
                <rect className="lx-growx lx-fade" style={{ transitionDelay: "300ms" }} x={x(min.amount)} y={mid - 4} width={Math.max(0, x(max.amount) - x(min.amount))} height={8} rx={4} fill={colors.wash} />
                {months.map((m, i) => {
                    const on = m.key === max.key, low = m.key === min.key;
                    const above = i % 2 === 0;
                    return (
                        <g key={m.key} {...bind(`${monthShort(m.key)} · ${mxn(m.amount)}`)}>
                            <circle className="lx-fade" style={{ transitionDelay: `${400 + i * 90}ms` }} cx={x(m.amount)} cy={mid} r={on || low ? 7 : 5} fill={on ? colors.signal : low ? colors.paper : colors.graphite} stroke={low ? colors.soot : "none"} strokeWidth={2} />
                            {/* v2 names only the two ends, max above and min below, and
                                leaves the months between to the tooltip: the
                                alternating labels ran into each other. */}
                            {!v2 ? (
                                <text className="lx-fade" style={{ ...TEXT, fill: on ? colors.edge : low ? colors.ink : colors.graphite, fontWeight: on || low ? 500 : 400, transitionDelay: `${500 + i * 90}ms` }} x={x(m.amount)} y={above ? mid - 16 : mid + 24} textAnchor="middle">
                                    {monthShort(m.key)}
                                </text>
                            ) : (on || low) && (
                                <text className="lx-fade" style={{ ...TEXT, fill: on ? accent : colors.ink, fontWeight: 500, transitionDelay: `${500 + i * 90}ms` }} x={x(m.amount)} y={on ? mid - 16 : mid + 10} dy={on ? 0 : "1em"} textAnchor="middle">
                                    {monthShort(m.key)} {k(m.amount)}
                                </text>
                            )}
                        </g>
                    );
                })}
            </svg>
            {node}
        </div>
    );
}

/* --------------------------------------------------------------- Día cero */

export function DiaCeroChart({ payday, income }: { payday: PaydayReading; income: number }) {
    const { box, bind, node, v2, accent } = useChartTip();
    const base = 160, top = 20;
    const max = Math.max(income, payday.curve[30]!) * 1.12 || 1;
    const y = (v: number) => base - ((base - top) * v) / max;
    const x = (day: number) => 20 + ((day - 1) / 30) * 560;
    const pts = payday.curve.map((v, i) => [x(i + 1), y(v)] as const);
    const d = pts.map(([px, py], i) => `${i ? "L" : "M"}${px} ${py}`).join(" ");
    const cross = payday.crossDay;
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 196" className="w-full overflow-visible" role="img" aria-label="Lo gastado en el mes, acumulado por día, contra tu ingreso">
                <path d={`${d} L${x(31)} ${base} L${x(1)} ${base} Z`} className="lx-fade" style={{ transitionDelay: "900ms" }} fill={colors.wash} opacity={0.45} />
                <line className="lx-fade" style={{ transitionDelay: "300ms" }} x1={10} x2={590} y1={y(income)} y2={y(income)} stroke={colors.ash} strokeDasharray="4 4" />
                <text className="lx-fade" style={{ ...TEXT, transitionDelay: "300ms" }} x={590} y={y(income) - 6} textAnchor="end">Ingreso {mxn(income)}</text>
                <path d={d} pathLength={1} className="lx-draw" fill="none" stroke={colors.signal} strokeWidth={2.5} strokeDasharray="1" />
                {cross !== null && (
                    <g className="lx-fade" style={{ transitionDelay: "1100ms" }}>
                        <line x1={x(cross)} x2={x(cross)} y1={y(income)} y2={base} stroke={colors.signal} />
                        <circle cx={x(cross)} cy={y(income)} r={6} fill={colors.signal} />
                        <text x={x(cross)} y={y(income) - 14} textAnchor="middle" style={{ ...TEXT, fill: accent, fontWeight: 500 }}>Día {cross}</text>
                    </g>
                )}
                {/* v2: the curve says what it is, not only the tooltip: it is
                    the average month, not any one month. Under its end, on the
                    wash, clear of the income label above the line. */}
                {v2 && (
                    <text className="lx-fade" style={{ ...TEXT, fill: accent, transitionDelay: "1100ms" }} x={x(31)} y={pts[30]![1]} dy="1.3em" textAnchor="end">
                        mes promedio
                    </text>
                )}
                {[1, 5, 10, 15, 20, 25, 30].map((day) => (
                    <text key={day} x={x(day)} y={base + 18} textAnchor="middle" style={TEXT}>{day}</text>
                ))}
                {payday.curve.map((v, i) => (
                    <rect key={i} x={x(i + 1) - 560 / 60} y={top} width={560 / 30} height={base - top} fill="transparent" {...bind(`Día ${i + 1} · ${mxn(v)} acumulados en el mes promedio`)} />
                ))}
            </svg>
            {node}
        </div>
    );
}

/* ----------------------------------------------------------- Comprometido */

export function ComprometidoChart({ committed, income }: { committed: CommittedReading; income: number }) {
    const { box, bind, node, v2 } = useChartTip();
    // v2: the shortfall is not "you" — a Negative hatch (never a solid red
    // fill), with its figure in the legend.
    const shortFill = v2 ? NEGATIVE_HATCH : { background: colors.signal };
    const spent = committed.fijos + committed.variable;
    const scale = Math.max(income, spent) || 1;
    const w = (v: number) => (v / scale) * 100;
    const short = Math.max(0, spent - income);
    const parts = [
        { label: "Fijos", amount: committed.fijos, fill: colors.soot },
        { label: "Variable", amount: committed.variable, fill: colors.graphite },
        { label: "Margen", amount: Math.max(0, committed.margin), fill: colors.wash },
    ].filter((p) => p.amount > 0);
    return (
        <div ref={box} className="relative">
            <div className="relative">
                <div className="flex h-5 gap-px overflow-hidden rounded-[3px] bg-fog">
                    {parts.map((p, i) => (
                        <div key={p.label} {...bind(`${p.label} · ${mxn(p.amount)} · ${pct(p.amount / income)} de tu ingreso`)} className="lx-growx h-full" style={{ width: `${w(p.amount)}%`, background: p.fill, transitionDelay: `${i * 160}ms` }} />
                    ))}
                    {short > 0 && (
                        <div {...bind(`Faltan ${mxn(short)} al mes`)} className="lx-fade h-full" style={{ width: `${w(short)}%`, ...shortFill, transitionDelay: "500ms" }} />
                    )}
                </div>
                {short > 0 && (
                    <span aria-hidden className="absolute -top-1 h-7 w-px bg-ink" style={{ left: `${w(income)}%` }} />
                )}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-label tabular text-graphite">
                <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.soot }} />Fijos {mxn(committed.fijos)}</span>
                <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.graphite }} />Variable {mxn(committed.variable)}</span>
                {committed.margin >= 0 ? (
                    <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: colors.wash }} />Margen {mxn(committed.margin)}</span>
                ) : (
                    <span className={cn("flex items-center gap-1.5", v2 && "text-negative")}><i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={shortFill} />Faltan {mxn(-committed.margin)}</span>
                )}
            </div>
            <ul className="mt-4 divide-y divide-mist">
                {committed.rows.slice(0, 5).map((r, i) => (
                    <li key={r.key} className="lx-fade flex items-baseline justify-between gap-3 py-1.5 text-label" style={{ transitionDelay: `${400 + i * 80}ms` }}>
                        <span className="min-w-0 truncate text-ink">{r.label}</span>
                        <span className="shrink-0 tabular text-graphite">{mxn(r.monthly_equivalent)}/mes</span>
                    </li>
                ))}
                {committed.rows.length > 5 && (
                    <li className="py-1.5 text-label text-graphite">y {committed.rows.length - 5} más</li>
                )}
            </ul>
            {node}
        </div>
    );
}

/* ------------------------------------------------------ Decil contra decil */

export function DecilRatioChart({ ratios, decile, factor }: { ratios: number[]; decile: number; factor: number }) {
    const { box, bind, node, v2, accent } = useChartTip();
    const base = 130, top = 20;
    const max = Math.max(1.1, factor, ...ratios) * 1.12;
    const y = (v: number) => base - ((base - top) * v) / max;
    const bw = 44, gap = (560 - bw * 10) / 9;
    return (
        <div ref={box} className="relative">
            <svg viewBox="0 0 600 160" className="w-full overflow-visible" role="img" aria-label="Gasto por cada peso de ingreso, por decil">
                <line x1={10} x2={590} y1={y(1)} y2={y(1)} stroke={colors.mist} strokeDasharray="3 4" />
                <text x={10} y={y(1) - 5} style={{ ...TEXT, fill: colors.ash }}>$1.00 · todo lo que entra</text>
                {ratios.map((r, i) => {
                    const x = 20 + i * (bw + gap);
                    const on = i === decile;
                    return (
                        <g key={i} {...bind(`Decil ${DECILE_LABELS[i]} · gasta $${r.toFixed(2)} de cada peso`)}>
                            <rect x={x} y={top} width={bw} height={base - top} fill="transparent" />
                            <rect className="lx-grow" style={{ transitionDelay: `${i * 60}ms` }} x={x} y={y(r)} width={bw} height={base - y(r)} rx={2} fill={on ? colors.signal : colors.mist} />
                            <text x={x + bw / 2} y={base + 16} textAnchor="middle" style={{ ...TEXT, fill: on ? accent : colors.graphite, fontWeight: on ? 500 : 400 }}>{DECILE_LABELS[i]}</text>
                            {/* v2: this decile is by income — the Decil chart
                                above it marks the one by spend. */}
                            {v2 && on && <text x={x + bw / 2} y={base + 16} dy="1.3em" textAnchor="middle" style={{ ...TEXT, fill: accent }}>tu decil por ingreso</text>}
                            <text className="lx-fade" style={{ ...TEXT, fill: on ? colors.ink : colors.ash, transitionDelay: `${400 + i * 60}ms` }} x={x + bw / 2} y={y(r) - 5} textAnchor="middle">{r.toFixed(2)}</text>
                        </g>
                    );
                })}
                <line className="lx-fade" style={{ transitionDelay: "900ms" }} x1={10} x2={590} y1={y(factor)} y2={y(factor)} stroke={v2 ? colors.signal : colors.soot} strokeWidth={1.5} />
                <text className="lx-fade" style={{ ...TEXT, fill: v2 ? accent : colors.ink, fontWeight: 500, transitionDelay: "900ms" }} x={590} y={y(factor) - 6} textAnchor="end">Tú ${factor.toFixed(2)}</text>
            </svg>
            {node}
        </div>
    );
}
