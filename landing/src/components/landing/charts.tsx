import type { CSSProperties } from "react";
import { CreditCard } from "lucide-react";
import { chart, colors } from "@/design/tokens";
import { dark } from "@/design/dark";
import { cn } from "@/lib/cn";
import {
    INCOME,
    LECTURA,
    LO_QUE_ENTRA,
    LO_QUE_SE_VA,
    NO_CUADRA,
    PAGOS,
    POR_CATEGORIA,
    POR_MES,
    PRECIOS,
    k,
    monthShort,
    mxn,
    mxn2,
    pct,
} from "@/lib/data";
import { DECILE_LABELS, ENIGH_MONTHLY, ENIGH_YEAR, decileIndex, percentileOf } from "@/lib/pais";

/*
 * The dashboard's charts, redrawn for Night. Same shapes and the same rule as
 * Gráficas v2 (frontend/src/components/estado/*, movimientos/PorMesChart,
 * recurrentes/LoadTimelineChart, pronostico/ContrastChart): Signal is "tú" or
 * the thing the title is about, the country and the rest are stone, a
 * category wears its taxonomy color, a partial month is drawn apart and a
 * projection sits on its own band. Bars are HTML so their labels stay at
 * 10–12px on a phone; only lines are SVG, stretched under HTML labels.
 */

const INK = {
    you: colors.signal,
    youSoft: chart.signalTint[2]!,
    stone: "#6b645f",
    stoneHi: dark.colors.dust,
    bone: dark.colors.bone,
    band: "rgba(255, 255, 255, 0.045)",
} as const;

/** The fijos' stone ramp, biggest charge brightest: the dashboard's ramp turned for a dark ground. */
const RAMP = ["#e7e5e4", "#c9c4c0", "#aaa39e", "#8c8580", "#6f6863", "#57504b"];

const at = (v: number, max: number) => `${(v / max) * 100}%`;
/** Lines live in a stretched 100×100 box; this keeps their stroke in screen pixels. */
const LINE: CSSProperties = { vectorEffect: "non-scaling-stroke" };

/* ---------------------------------------------------------- Contra el país */

const DECIL_COLS = "grid grid-cols-[2.25rem_repeat(10,minmax(0,1fr))] gap-x-1 sm:gap-x-1.5";

/** ENIGH by decile: the bars are the survey, the dashed line is you, Signal is the decile your spend lands in. */
export function DecilChart() {
    const { decil, average } = LECTURA;
    const incomeD = decileIndex(percentileOf(INCOME, ENIGH_MONTHLY.ingreso));
    const max = Math.max(average, ...ENIGH_MONTHLY.gasto) * 1.1;
    return (
        <div>
            <p className="mb-3 text-label text-dust">Gasto al mes por hogar, por decil de ingreso · ENIGH {ENIGH_YEAR}</p>
            <div className={cn(DECIL_COLS, "relative h-40 sm:h-44")}>
                <span />
                {ENIGH_MONTHLY.gasto.map((g, i) => (
                    <div key={i} className="flex h-full flex-col items-center justify-end">
                        {i === incomeD && (
                            <span className="mb-1 whitespace-nowrap text-[10px] font-medium leading-none text-bone">Ingresas aquí</span>
                        )}
                        <div
                            className="w-full max-w-8 rounded-[2px]"
                            style={{ height: at(g, max), background: i === decil.index ? INK.you : INK.stone }}
                        />
                    </div>
                ))}
                <div className="pointer-events-none absolute right-0 border-t border-dashed border-signal" style={{ left: "2.25rem", bottom: at(average, max) }}>
                    <span className="absolute bottom-1 left-0 whitespace-nowrap text-label font-medium text-signal">
                        Tú gastas {mxn(average)}
                    </span>
                </div>
            </div>
            <div className={cn(DECIL_COLS, "mt-2 border-t border-lineStrong pt-2 text-center text-label tabular")}>
                <span className="text-left text-ash">Decil</span>
                {DECILE_LABELS.map((l, i) => (
                    <span key={l} className={i === decil.index ? "font-medium text-signal" : "text-dust"}>
                        {l}
                    </span>
                ))}
            </div>
            {/* The figures per decile need the width; on a phone the card's figures carry them. */}
            <div className={cn(DECIL_COLS, "hidden text-center text-[11px] leading-5 tabular sm:grid")}>
                <span className="text-left text-ash">Gasta</span>
                {ENIGH_MONTHLY.gasto.map((g, i) => (
                    <span key={i} className={i === decil.index ? "text-signal" : "text-dust"}>{k(g)}</span>
                ))}
                <span className="text-left text-ash">Gana</span>
                {ENIGH_MONTHLY.ingreso.map((g, i) => (
                    <span key={i} className="text-ash">{k(g)}</span>
                ))}
            </div>
            <p className="mt-2 flex items-center gap-1.5 text-label text-dust">
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-bone" />
                Tu ingreso de {mxn(INCOME)} cae en el decil {DECILE_LABELS[incomeD]}
            </p>
        </div>
    );
}

