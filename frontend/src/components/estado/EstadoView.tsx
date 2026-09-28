"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CalendarDays } from "lucide-react";
import { useAppData } from "@/components/AppChrome";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import { useMovimientosSearch } from "@/components/movimientos/MovimientosSearchProvider";
import { useTransactions } from "@/components/movimientos/useTransactions";
import { useAttention } from "@/components/movimientos/useAttention";
import { BackendNotice, Button, EmptyState, Skeleton } from "@/components/ui";
import type { AttentionKind, Transaction } from "@/lib/api";
import { useBankScope } from "@/lib/banks";
import { useCategories } from "@/lib/categories";
import { cn } from "@/lib/cn";
import { dayLabel, mxn, mxn2 } from "@/lib/format";
import { DECILE_LABELS, ENIGH_MONTHLY, NATIONAL_SPEND_RATIO, decileIndex, percentileOf, valueAtPercentile } from "@/lib/enigh";
import {
    HOURS_PER_MONTH,
    balanceAgainst,
    growthWords,
    ratioWords,
    readEstado,
    stretches,
    weekendShare,
    type Leaf,
} from "@/lib/lecturaEstado";
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
    const diasTitle = shares[0] < 0.25
        ? "Gastas más en la segunda mitad del mes"
        : shares[0] > 0.45
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

            <div className="grid gap-5 lg:grid-cols-2">
                <Card title={`Gastas como un hogar del decil ${DECILE_LABELS[decileIndex(spendP)]}`} foot={decilFoot}>
                    <DecilChart income={income} spendP={spendP} incomeP={incomeP} equivalent={equivalent} />
                </Card>

                {bal ? (
                    <Card
                        title={bal.factor > 1 ? `Sale $${bal.factor.toFixed(2)} por cada $1 que entra` : `Salen $${bal.factor.toFixed(2)} de cada $1 que entra`}
                        foot={`${bal.gap > 0 ? `En ${bal.months} meses faltaron ~${mxn(bal.gap)}.` : `En ${bal.months} meses te sobraron ~${mxn(-bal.gap)}.`} El hogar promedio en México gasta $${NATIONAL_SPEND_RATIO.toFixed(2)} de cada peso.`}
                    >
                        <BalanceChart months={reading.months} income={income!} />
                    </Card>
                ) : (
                    <AskIncome title="Cuánto sale por cada peso que entra" onAsk={() => setEditing(true)}>
                        Con tu ingreso, esta lectura dice cuántos meses gastaste más de lo que entró y cuánto faltó.
                    </AskIncome>
                )}

                <Card title={diasTitle} foot={`${Math.round((1 - shares[0]) * 100)}% de tu gasto cae después del día 10.`}>
                    <DiasChart byDay={reading.byDay} shares={shares} />
                </Card>

                <Card title={weTitle} foot="Sábado y domingo son el 29% de los días.">
                    <SemanaChart byWeekday={reading.byWeekday} share={we} />
                </Card>

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

                {income && movable ? (
                    <Card
                        title={`${movable.name} te costó ${Math.round(movable.amount / hourValue)} horas de trabajo`}
                        foot={`Con ${mxn(income)}/mes tu hora vale ~${mxn(hourValue)}.`}
                    >
                        <HorasChart rows={horasRows} hourValue={hourValue} highlight={movable.name} />
                    </Card>
                ) : (
                    <AskIncome title="Cuántas horas de trabajo cuesta lo que compras" onAsk={() => setEditing(true)}>
                        Con tu ingreso, cada categoría se lee en horas de tu trabajo y no en pesos.
                    </AskIncome>
                )}

                <Card
                    title={growth ? `Tu gasto de segunda ${growth} desde ${monthName(first!.key, withYear)}` : "Tu gasto de segunda necesidad, mes a mes"}
                    foot={first ? `De ${mxn(first.segunda)} en ${monthName(first.key, withYear)} a ${mxn(peak.segunda)} en ${monthName(peak.key, withYear)}.` : ""}
                >
                    <SegundaChart months={reading.months} />
                </Card>

                <Card
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
            </div>

            <p className="text-label text-ash">
                Base: cargos de los últimos {SPAN_MONTHS} meses, sin «Entre mis cuentas» ni excluidos. Población: INEGI · ENIGH 2024, por hogar.
            </p>
        </div>
    );
}

/** A reading card: its title is the finding, its foot says what it means. The
 *  chart inside plays once, the first time the card is on screen. */
function Card({ title, foot, children }: { title: string; foot: ReactNode; children: ReactNode }) {
    const { ref, seen } = useReveal<HTMLElement>();
    return (
        <section ref={ref} data-play={seen} className="card flex min-w-0 flex-col">
            <h3 className="text-body-lg font-medium text-ink">{title}</h3>
            <div className="mt-5 flex-1">{children}</div>
            <p className="mt-5 border-t border-mist pt-4 text-body-sm text-graphite">{foot}</p>
        </section>
    );
}

/** The card a reading shows when it needs the income nobody has given yet. */
function AskIncome({ title, children, onAsk }: { title: string; children: ReactNode; onAsk: () => void }) {
    return (
        <section className="card flex min-w-0 flex-col">
            <h3 className="text-body-lg font-medium text-ink">{title}</h3>
            <p className="mt-3 flex-1 text-body-sm text-graphite">{children}</p>
            <div className="mt-5 border-t border-mist pt-4">
                <Button size="sm" variant="secondary" onClick={onAsk}>Agregar mi ingreso</Button>
            </div>
        </section>
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
                <>Sin ingreso todavía: tres lecturas lo necesitan · </>
            )}
            <button type="button" className="text-edge hover:underline" onClick={() => onEdit(true)}>
                {income ? "Cambiar" : "Agregar"}
            </button>
        </p>
    );
}

/** The reading's geometry before the reading: the title card, then the
 *  eight chart cards the grid draws, each with its title, its chart and its
 *  foot line. */
function EstadoSkeleton() {
    return (
        <div className="space-y-5" aria-busy>
            <section className="card space-y-4">
                <Skeleton className="h-9 w-80 max-w-full" />
                <Skeleton className="h-4 w-56" />
            </section>
            <div className="grid gap-5 lg:grid-cols-2">
                {Array.from({ length: 8 }).map((_, i) => (
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
