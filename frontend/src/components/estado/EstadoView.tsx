"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { CalendarDays } from "lucide-react";
import { useAppData } from "@/components/AppChrome";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import { useMovimientosSearch } from "@/components/movimientos/MovimientosSearchProvider";
import { useTransactions } from "@/components/movimientos/useTransactions";
import { useAttention } from "@/components/movimientos/useAttention";
import { useRecurringSeries } from "@/components/recurrentes/useRecurringSeries";
import { useReceipts } from "@/components/precios/useReceipts";
import { BackendNotice, Button, EmptyState, Skeleton } from "@/components/ui";
import type { AttentionKind, Transaction } from "@/lib/api";
import { useBankScope, useStatements } from "@/lib/banks";
import { useCategories } from "@/lib/categories";
import { cn } from "@/lib/cn";
import { dayLabel, mxn, mxn2 } from "@/lib/format";
import { DECILE_LABELS, ENIGH_MONTHLY, ENIGH_SPEND_RATIO, NATIONAL_SPEND_RATIO, decileIndex, percentileOf, valueAtPercentile } from "@/lib/enigh";
import {
    HORMIGA_MAX,
    HOURS_PER_MONTH,
    balanceAgainst,
    completeMonths,
    concentration,
    extremes,
    growthWords,
    hormiga,
    ratioWords,
    readCommitted,
    readDays,
    readEstado,
    readPayday,
    stretches,
    trendOf,
    weekendShare,
    type Leaf,
} from "@/lib/lecturaEstado";
import { CANASTA_SOURCE } from "@/lib/canasta";
import { RUBRO_LABELS } from "@/lib/enighRubros";
import { INPC_SOURCE } from "@/lib/inpc";
import { inpcChange, inpcIndexed, readCanasta, readPriceDrift, readRubros } from "@/lib/lecturaPais";
import { EMPTY_QUERY, UNCATEGORIZED } from "@/lib/movimientosQuery";
import { fromIso, monthName, SPAN_MONTHS, spanBounds, spanMonthKeys } from "@/lib/porMes";
import { track } from "@/lib/telemetry";
import {
    BalanceChart,
    DecilChart,
    DiasChart,
    HorasChart,
    NecesidadChart,
    SegundaChart,
    SemanaChart,
} from "./EstadoCharts";
import {
    CalendarioChart,
    ComprometidoChart,
    ConcentracionChart,
    DecilRatioChart,
    DiaCeroChart,
    EfectivoChart,
    ExtremosChart,
    HabitualChart,
    HormigaChart,
    TendenciaChart,
    dayShort,
    pct,
} from "./HabitosCharts";
import { CanastaChart, InpcChart, RubrosChart } from "./PaisCharts";
import { useIngresoMensual } from "./useIngresoMensual";
import { useReveal } from "./useReveal";

/**
 * Lectura: the first face of Movimientos. The last six months of cargos read
 * as eight findings, one card each — the sentence is the card's title, the
 * chart is its proof, the line under it says what it means.
 *
 * It reads the same fixed span as Por mes and ignores the ⌘K query on purpose:
 * "gastas como un hogar del decil IX" is a claim about everything, and a
 * filtered set would make it a claim about nothing. Banks still apply.
 *
 * Three readings need to know what comes in (decil, balance, horas). Income is
 * never inferred: it is what the user typed here, or the deposits they labeled
 * nómina in Plan. Without it those cards ask for it instead of guessing.
 */