function Persons({ value, label, on }: { value: number; label: string; on: boolean }) {
    const fill = on ? INK.you : INK.youSoft;
    const whole = Math.floor(value);
    const part = value - whole;
    return (
        <div>
            <div className="flex items-baseline justify-between gap-3 text-body-sm">
                <span className={on ? "text-bone" : "text-dust"}>{label}</span>
                <span className={cn("shrink-0 tabular", on ? "text-signal" : "text-dust")}>{value.toFixed(1)} personas</span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1">
                {Array.from({ length: whole }, (_, i) => (
                    <span key={i} className="h-5 w-5 rounded-[3px]" style={{ background: fill }} />
                ))}
                {part > 0.05 && (
                    <span className="relative h-5 w-5 overflow-hidden rounded-[3px] bg-white/[0.06]">
                        <span className="absolute inset-y-0 left-0" style={{ width: `${part * 100}%`, background: fill }} />
                    </span>
                )}
            </div>
        </div>
    );
}

/** Canasta: how many people your money feeds at the published per-person price. */
export function CanastaChart() {
    const { canasta, average } = LECTURA;
    return (
        <div className="w-full space-y-4">
            <Persons on value={canasta.foodPersons} label={`Tu comida de casa, ${mxn(canasta.food)} al mes`} />
            <Persons on={false} value={canasta.totalPersons} label={`Todo tu mes, ${mxn(average)}`} />
            <p className="text-label text-dust">Cada cuadro es una persona a precio de la canasta urbana.</p>
        </div>
    );
}

/** INPC from the first month (=100): food in bone, general in stone, your tickets as the Signal point. */
export function InpcChart() {
    const { points, user } = LECTURA.inpc;
    const values = points.flatMap((p) => [p.general, p.alimentos]).concat(user.value);
    const lo = Math.min(100, ...values), hi = Math.max(100, ...values);
    const pad = Math.max(1, (hi - lo) * 0.15);
    const min = lo - pad, max = hi + pad;
    const y = (v: number) => ((max - v) / (max - min)) * 100;
    const x = (i: number) => (i / (points.length - 1)) * 100;
    const path = (pick: (p: (typeof points)[number]) => number) =>
        points.map((p, i) => `${i ? "L" : "M"}${x(i)} ${y(pick(p))}`).join(" ");
    const last = points[points.length - 1]!;
    return (
        <div className="w-full">
            <div className="relative mr-[32%] mt-6 h-36">
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
                    <line x1={0} x2={100} y1={y(100)} y2={y(100)} stroke={INK.stone} strokeDasharray="3 4" style={LINE} />
                    <path d={path((p) => p.general)} fill="none" stroke={INK.stoneHi} strokeWidth={2} style={LINE} />
                    <path d={path((p) => p.alimentos)} fill="none" stroke={INK.bone} strokeWidth={2.5} style={LINE} />
                </svg>
                <span className="absolute left-0 -translate-y-full pb-1 text-label text-ash" style={{ top: `${y(100)}%` }}>
                    100 · {monthShort(points[0]!.key)}
                </span>
                {points.map((p, i) => (
                    <span
                        key={p.key}
                        className="absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 bg-slate"
                        style={{ left: `${x(i)}%`, top: `${y(p.alimentos)}%`, borderColor: INK.bone }}
                    />
                ))}
                <span className="absolute left-full ml-3 -translate-y-1/2 whitespace-nowrap text-label text-dust" style={{ top: `${y(last.general)}%` }}>
                    General <span className="font-medium tabular">{last.general.toFixed(1)}</span>
                </span>
                <span className="absolute left-full ml-3 -translate-y-1/2 whitespace-nowrap text-label text-bone" style={{ top: `${y(last.alimentos)}%` }}>
                    Alimentos <span className="font-medium tabular">{last.alimentos.toFixed(1)}</span>
                </span>
                <span className="absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-signal" style={{ left: "100%", top: `${y(user.value)}%` }} />
                <span className="absolute right-0 -translate-y-full whitespace-nowrap pb-2.5 text-label font-medium text-signal" style={{ top: `${y(user.value)}%` }}>
                    {user.label}
                </span>
            </div>
            <div className="relative mr-[32%] mt-2 h-4 text-label text-dust">
                {points.map((p, i) => (
                    <span key={p.key} className="absolute -translate-x-1/2" style={{ left: `${x(i)}%` }}>
                        {monthShort(p.key)}
                    </span>
                ))}
            </div>
            <p className="mt-3 text-label text-dust">
                Alimentos es el INPC de alimentos, bebidas y tabaco. Eje recortado: empieza en {min.toFixed(1)}, no en 0.
            </p>
        </div>
    );
}

/* ------------------------------------------------------------ Con tu ingreso */

/** Día cero: the average month's running total against what comes in. */
export function DiaCeroChart() {
    const { curve, crossDay } = LECTURA.diaCero;
    const max = Math.max(INCOME, curve[30]!) * 1.12;
    const y = (v: number) => 100 - (v / max) * 100;
    const x = (day: number) => ((day - 1) / 30) * 100;
    const d = curve.map((v, i) => `${i ? "L" : "M"}${x(i + 1)} ${y(v)}`).join(" ");
    return (
        <div className="w-full">
            <div className="relative mt-6 h-36">
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
                    <path d={`${d} L100 100 L0 100 Z`} fill={INK.you} opacity={0.12} />
                    <line x1={0} x2={100} y1={y(INCOME)} y2={y(INCOME)} stroke={INK.stoneHi} strokeDasharray="4 4" style={LINE} />
                    <path d={d} fill="none" stroke={INK.you} strokeWidth={2.5} style={LINE} />
                    {crossDay && <line x1={x(crossDay)} x2={x(crossDay)} y1={y(INCOME)} y2={100} stroke={INK.you} style={LINE} />}
                </svg>
                <span className="absolute left-0 -translate-y-full pb-1 text-label text-dust" style={{ top: `${y(INCOME)}%` }}>
                    Ingreso {mxn(INCOME)}
                </span>
                {crossDay && (
                    <>
                        <span className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-signal" style={{ left: `${x(crossDay)}%`, top: `${y(INCOME)}%` }} />
                        <span className="absolute -translate-x-full -translate-y-full whitespace-nowrap pb-1.5 pr-2 text-label font-medium text-signal" style={{ left: `${x(crossDay)}%`, top: `${y(INCOME)}%` }}>
                            Día {crossDay}
                        </span>
                    </>
                )}
            </div>
            <div className="relative mt-2 h-4 text-label text-dust">
                {[1, 5, 10, 15, 20, 25, 30].map((day) => (
                    <span key={day} className="absolute -translate-x-1/2 tabular" style={{ left: `${x(day)}%` }}>
                        {day}
                    </span>
                ))}
            </div>
        </div>
    );
}

/* ------------------------------------------------------------ En el tiempo */

const STRETCHES = [
    { from: 1, to: 10 },
    { from: 11, to: 20 },
    { from: 21, to: 31 },
] as const;

/** One bar per day of the month, summed over the span; the stretch the title names in Signal. */
export function DiasChart() {
    const { byDay, shares } = LECTURA.dias;
    const max = Math.max(...byDay);
    const peak = byDay.indexOf(max);
    const late = shares[0] < 0.25;
    return (
        <div className="w-full">
            <div className="relative flex h-36 items-end gap-[2px] pt-5">
                {[10, 20].map((d) => (
                    <span key={d} className="absolute bottom-0 top-3 border-l border-dashed border-lineStrong" style={{ left: `${(d / 31) * 100}%` }} />
                ))}
                {byDay.map((v, i) => (
                    <div key={i} className="relative flex h-full flex-1 flex-col justify-end">
                        {i === peak && (
                            <span className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-label text-signal" style={{ bottom: `calc(${at(v, max)} + 4px)` }}>
                                {k(v)}
                            </span>
                        )}
                        <div className="rounded-[1.5px]" style={{ height: at(v, max), background: (late ? i >= 10 : i === peak) ? INK.you : INK.stone }} />
                    </div>
                ))}
            </div>
            <div className="relative mt-1 h-4 text-label text-ash tabular">
                {[1, 5, 10, 15, 20, 25, 31].map((d) => (
                    <span key={d} className="absolute -translate-x-1/2" style={{ left: `${((d - 0.5) / 31) * 100}%` }}>
                        {d}
                    </span>
                ))}
            </div>
            <div className="mt-2 grid grid-cols-[10fr_10fr_11fr] text-center text-label tabular">
                {STRETCHES.map((s, i) => (
                    <span key={s.from} className={late && i > 0 ? "font-medium text-signal" : "text-dust"}>
                        <span className="hidden sm:inline">Días </span>
                        {s.from}–{s.to} · {pct(shares[i]!)}
                    </span>
                ))}
            </div>
        </div>
    );
}