export function EstadoView({
}: {
} = {}) {
    const { dataVersion } = useAppData();
    const { anchor, selectCustom } = useTimeWindow();
    const { statementIds } = useBankScope(dataVersion);
    const statements = useStatements(dataVersion);
    const categories = useCategories();
    const { openModal } = useMovimientosSearch();

    const keys = useMemo(() => spanMonthKeys(anchor), [anchor]);
    const bounds = useMemo(() => spanBounds(anchor), [anchor]);
    const { items, error, loading } = useTransactions(bounds, dataVersion, statementIds);
    const attention = useAttention(bounds, dataVersion, statementIds);
    const reading = useMemo(
        () => (items ? readEstado(items, categories, keys) : null),
        [items, categories, keys]
    );
    const { income, source, setDeclared } = useIngresoMensual(items, keys);
    const [editing, setEditing] = useState(false);
    // What the statements in scope cover, from their own periods. A month
    // outside it is a month the record only half saw. Without periods (an
    // older backend), the cargos themselves bound the record.
    const coverage = useMemo(() => {
        const inScope = (statements ?? []).filter((s) => !statementIds || statementIds.includes(s.id));
        const starts = inScope.map((s) => s.period_start).filter((d): d is string => !!d).sort();
        const ends = inScope.map((s) => s.period_end).filter((d): d is string => !!d).sort();
        const dates = (items ?? []).map((t) => t.date).sort();
        return {
            start: starts[0] ?? dates[0] ?? anchor,
            end: ends[ends.length - 1] ?? anchor,
        };
    }, [statements, statementIds, items, anchor]);
    // The fijos the user pinned in Plan, for the committed-money reading. The
    // same three sources Plan and Recurrentes agree on; nothing is inferred.
    const series = useRecurringSeries(dataVersion);
    // The tickets, for the reading that holds the user's own prices against the INPC.
    const { receipts, terms } = useReceipts(dataVersion);
    const pinned = useMemo(() => {
        const keys = new Set(series.fijos.state.pinnedKeys);
        const detectedKeys = new Set(series.detected.map((i) => i.key));
        return [
            ...series.detected.filter((i) => keys.has(i.key)),
            ...series.manuals.filter((m) => !detectedKeys.has(m.key)),
            ...series.taughtRest.filter((i) => keys.has(i.key)),
        ];
    }, [series.fijos.state.pinnedKeys, series.detected, series.manuals, series.taughtRest]);

    if (error) {
        return (
            <div className="space-y-4">
                <BackendNotice what="tus movimientos" detail={error} />
            </div>
        );
    }

    if (reading === null) {
        return <EstadoSkeleton />;
    }

    if (reading.count === 0) {
        return (
            <div className="space-y-4">
                <EmptyState icon={CalendarDays} title="Todavía no hay nada que leer">
                    Sube un estado de cuenta y Tomin lo lee aquí.
                </EmptyState>
            </div>
        );
    }

    /** Opens the modal over the whole span, so what it lists is what was read. */
    function ver(source: string, seed: typeof EMPTY_QUERY) {
        if (bounds.start && bounds.end) selectCustom(bounds.start, bounds.end, "lectura");
        openModal(source, seed);
    }

    const withYear = new Set(keys.map((k) => k.slice(0, 4))).size > 1;
    const avg = reading.average;

    // 1 · Decil
    const spendP = percentileOf(avg, ENIGH_MONTHLY.gasto);
    const equivalent = valueAtPercentile(spendP, ENIGH_MONTHLY.ingreso);
    const incomeP = income ? percentileOf(income, ENIGH_MONTHLY.ingreso) : null;
    const eqRatio = income ? equivalent / income : 0;
    const decilFoot = !income
        ? `Tus ${mxn(avg)} de gasto al mes son los de un hogar que ingresa ~${mxn(equivalent)}. Dinos cuánto entra y verás qué tan lejos está de lo tuyo.`
        : eqRatio > 1.15
          ? `Ganas más que ~${Math.round(incomeP!)}% de los hogares. Tu gasto es el de alguien que gana ${ratioWords(eqRatio)}.`
          : eqRatio < 0.87
            ? `Ganas más que ~${Math.round(incomeP!)}% de los hogares y gastas como alguien que gana menos que tú. Ese es tu margen.`
            : `Ganas más que ~${Math.round(incomeP!)}% de los hogares, y tu gasto va de acuerdo con lo que ganas.`;

    // 2 · Balance
    const bal = income ? balanceAgainst(reading, income) : null;

    // 3 · Día del mes
    const shares = stretches(reading.byDay);
    const diasFocus = shares[0] < 0.25 ? "late" : shares[0] > 0.45 ? "early" : null;
    const diasTitle = diasFocus === "late"
        ? "Gastas más en la segunda mitad del mes"
        : diasFocus === "early"
          ? "Gastas más al inicio del mes"
          : "Tu gasto se reparte a lo largo del mes";

    // 4 · Fin de semana
    const we = weekendShare(reading.byWeekday);
    const weTitle = we >= 0.5
        ? "Más de la mitad cae en fin de semana"
        : we >= 0.4
          ? "Casi la mitad cae en fin de semana"
          : `${Math.round(we * 100)}% de tu gasto cae en fin de semana`;

    // 5 · Necesidad
    const tier = (t: string) => reading.tiers.find((s) => s.tier === t)!;
    const primera = tier("primera"), segunda = tier("segunda"), sin = tier("sin");

    // 6 · Horas
    const hourValue = income ? income / HOURS_PER_MONTH : 0;
    const movable = reading.leaves.find((l) => l.tier !== "primera") ?? null;
    let horasRows: Leaf[] = reading.leaves.slice(0, 3);
    if (movable && !horasRows.includes(movable)) horasRows = [...horasRows.slice(0, 2), movable];

    // 7 · Segunda por mes
    const held = reading.months.filter((m) => m.count > 0);
    const first = held[0];
    const peak = held.reduce((b, m) => (m.segunda > b.segunda ? m : b), held[0]!);
    const growth = first && first.segunda > 0 ? growthWords(peak.segunda / first.segunda) : null;

    // 8 · No cuadran
    const byId = new Map((items ?? []).map((t) => [t.id, t]));
    const flagged = attention.items
        .map((a) => ({ a, t: byId.get(a.transaction_id) }))
        .filter((x): x is { a: (typeof attention.items)[number]; t: Transaction } => !!x.t)
        .sort((x, y) => Math.abs(y.t.amount) - Math.abs(x.t.amount))
        .slice(0, 4);

    const last = held[held.length - 1];
    const name = (key: string) => monthName(key, withYear);
    // The months the record covers whole: what a trend, an extreme or a
    // running total may be read over. The others are named where it matters.
    const complete = completeMonths(held, coverage);
    const completeKeys = complete.map((m) => m.key);
    const skipped = held.filter((m) => !completeKeys.includes(m.key));
    const skippedNote = skipped.length === 0
        ? ""
        : ` Sin ${skipped.map((m) => name(m.key)).join(" ni ")}, que el registro no cubre completo.`;

    // 9 · Concentración
    const conc = concentration(reading.merchants, 3);
    const concTitle = conc.top.length === 0
        ? "Sin lugares que leer todavía"
        : conc.top.length === 1
          ? `Un solo lugar se lleva el ${pct(conc.share)} de tu gasto`
          : `${conc.top.length} lugares se llevan el ${pct(conc.share)} de tu gasto`;

    // 10 · Hormiga
    const ant = hormiga(reading.buckets);

    // 11 · Efectivo
    const cash = reading.cash;
    const cashTitle = cash.count === 0
        ? "No retiras efectivo: cada peso deja huella"
        : `${mxn(cash.amount / held.length)} al mes salen en cajero y no sabemos a dónde van`;

    // 12 · Días con gasto
    const days = readDays(reading.byDate, held.map((m) => m.key), coverage.start, coverage.end);
    const per30 = days.total > 0 ? Math.round((days.active / days.total) * 30) : 0;
    const gap = days.gap;

    // 13 · Habitual contra nuevo
    const habit = reading.habit;
    const habitAfter = habit.months.filter((m) => !m.base);
    const habitTitle = habitAfter.length === 0
        ? "Falta un segundo mes para saber qué lugar es nuevo"
        : `${pct(habit.knownShare)} de tu gasto va a lugares donde ya habías pagado`;

    // 14 · Tendencia
    const slope = trendOf(complete);
    const trendTitle = slope === null
        ? "Faltan meses para leer una tendencia"
        : Math.abs(slope) < avg * 0.03
          ? "Tu gasto mensual se mantiene"
          : slope > 0
            ? `Cada mes gastas ~${mxn(slope)} más que el anterior`
            : `Cada mes gastas ~${mxn(-slope)} menos que el anterior`;

    // 15 · Extremos
    const ext = extremes(complete);
    const extTitle = !ext
        ? "Falta un segundo mes para comparar"
        : ext.ratio < 1.15
          ? "Tus meses se parecen: el más caro y el más barato casi empatan"
          : `Tu mes más caro costó ${ext.ratio.toFixed(1)} veces tu mes más barato`;

    // 16 · Día cero
    const payday = income && complete.length > 0 ? readPayday(reading.byDate, completeKeys, income) : null;
    const ranOut = payday ? payday.perMonth.filter((m) => m.early).length : 0;

    // 17 · Comprometido antes del día 1
    const committed = income ? readCommitted(pinned, income, avg) : null;

    // 18 · Decil contra decil
    const incomeD = incomeP === null ? null : decileIndex(incomeP);
    const decileRatio = incomeD === null ? null : ENIGH_SPEND_RATIO[incomeD]!;

    // 19 · Rubros contra la ENIGH. By the income decile when there is one;
    // by the spend decile until then, and the foot says which.
    const compareD = incomeD ?? decileIndex(spendP);
    const rubros = readRubros(reading.leaves, categories, compareD);
    const rubroTop = rubros.top;
    const rubroTitle = !rubroTop
        ? "Sin categorías que caigan en un rubro de la ENIGH"
        : `Destinas ${pct(rubroTop.share)} a ${RUBRO_LABELS[rubroTop.rubro].toLowerCase()}; el hogar del decil ${DECILE_LABELS[compareD]}, ${pct(rubroTop.decileShare)}`;
    const unmappedShare = rubros.mapped + rubros.unmapped.amount > 0
        ? rubros.unmapped.amount / (rubros.mapped + rubros.unmapped.amount)
        : 0;

    // 20 · Canasta
    const canasta = last ? readCanasta(reading.leaves, categories, avg, held.length, last.key) : null;

    // 21 · INPC
    const drift = receipts ? readPriceDrift(receipts, terms) : null;
    const driftInpc = drift ? inpcChange(drift.from, drift.to) : null;
    const inpcPoints = inpcIndexed(keys);
    const inpcFirst = inpcPoints[0], inpcLast = inpcPoints[inpcPoints.length - 1];
    const moved = (ratio: number, plural = true) => {
        const d = ratio - 1;
        if (Math.abs(d) < 0.005) return plural ? "no se movieron" : "no se movió";
        return `${d > 0 ? (plural ? "subieron" : "subió") : plural ? "bajaron" : "bajó"} ${pct(Math.abs(d))}`;
    };
    const inpcTitle = drift && drift.inpcMedian !== null
        ? `Tus productos ${moved(drift.median)}; el INPC de alimentos ${moved(drift.inpcMedian, false)} en los mismos meses`
        : drift
          ? `Tus productos ${moved(drift.median)} entre ${name(drift.from)} y ${name(drift.to)}`
          : inpcFirst && inpcLast && inpcFirst !== inpcLast
            ? `Los alimentos ${moved(inpcLast.alimentos / inpcFirst.alimentos)} de ${name(inpcFirst.key)} a ${name(inpcLast.key)}, según el INPC`
            : "El INPC de estos meses todavía no está publicado";
    const inpcFoot = drift
        ? `${drift.products} ${drift.products === 1 ? "producto comprado" : "productos comprados"} en más de un mes entre ${name(drift.from)} y ${name(drift.to)}, cada uno contra el INPC de sus propios meses; por litro o kilo cuando el ticket dio tamaño. ${driftInpc ? `El INPC general ${moved(driftInpc.general, false)} de ${name(drift.from)} a ${name(drift.to)}.` : "El INPC de esos meses no está en la tabla."} ${INPC_SOURCE}.`
        : `Sube tickets del súper y esta lectura compara tus precios con el índice. ${INPC_SOURCE}.`;
    // The user's point sits on the alimentos line at `to`, moved by how much
    // their prices beat or trailed the INPC over matched months — the gap
    // between point and line is the sentence's gap.
    const driftEnd = drift ? inpcPoints.find((p) => p.key === drift.to) : undefined;
    const userPoint = drift && drift.inpcMedian !== null && driftEnd
        ? { key: drift.to, value: (driftEnd.alimentos * drift.median) / drift.inpcMedian, label: `Tus tickets ${moved(drift.median)}` }
        : null;

    return (
        <div className="space-y-5">
            <section className="card space-y-4">
                <div className="min-w-0">
                    <h2 className="font-display text-title-lg font-normal text-ink">Tu estado de cuenta, leído.</h2>
                    <IncomeLine
                        income={income}
                        source={source}
                        editing={editing}
                        onEdit={setEditing}
                        onSave={(v) => {
                            track("lectura.income", { set: v !== null });
                            setDeclared(v);
                            setEditing(false);
                        }}
                    />
                </div>
            </section>

            {/* The decil strip leads the section across the whole row: the
                readings after it come in pairs, and the rubros, ten rows
                tall, close it on a row of their own. */}
            <Section title="Contra el país">
                <Card
                    layout="feature"
                    title={`Gastas como un hogar del decil ${DECILE_LABELS[decileIndex(spendP)]}`}
                    foot={decilFoot}
                    aside={
                        <Figures
                            items={[
                                { label: "Tu gasto al mes", value: mxn(avg), note: `promedio de ${held.length} ${held.length === 1 ? "mes" : "meses"}`, on: true },
                                {
                                    label: `Un hogar del decil ${DECILE_LABELS[decileIndex(spendP)]}`,
                                    value: mxn(ENIGH_MONTHLY.gasto[decileIndex(spendP)]!),
                                    note: `gasta al mes; gana ${mxn(ENIGH_MONTHLY.ingreso[decileIndex(spendP)]!)}`,
                                },
                                { label: "Gastas como quien gana", value: `~${mxn(equivalent)}`, note: "al mes, según la ENIGH" },
                                income
                                    ? {
                                          label: "Tu ingreso",
                                          value: mxn(income),
                                          note: income >= equivalent ? `${mxn(income - equivalent)} más que eso` : `${mxn(equivalent - income)} menos que eso`,
                                      }
                                    : { label: "Gastas más que", value: `~${Math.round(spendP)}%`, note: "de los hogares del país" },
                            ]}
                        />
                    }
                >
                    <DecilChart spend={avg} spendP={spendP} income={income} incomeP={incomeP} />
                </Card>

                {bal && (
                    <Card
                        title={bal.factor > 1 ? `Sale $${bal.factor.toFixed(2)} por cada $1 que entra` : `Salen $${bal.factor.toFixed(2)} de cada $1 que entra`}
                        foot={`${bal.gap > 0 ? `En ${bal.months} meses faltaron ~${mxn(bal.gap)}.` : `En ${bal.months} meses te sobraron ~${mxn(-bal.gap)}.`} El hogar promedio en México gasta $${NATIONAL_SPEND_RATIO.toFixed(2)} de cada peso.`}
                    >
                        <BalanceChart months={reading.months} income={income!} />
                    </Card>
                )}

                {bal && incomeD !== null && decileRatio !== null && (
                    <Card
                        title={`Los hogares de tu decil gastan $${decileRatio.toFixed(2)} de cada peso; tú $${bal.factor.toFixed(2)}`}
                        foot={`Decil ${DECILE_LABELS[incomeD]} por tu ingreso de ${mxn(income!)}. El decil I gasta $${ENIGH_SPEND_RATIO[0]!.toFixed(2)} de cada peso, más de lo que declara; el X, $${ENIGH_SPEND_RATIO[9]!.toFixed(2)}.`}
                    >
                        <DecilRatioChart ratios={ENIGH_SPEND_RATIO} decile={incomeD} factor={bal.factor} />
                    </Card>
                )}

                <Card
                    title={
                        !canasta
                            ? "La canasta alimentaria de estos meses todavía no está publicada"
                            : canasta.food <= 0
                              ? "Sin gasto de supermercado que comparar con la canasta alimentaria"
                              : `Tu comida de casa alimentaría a ${canasta.foodPersons.toFixed(1)} personas con la canasta alimentaria`
                    }
                    foot={
                        canasta
                            ? `Canasta alimentaria urbana de ${name(canasta.key)}: ${mxn2(canasta.line.alimentariaUrbana)} por persona al mes; con lo no alimentario, ${mxn2(canasta.line.completaUrbana)}. ${CANASTA_SOURCE}.`
                            : `${CANASTA_SOURCE}: la serie llega hasta agosto de 2026.`
                    }
                >
                    {canasta ? (
                        <CanastaChart reading={canasta} average={avg} />
                    ) : (
                        <p className="text-body-sm text-graphite">Cuando INEGI publique el mes, la lectura aparece aquí.</p>
                    )}
                </Card>

                {receipts === null ? (
                    <CardSkeleton />
                ) : (
                <Card title={inpcTitle} foot={inpcFoot}>
                    {inpcPoints.length >= 2 ? (
                        <InpcChart points={inpcPoints} user={userPoint} />
                    ) : (
                        <p className="text-body-sm text-graphite">El INPC se publica el día 9 de cada mes; estos meses aún no están en la tabla.</p>
                    )}
                </Card>
                )}

                <Card
                    layout="full"
                    title={rubroTitle}
                    foot={
                        <>
                            {incomeD !== null ? "Decil por tu ingreso" : "Decil por tu gasto, hasta que digas cuánto entra"}; rubros de la ENIGH 2024, por hogar.
                            {unmappedShare > 0 && (
                                <>
                                    {" "}
                                    {pct(unmappedShare)} de tu gasto ({rubros.unmapped.names.slice(0, 3).join(", ")}
                                    {rubros.unmapped.names.length > 3 ? "…" : ""}) no cae en ningún rubro y quedó fuera.
                                </>
                            )}
                        </>
                    }
                >
                    {rubroTop ? (
                        <RubrosChart rows={rubros.rows} decile={compareD} decileLabel={DECILE_LABELS[compareD]!} highlight={rubroTop.rubro} />
                    ) : (
                        <p className="text-body-sm text-graphite">Clasifica tus cargos en comida, vivienda, transporte o salud y esta lectura los compara con los hogares de tu decil.</p>
                    )}
                </Card>
            </Section>

            <Section title="Con tu ingreso">
                {!income ? (
                    <AskIncome onAsk={() => setEditing(true)} />
                ) : (
                    <>
                        {payday ? (
                            <Card
                                title={payday.crossDay !== null ? `El día ${payday.crossDay} ya gastaste todo lo que entra` : `Tu ingreso alcanza todo el mes: al cierre te quedan ~${mxn(payday.leftover)}`}
                                foot={`Mes promedio sobre ${complete.length} ${complete.length === 1 ? "mes completo" : "meses completos"}. ${ranOut === 0 ? "En ninguno se acabó el dinero antes del último día." : `En ${ranOut} de ${complete.length} el dinero se acabó antes del último día.`}${skippedNote}`}
                            >
                                <DiaCeroChart payday={payday} income={income} />
                            </Card>
                        ) : (
                            <Card title="Qué día del mes se acaba tu ingreso" foot={`El registro no cubre ningún mes completo todavía.${skippedNote}`}>
                                <p className="text-body-sm text-graphite">Con un mes entero de cargos, esta lectura sigue lo gastado día a día y marca el día en que ya no queda nada.</p>
                            </Card>
                        )}

                        {series.loading ? (
                            <CardSkeleton />
                        ) : !committed || committed.rows.length === 0 ? (
                            <AskFijos />
                        ) : (
                            <Card
                                title={`${mxn(committed.fijos)} de tus ${mxn(income)} ya están apartados antes del día 1`}
                                foot={`${pct(committed.share)} de tu ingreso son ${committed.rows.length} ${committed.rows.length === 1 ? "fijo" : "fijos"}. Lo variable del mes promedio fue ${mxn(committed.variable)}; ${committed.margin >= 0 ? `te quedan ${mxn(committed.margin)}` : `faltaron ${mxn(-committed.margin)}`}.`}
                            >
                                <ComprometidoChart committed={committed} income={income} />
                            </Card>
                        )}

                        {movable && (
                            <Card
                                layout="feature"
                                title={`${movable.name} te costó ${Math.round(movable.amount / hourValue)} horas de trabajo`}
                                foot={`Las horas salen de tu ingreso de ${mxn(income)} entre ${HOURS_PER_MONTH} horas de trabajo al mes.`}
                                aside={
                                    <Figures
                                        items={[
                                            { label: movable.name, value: `${Math.round(movable.amount / hourValue)} h`, note: mxn(movable.amount), on: true },
                                            { label: "En semanas de 40 h", value: (movable.amount / hourValue / 40).toFixed(1), note: "de trabajo completo" },
                                            {
                                                label: `Estas ${horasRows.length} categorías`,
                                                value: `${Math.round(horasRows.reduce((s, r) => s + r.amount, 0) / hourValue)} h`,
                                                note: mxn(horasRows.reduce((s, r) => s + r.amount, 0)),
                                            },
                                            { label: "Tu hora vale", value: `~${mxn(hourValue)}`, note: `con ${mxn(income)} al mes` },
                                        ]}
                                    />
                                }
                            >
                                <HorasChart rows={horasRows} hourValue={hourValue} highlight={movable.name} />
                            </Card>
                        )}
                    </>
                )}
            </Section>

            <Section title="En el tiempo">
                <Card title={diasTitle} foot={`${Math.round((1 - shares[0]) * 100)}% de tu gasto cae después del día 10.`}>
                    <DiasChart byDay={reading.byDay} shares={shares} focus={diasFocus} />
                </Card>

                <Card title={weTitle} foot="Sábado y domingo son el 29% de los días.">
                    <SemanaChart byWeekday={reading.byWeekday} share={we} />
                </Card>

                <Card
                    title={`Gastas en ${per30} de cada 30 días`}
                    foot={
                        !gap
                            ? `Ningún día sin gasto en los ${days.total} días que cubre el registro.`
                            : gap.days === 1
                              ? `Tu racha más larga sin gastar fue de un día, el ${dayShort(gap.from)}.`
                              : `Tu racha más larga sin gastar fue de ${gap.days} días, del ${dayShort(gap.from)} al ${dayShort(gap.to)}.`
                    }
                >
                    <CalendarioChart days={days} />
                </Card>

                <Card
                    title={trendTitle}
                    foot={
                        slope === null
                            ? `Con tres meses completos de cargos esta lectura dice si tu gasto sube o baja.${skippedNote}`
                            : `Recta ajustada sobre ${complete.length} meses completos: de ${mxn(complete[0]!.amount)} en ${name(complete[0]!.key)} a ${mxn(complete[complete.length - 1]!.amount)} en ${name(complete[complete.length - 1]!.key)}.${skippedNote}`
                    }
                >
                    <TendenciaChart months={complete.length > 0 ? complete : held} slope={slope} />
                </Card>

                <Card
                    title={extTitle}
                    foot={ext ? `${name(ext.max.key)} ${mxn(ext.max.amount)} contra ${name(ext.min.key)} ${mxn(ext.min.amount)}. El promedio de los meses con cargos fue ${mxn(avg)}.${skippedNote}` : `Con dos meses completos de cargos esta lectura compara el más caro con el más barato.${skippedNote}`}
                >
                    {ext ? <ExtremosChart months={complete} max={ext.max} min={ext.min} average={avg} /> : <p className="text-body-sm text-graphite">Todavía no hay dos meses completos en el registro.</p>}
                </Card>

                <Card
                    title={growth ? `Tu gasto de segunda ${growth} desde ${monthName(first!.key, withYear)}` : "Tu gasto de segunda necesidad, mes a mes"}
                    foot={first ? `De ${mxn(first.segunda)} en ${monthName(first.key, withYear)} a ${mxn(peak.segunda)} en ${monthName(peak.key, withYear)}.` : ""}
                >
                    <SegundaChart months={reading.months} />
                </Card>
            </Section>

            <Section title="En qué y dónde">
                <Card
                    title={`${Math.round(primera.share * 100)}% de tu gasto es de primera necesidad`}
                    foot={
                        <>
                            Primera y segunda necesidad suman el {Math.round((primera.share + segunda.share) * 100)}%.
                            {sin.count > 0 && (
                                <>
                                    {" "}
                                    <button
                                        type="button"
                                        className="text-ink underline decoration-muted underline-offset-2 hover:decoration-ink"
                                        onClick={() => ver("lectura-necesidad", { ...EMPTY_QUERY, categoryIds: [UNCATEGORIZED] })}
                                    >
                                        Clasificar {sin.count} {sin.count === 1 ? "cargo" : "cargos"}
                                    </button>{" "}
                                    afina esta lectura.
                                </>
                            )}
                        </>
                    }
                >
                    <NecesidadChart tiers={reading.tiers} />
                </Card>

                <Card
                    title={concTitle}
                    foot={reading.merchants.length > conc.top.length ? `Los otros ${reading.merchants.length - conc.top.length} lugares se reparten el ${pct(1 - conc.share - cash.share)}${cash.share > 0 ? `; el efectivo, el ${pct(cash.share)}` : ""}.` : "Todo tu gasto cabe en estos lugares."}
                >
                    <ConcentracionChart merchants={reading.merchants} highlight={conc.top.length} />
                </Card>

                <Card
                    title={`${pct(ant.countShare)} de tus cargos son de $${HORMIGA_MAX} o menos y suman el ${pct(ant.amountShare)} del dinero`}
                    foot={`Gasto hormiga: ${ant.count} ${ant.count === 1 ? "cargo" : "cargos"}, ${mxn(ant.amount)} en ${held.length} ${held.length === 1 ? "mes" : "meses"}. Cada uno es chico; juntos son ~${mxn(ant.amount / held.length)} al mes.`}
                >
                    <HormigaChart buckets={reading.buckets} />
                </Card>

                <Card
                    title={cashTitle}
                    foot={cash.count === 0
                        ? "Todo lo que sale de tus cuentas queda escrito en el estado. Cada retiro sería un hueco en esta lectura."
                        : `${pct(cash.share)} de tu gasto, en ${cash.count} ${cash.count === 1 ? "retiro" : "retiros"}. Lo que pagas con tarjeta deja huella; el efectivo no.`}
                >
                    <EfectivoChart months={reading.months} share={cash.share} />
                </Card>

                <Card
                    layout="feature"
                    title={habitTitle}
                    foot={habitAfter.length === 0
                        ? "Desde el segundo mes, cada lugar se compara con los que ya habías pagado."
                        : `Un lugar es nuevo el mes en que pagas ahí por primera vez; ${name(habit.months[0]!.key)} es el mes base.${cash.count > 0 ? " El efectivo no cuenta: no tiene lugar." : ""}`}
                    aside={
                        habitAfter.length > 0 && (
                            <Figures
                                items={[
                                    { label: "En lugares conocidos", value: pct(habit.knownShare), note: `desde ${name(habitAfter[0]!.key)}`, on: true },
                                    { label: "Lugares nuevos", value: String(habit.freshMerchants), note: `en ${habitAfter.length} ${habitAfter.length === 1 ? "mes" : "meses"}` },
                                    { label: "Gastado en nuevos", value: mxn(habit.freshAmount), note: `${pct(1 - habit.knownShare)} de tu gasto` },
                                    { label: "Al mes en nuevos", value: mxn(habit.freshAmount / habitAfter.length), note: "en promedio" },
                                ]}
                            />
                        )
                    }
                >
                    <HabitualChart months={habit.months} />
                </Card>
            </Section>

            <Section title="Lo que no cuadra">
                <Card
                    layout="full"
                    title={flagged.length === 0 ? "Ningún cargo fuera de lo común" : flagged.length === 1 ? "1 cargo que no cuadra" : `${flagged.length} cargos que no cuadran`}
                    foot="Tomin no adivina: tú dices si son tuyos."
                >
                    {flagged.length === 0 ? (
                        <p className="text-body-sm text-graphite">Ningún monto inusual, repetido o de un comercio nuevo en estos meses.</p>
                    ) : (
                        <ul className="divide-y divide-mist">
                            {flagged.map(({ a, t }, i) => (
                                <li key={a.transaction_id} className="lx-fade flex items-start gap-3 py-2.5" style={{ transitionDelay: `${i * 120}ms` }}>
                                    <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", a.severity === "warn" ? "bg-signal" : "bg-ash")} />
                                    <div className="min-w-0 flex-1">
                                        <p className="flex items-center gap-2 text-body-sm text-ink">
                                            <span className="truncate">{t.description}</span>
                                            <Flag kind={a.kind} />
                                        </p>
                                        <p className="text-label text-graphite">
                                            {dayLabel(fromIso(t.date))} · {a.reason}
                                        </p>
                                    </div>
                                    <span className="tabular text-body-sm text-ink">{mxn2(Math.abs(t.amount))}</span>
                                    <span className="flex shrink-0 gap-1">
                                        <Button size="sm" variant="ghost" onClick={() => attention.dismiss(a.transaction_id)}>Es mío</Button>
                                        <Button size="sm" variant="secondary" onClick={() => ver("lectura-cargo", { ...EMPTY_QUERY, needle: t.description })}>Ver</Button>
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
            </Section>

            <p className="text-label text-ash">
                Base: cargos de los últimos {SPAN_MONTHS} meses, sin «Entre mis cuentas» ni excluidos. Población: INEGI · ENIGH 2024, por hogar; líneas de pobreza e INPC del INEGI hasta agosto de 2026.
            </p>
        </div>
    );
}

/**
 * A card's three rows — title, proof, foot — from `lg` up are rows of the
 * section's grid, so two cards side by side share them: a title that wraps
 * to two lines pushes its neighbour's chart down with it, and both foot rules
 * sit on one line.
 */
const CARD = "card flex min-w-0 flex-col lg:row-span-3 lg:grid lg:grid-rows-subgrid lg:gap-y-0";

/**
 * How a card sits in its section's grid. `pair` shares its rows with the card
 * beside it. A card that has the row to itself is `feature` when it holds a
 * chart — the SVG charts are drawn for half a row and would scale their type
 * up across a whole one, so the chart keeps that width on the right and the
 * words take the left — or `full` when it holds a list that wants the width.
 */
type CardLayout = "pair" | "feature" | "full";

const LAYOUT: Record<CardLayout, { card: string; body: string; foot: string }> = {
    pair: { card: CARD, body: "mt-5 flex-1", foot: "mt-5" },
    feature: {
        card: "card flex min-w-0 flex-col lg:col-span-2 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,34rem)] lg:grid-rows-[auto_1fr_auto] lg:gap-x-12",
        body: "mt-5 lg:col-start-2 lg:row-span-3 lg:row-start-1 lg:mt-0 lg:self-center",
        foot: "mt-5 lg:col-start-1 lg:row-start-3",
    },
    full: { card: "card flex min-w-0 flex-col lg:col-span-2", body: "mt-5 flex-1", foot: "mt-5" },
};

/** A reading card: its title is the finding, its foot says what it means. The
 *  chart inside plays once, the first time the card is on screen. A feature
 *  card's `aside` holds the reading's figures under the title, in the column
 *  the chart leaves beside it. */
function Card({ title, foot, children, aside, layout = "pair" }: {
    title: string;
    foot: ReactNode;
    children: ReactNode;
    aside?: ReactNode;
    layout?: CardLayout;
}) {
    const { ref, seen } = useReveal<HTMLElement>();
    const l = LAYOUT[layout];
    return (
        <section ref={ref} data-play={seen} className={l.card}>
            <h3 className="text-body-lg font-medium text-ink">{title}</h3>
            {aside && <div className="mt-5 lg:col-start-1 lg:row-start-2 lg:self-center">{aside}</div>}
            <div className={l.body}>{children}</div>
            <div className={cn("border-t border-mist pt-4 text-body-sm text-graphite", l.foot)}>{foot}</div>
        </section>
    );
}

/** The figures a feature card reads from, two by two. */
function Figures({ items }: { items: { label: string; value: string; note: string; on?: boolean }[] }) {
    return (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-5">
            {items.map((f) => (
                <div key={f.label} className="min-w-0">
                    <dt className="text-label text-graphite">{f.label}</dt>
                    <dd className={cn("tabular mt-1 truncate text-metric-sm font-normal", f.on ? "text-edge" : "text-ink")}>{f.value}</dd>
                    <dd className="mt-0.5 text-label text-ash">{f.note}</dd>
                </div>
            ))}
        </dl>
    );
}

/** A run of readings under one short heading, in the two-column grid. */
function Section({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section className="space-y-3">
            <h2 className="text-label font-medium uppercase tracking-wider text-graphite">{title}</h2>
            <div className="grid gap-5 lg:grid-cols-2">{children}</div>
        </section>
    );
}

/** The committed-money card before any fijo is pinned: it points at Plan
 *  instead of guessing which charges are fixed. */
function AskFijos() {
    return (
        <Card
            title="Cuánto de tu ingreso ya está comprometido antes del día 1"
            foot={<Link href="/plan" className="text-edge hover:underline">Fijar mis gastos fijos en Plan</Link>}
        >
            <p className="text-body-sm text-graphite">
                Fija en Plan los cargos que llegan cada mes y esta lectura dice qué parte de lo que entra ya está apartada antes de empezar.
            </p>
        </Card>
    );
}

/** The readings that need what comes in. Income is never inferred, so until
 *  it is given they are one card that names them, not five that each ask. */
const INCOME_READINGS = [
    { title: "Cuánto sale por cada peso que entra", body: "Cuántos meses gastaste más de lo que entró y cuánto faltó." },
    { title: "Cuánto gastan de cada peso los hogares que ganan como tú", body: "Tu factor de gasto junto al de los hogares de tu mismo decil." },
    { title: "Qué día del mes se acaba tu ingreso", body: "Lo gastado día a día, y el día en que ya no queda nada." },
    { title: "Cuánto de tu ingreso ya está comprometido antes del día 1", body: "Qué parte del mes ya está apartada antes de empezar, con tus fijos." },
    { title: "Cuántas horas de trabajo cuesta lo que compras", body: "Cada categoría en horas de tu trabajo y no en pesos." },
] as const;

function AskIncome({ onAsk }: { onAsk: () => void }) {
    return (
        <Card
            layout="feature"
            title="Cinco lecturas esperan tu ingreso"
            foot={<Button size="sm" variant="secondary" onClick={onAsk}>Agregar mi ingreso</Button>}
            aside={
                <p className="text-body-sm text-graphite">
                    Tomin no adivina cuánto entra. Escríbelo una vez, o etiqueta tus depósitos de nómina en Plan, y estas
                    lecturas se calculan con tus cargos de los últimos {SPAN_MONTHS} meses.
                </p>
            }
        >
            <ul className="space-y-3">
                {INCOME_READINGS.map((r) => (
                    <li key={r.title} className="min-w-0">
                        <p className="text-body-sm font-medium text-ink">{r.title}</p>
                        <p className="text-label text-graphite">{r.body}</p>
                    </li>
                ))}
            </ul>
        </Card>
    );
}

function Flag({ kind }: { kind: AttentionKind }) {
    const word = { unusual_amount: "inusual", possible_duplicate: "duplicado", new_merchant: "nuevo" }[kind];
    return (
        <span className="shrink-0 rounded-tag border border-signal px-1.5 py-px text-caption font-medium uppercase text-ink">
            {word}
        </span>
    );
}

/** "Ingreso: $20,000/mes · Cambiar" — and the field that sets it. */
function IncomeLine({ income, source, editing, onEdit, onSave }: {
    income: number | null;
    source: "declarado" | "etiquetado" | null;
    editing: boolean;
    onEdit: (v: boolean) => void;
    onSave: (v: number | null) => void;
}) {
    const [draft, setDraft] = useState("");
    useEffect(() => {
        if (editing) setDraft(income ? String(Math.round(income)) : "");
    }, [editing, income]);

    if (editing) {
        const n = Number(draft.replace(/[^0-9.]/g, ""));
        return (
            <form
                className="mt-3 flex flex-wrap items-center gap-2"
                onSubmit={(e) => {
                    e.preventDefault();
                    if (n > 0) onSave(n);
                }}
            >
                <label className="text-body-sm text-graphite" htmlFor="lectura-ingreso">¿Cuánto entra al mes?</label>
                <span className="flex h-8 items-center rounded-control border border-muted bg-paper px-2 text-body-sm">
                    <span className="text-graphite">$</span>
                    <input
                        id="lectura-ingreso"
                        autoFocus
                        inputMode="numeric"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        className="w-28 bg-transparent px-1 tabular outline-none"
                        placeholder="20000"
                    />
                </span>
                <Button size="sm" variant="secondary" type="submit" disabled={!(n > 0)}>Guardar</Button>
                {source === "declarado" && (
                    <Button size="sm" variant="ghost" type="button" onClick={() => onSave(null)}>Quitar</Button>
                )}
                <Button size="sm" variant="ghost" type="button" onClick={() => onEdit(false)}>Cancelar</Button>
            </form>
        );
    }

    return (
        <p className="mt-2 text-body-sm text-graphite">
            {income ? (
                <>
                    {source === "etiquetado" ? "Ingreso de tu nómina etiquetada" : "Ingreso que escribiste"}:{" "}
                    <span className="tabular text-ink">{mxn(income)}/mes</span> ·{" "}
                </>
            ) : (
                <>Sin ingreso todavía: cinco lecturas lo necesitan · </>
            )}
            <button type="button" className="text-edge hover:underline" onClick={() => onEdit(true)}>
                {income ? "Cambiar" : "Agregar"}
            </button>
        </p>
    );
}

/** One card's geometry while the data behind it is still on its way: the
 *  fijos and the tickets arrive after the movements, and a card that first
 *  says "no tienes" and then fills in would be a lie for a second. */
function CardSkeleton() {
    return (
        <section className={CARD} aria-busy>
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="mt-5 h-[200px] w-full" />
            <Skeleton className="mt-5 h-4 w-2/3" />
        </section>
    );
}

/** The reading's geometry before the reading: the title card, then a dozen
 *  of the chart cards the grid draws, each with its title, its chart and its
 *  foot line. */
function EstadoSkeleton() {
    return (
        <div className="space-y-5" aria-busy>
            <section className="card space-y-4">
                <Skeleton className="h-9 w-80 max-w-full" />
                <Skeleton className="h-4 w-56" />
            </section>
            <div className="grid gap-5 lg:grid-cols-2">
                {Array.from({ length: 12 }).map((_, i) => (
                    <section key={i} className="card flex min-w-0 flex-col gap-4">
                        <Skeleton className="h-5 w-3/4" />
                        <Skeleton className="h-[200px] w-full" />
                        <Skeleton className="h-4 w-2/3" />
                    </section>
                ))}
            </div>
        </div>
    );
}