/* -------------------------------------------------------- Lo que no cuadra */

/** The attention rows as the Lectura lists them: dot, bank line, flag, reason, amount, and the two answers. */
export function NoCuadraList() {
    return (
        <ul className="w-full divide-y divide-line">
            {NO_CUADRA.map((r) => (
                <li key={r.description} className="flex items-start gap-3 py-2.5">
                    <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", r.warn ? "bg-signal" : "bg-ash")} />
                    <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-2 text-body-sm text-bone">
                            <span className="truncate">{r.description}</span>
                            <span className="shrink-0 rounded-tag border border-signal px-1.5 py-px text-caption font-medium uppercase text-bone">
                                {r.flag}
                            </span>
                        </p>
                        <p className="text-label text-dust">
                            {r.day} · {r.reason}
                        </p>
                    </div>
                    <span className="tabular text-body-sm text-bone">{mxn2(r.amount)}</span>
                    <span className="hidden shrink-0 gap-1 sm:flex">
                        <span className="rounded-control px-3 py-1 text-body-sm text-dust">Es mío</span>
                        <span className="rounded-control border border-lineStrong px-3 py-1 text-body-sm text-bone">Ver</span>
                    </span>
                </li>
            ))}
        </ul>
    );
}

/* ----------------------------------------------------------- Movimientos */

const monthAxis = (m: { key: string; partialDay?: number }) =>
    m.partialDay ? (
        <>
            {monthShort(m.key)}
            <span className="block sm:inline"><span className="hidden sm:inline"> · </span>al {m.partialDay}</span>
        </>
    ) : (
        monthShort(m.key)
    );

/** Por mes: one stone column per month, the mean as a dashed rule, the open month in Signal, the running one faded. */
export function PorMesChart() {
    const { months, average, peak } = POR_MES;
    const max = Math.max(...months.map((m) => m.amount)) * 1.12;
    return (
        <div className="w-full">
            <div className="relative flex h-36 items-end gap-2 sm:gap-3">
                {months.map((m) => (
                    <div key={m.key} className="flex h-full flex-1 flex-col justify-end">
                        <div
                            className="rounded-[3px]"
                            style={{
                                height: at(m.amount, max),
                                background: m.key === peak ? INK.you : INK.stoneHi,
                                opacity: m.key === peak ? 1 : m.partialDay ? 0.25 : 0.55,
                            }}
                        />
                    </div>
                ))}
                <div className="pointer-events-none absolute inset-x-0 border-t border-dashed border-bone/70" style={{ bottom: at(average, max) }}>
                    <span className="absolute bottom-1 right-0 rounded-[3px] bg-slate/80 px-1 text-label text-bone">Promedio {mxn(average)}</span>
                </div>
            </div>
            <div className="mt-1.5 flex gap-2 text-center text-label text-dust sm:gap-3">
                {months.map((m) => (
                    <span key={m.key} className={cn("flex-1 truncate", m.key === peak && "font-medium text-signal")}>
                        {monthAxis(m)}
                    </span>
                ))}
            </div>
        </div>
    );
}

/** Por categoría: the period as one bar, each root category in its taxonomy color; legend is name and percent. */
export function ComposicionChart() {
    const { slices } = POR_CATEGORIA;
    return (
        <div className="w-full">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-label">
                {slices.slice(0, 5).map((s) => (
                    <span key={s.name} className="flex items-center gap-1.5 text-dust">
                        <i className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                        {s.name} <span className="tabular text-bone">{pct(s.share)}</span>
                    </span>
                ))}
            </div>
            <div className="mt-3 flex h-8 gap-[2px] overflow-hidden rounded-[6px]">
                {slices.map((s, i) => (
                    <div key={s.name} style={{ width: pct(s.share), background: s.color }} className={cn(i === 0 && "ring-2 ring-inset ring-bone")} />
                ))}
            </div>
            <p className="mt-2 text-label text-ash">{slices.length} categorías · lo que no tiene, en gris</p>
        </div>
    );
}

/* ------------------------------------------------------------------ Plan */

/** Lo que se va: the fijos month by month, stacked by charge; what is projected sits on its own band. */
export function FijosChart() {
    const { timeline, firstFuture } = LO_QUE_SE_VA;
    const totals = timeline.map((m) => m.values.reduce((a, b) => a + b, 0));
    const max = Math.max(...totals) * 1.15;
    return (
        <div className="w-full">
            <div className="flex h-36 items-stretch">
                {timeline.map((m, i) => (
                    <div
                        key={m.key}
                        className={cn(
                            "relative flex flex-1 flex-col-reverse justify-start px-1",
                            i >= firstFuture && "bg-white/[0.045]",
                            i === firstFuture && "border-l border-dashed border-lineStrong"
                        )}
                    >
                        {i === firstFuture && <span className="absolute left-1.5 top-1 text-label text-dust">Proyección</span>}
                        {m.values.map((v, j) =>
                            v > 0 ? <div key={j} className="border-t border-slate first:rounded-b-[2px]" style={{ height: at(v, max), background: RAMP[j] }} /> : null
                        )}
                    </div>
                ))}
            </div>
            <div className="mt-1.5 flex text-center text-label text-dust">
                {timeline.map((m) => (
                    <span key={m.key} className="flex-1">{monthShort(m.key)}</span>
                ))}
            </div>
        </div>
    );
}

/** Lo que entra: nómina and extra stacked in Signal, the fijos as a line over them. */
export function ContrasteChart() {
    const { months, firstFuture } = LO_QUE_ENTRA;
    const max = Math.max(...months.map((m) => Math.max(m.nomina + m.extra, m.fijos))) * 1.12;
    const n = months.length;
    const cx = (i: number) => ((i + 0.5) / n) * 100;
    const y = (v: number) => 100 - (v / max) * 100;
    return (
        <div className="w-full">
            <div className="mb-3 flex gap-4 text-label text-dust">
                <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-[2px]" style={{ background: INK.you }} />Nómina</span>
                <span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-[2px]" style={{ background: INK.youSoft }} />Extra</span>
                <span className="flex items-center gap-1.5"><i className="h-0.5 w-3" style={{ background: INK.bone }} />Fijos</span>
            </div>
            <div className="relative h-32">
                <div className="absolute inset-0 flex">
                    {months.map((m, i) => (
                        <div key={m.key} className={cn("flex flex-1 flex-col justify-end px-1.5", i >= firstFuture && "border-l border-dashed border-lineStrong bg-white/[0.045]")}>
                            <div className="rounded-t-[2px]" style={{ height: at(m.extra, max), background: INK.youSoft, opacity: i >= firstFuture ? 0.5 : 1 }} />
                            <div style={{ height: at(m.nomina, max), background: INK.you, opacity: i >= firstFuture ? 0.5 : 1 }} />
                        </div>
                    ))}
                </div>
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
                    <path d={months.map((m, i) => `${i ? "L" : "M"}${cx(i)} ${y(m.fijos)}`).join(" ")} fill="none" stroke={INK.bone} strokeWidth={2} style={LINE} />
                </svg>
                {months.map((m, i) => (
                    <span key={m.key} className="absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 bg-slate" style={{ left: `${cx(i)}%`, top: `${y(m.fijos)}%`, borderColor: INK.bone }} />
                ))}
            </div>
            <div className="mt-1.5 flex text-center text-label text-dust">
                {months.map((m) => (
                    <span key={m.key} className="flex-1">{monthShort(m.key)}</span>
                ))}
            </div>
        </div>
    );
}

/* ------------------------------------------------------------------ Pagos */

const WEEK = ["L", "M", "M", "J", "V", "S", "D"];

/** Pagos: the card payment as printed on the statement, then the month — today filled, a dot under every charge, the picked day ringed. */
export function PagosChart() {
    const { card, monthStartsOn, days, today, picked, upcoming, charged } = PAGOS;
    const cells = [...Array.from({ length: monthStartsOn }, () => 0), ...Array.from({ length: days }, (_, i) => i + 1)];
    return (
        <div className="w-full space-y-4">
            <div className="flex items-center justify-between gap-3 rounded-card bg-white/[0.05] px-3 py-2.5">
                <span className="flex min-w-0 items-center gap-2.5">
                    <CreditCard size={14} aria-hidden className="shrink-0 text-dust" />
                    <span className="min-w-0">
                        <span className="block text-body-sm font-medium text-bone">Pago para no generar intereses</span>
                        <span className="block text-label text-ash">
                            fecha límite {card.due} · pago mínimo {mxn2(card.minimum)}
                        </span>
                    </span>
                </span>
                <span className="shrink-0 tabular text-body-sm text-bone">{mxn2(card.amount)}</span>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)] gap-4">
                <div>
                    <div className="grid grid-cols-7 text-center text-[10px] text-ash">
                        {WEEK.map((d, i) => (
                            <span key={i}>{d}</span>
                        ))}
                    </div>
                    <div className="mt-1 grid grid-cols-7 gap-y-0.5 text-center text-[11px] tabular">
                        {cells.map((d, i) => (
                            <span key={i} className="relative flex h-6 items-center justify-center">
                                {d > 0 && (
                                    <span
                                        className={cn(
                                            "flex h-5 w-5 items-center justify-center rounded-full",
                                            d === today ? "bg-bone text-night" : d === picked ? "text-bone ring-1 ring-bone" : "text-dust"
                                        )}
                                    >
                                        {d}
                                    </span>
                                )}
                                {(charged as readonly number[]).includes(d) && d !== today && (
                                    <span className="absolute bottom-0 h-1 w-1 rounded-full bg-signal" />
                                )}
                            </span>
                        ))}
                    </div>
                </div>
                <ul className="space-y-1.5 text-label">
                    <li className="text-ash">Octubre</li>
                    {upcoming.map((u) => (
                        <li key={u.label} className={cn("flex justify-between gap-2", u.day === picked ? "text-bone" : "text-dust")}>
                            <span className="truncate">
                                {u.day} · {u.label}
                            </span>
                            <span className="tabular">{mxn(u.amount)}</span>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}

/* ---------------------------------------------------------------- Precios */

/** The ticket, read line by line, and the price book's line for the product that moved. */
export function PreciosChart() {
    const { store, total, rows, history, median, delta } = PRECIOS;
    const lo = Math.min(...history, median) * 0.94, hi = Math.max(...history) * 1.04;
    const y = (v: number) => ((hi - v) / (hi - lo)) * 100;
    const x = (i: number) => (i / (history.length - 1)) * 100;
    const d = history.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join(" ");
    return (
        <div className="grid w-full items-center gap-6 sm:grid-cols-[200px_minmax(0,1fr)]">
            <div className="mx-auto w-full max-w-[200px] rounded-[4px] border border-lineStrong bg-night/60 px-4 py-3 font-mono text-[10px] text-dust">
                <p className="text-center tracking-widest text-bone">{store}</p>
                <div className="my-2 border-t border-dashed border-lineStrong" />
                {rows.map(([name, amount, hot]) => (
                    <p key={name} className={cn("-mx-1 flex justify-between rounded-[2px] px-1 py-px", hot && "bg-signal/15 text-signal")}>
                        <span>{name.toUpperCase()}</span>
                        <span>{amount}</span>
                    </p>
                ))}
                <div className="my-2 border-t border-dashed border-lineStrong" />
                <p className="flex justify-between text-bone">
                    <span>TOTAL</span>
                    <span>{total}</span>
                </p>
            </div>
            <div>
                <p className="mb-6 text-label text-dust">Leche 1L · precio por litro, ticket por ticket</p>
                <div className="relative h-24">
                    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
                        <line x1={0} x2={100} y1={y(median)} y2={y(median)} stroke={INK.stone} strokeDasharray="3 4" style={LINE} />
                        <path d={d} fill="none" stroke={INK.stoneHi} strokeWidth={2} style={LINE} />
                    </svg>
                    <span className="absolute right-0 pt-1.5 text-label text-ash" style={{ top: `${y(median)}%` }}>
                        Lo típico {mxn2(median)}
                    </span>
                    {history.map((v, i) => (
                        <span
                            key={i}
                            className={cn("absolute -translate-x-1/2 -translate-y-1/2 rounded-full", i === history.length - 1 ? "h-3.5 w-3.5 bg-signal" : "h-2 w-2 border-2 bg-slate")}
                            style={{ left: `${x(i)}%`, top: `${y(v)}%`, borderColor: INK.stoneHi }}
                        />
                    ))}
                    <span className="absolute right-0 -translate-y-full whitespace-nowrap pb-2.5 text-label font-medium text-signal" style={{ top: `${y(history[history.length - 1]!)}%` }}>
                        {mxn2(history[history.length - 1]!)} · {delta}
                    </span>
                </div>
            </div>
        </div>
    );
}
