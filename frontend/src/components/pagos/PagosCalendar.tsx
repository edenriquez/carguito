"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { RecurringItem } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui";
import { dayLabel, fullDayLabel, mxn } from "@/lib/format";
import { today } from "@/components/recurrentes/projection";
import {
    buildDueMonth,
    isoOf,
    shiftMonth,
    startOfMonth,
    withCardPayment,
    type CardPayment,
    type DayCell,
    type DueLine,
} from "./dueMonth";

const WEEKDAYS = ["L", "M", "M", "J", "V", "S", "D"] as const;

const FREQUENCY: Record<RecurringItem["frequency"], string> = {
    weekly: "semanal",
    biweekly: "quincenal",
    monthly: "mensual",
    bimonthly: "bimestral",
    semiannual: "semestral",
    yearly: "anual",
};

/** How far back the month can be turned: a year of landed charges. */
const BACK_MONTHS = 12;

/**
 * One month, and the day you are looking at.
 *
 * The grid is a calendar and nothing more: Monday first, today filled, a dot
 * under every day that has a charge, the chosen day ringed. No pulse, no
 * ramp from red to blue — what is due is a date and an amount, and both are
 * written in the column beside the grid, where words go. Red is the colour
 * of money leaving in a ledger, not of a Tuesday.
 *
 * The column is the month on the grid, in ink, and under it a shaded preview
 * of the month after — one block, labelled as next month, that turns both
 * when pressed. Off the current month, the heading offers the way back.
 */
export function PagosCalendar({
    items,
    card,
}: {
    items: RecurringItem[];
    card: CardPayment | null;
}) {
    const [offset, setOffset] = useState(0);
    const [picked, setPicked] = useState<string | null>(null);

    const now = today();
    const month = shiftMonth(startOfMonth(now), offset);
    // One build per month the column can show. The grid and the list read
    // the same one, so turning never reveals a different set of payments.
    const months = useMemo(() => {
        const at = (delta: number) => monthLines(items, shiftMonth(month, delta), card);
        return { current: at(0), next: at(1) };
    }, [items, month, card]);
    const view = months.current.view;

    // The day the column opens on: the one you picked, else the next charge
    // still ahead in this month, else today when the month is the current one.
    const selected = useMemo(() => {
        if (picked && view.cells.some((w) => w.some((c) => c.iso === picked && !c.outside))) {
            return picked;
        }
        const next = view.dueThisMonth.find((l) => l.date >= now);
        if (next) return next.iso;
        return offset === 0 ? isoOf(now) : null;
    }, [picked, view, now, offset]);

    const canBack = offset > -(BACK_MONTHS - 1);
    const canForward = offset < 1;

    function turn(delta: number) {
        setOffset((cur) => {
            const next = cur + delta;
            if (next > 1 || next < -(BACK_MONTHS - 1)) return cur;
            return next;
        });
        setPicked(null);
    }

    function goToday() {
        setOffset(0);
        setPicked(null);
    }

    return (
        <div className="grid gap-8 md:grid-cols-[minmax(0,56fr)_minmax(0,44fr)]">
            <div>
                <div className="flex items-center justify-between">
                    <MonthChevron direction="back" disabled={!canBack} onClick={() => turn(-1)} />
                    <p className="text-body-sm font-medium text-ink">{monthTitle(month)}</p>
                    <MonthChevron direction="forward" disabled={!canForward} onClick={() => turn(1)} />
                </div>

                <div className="mt-3 grid grid-cols-7 text-center">
                    {WEEKDAYS.map((d, i) => (
                        <span key={`${d}-${i}`} className="py-1 text-label text-ash">
                            {d}
                        </span>
                    ))}
                    {view.cells.flat().map((cell) => (
                        <Day
                            key={cell.iso}
                            cell={cell}
                            selected={selected === cell.iso && !cell.outside}
                            onPick={() => setPicked(cell.iso)}
                        />
                    ))}
                </div>

                <Legend />
            </div>

            <div className="min-w-0 space-y-4">
                <MonthList
                    month={months.current.month}
                    lines={months.current.lines}
                    selected={selected}
                    home={offset === 0 ? null : startOfMonth(now)}
                    onHome={goToday}
                />
                {canForward && (
                    <NextMonth month={months.next.month} lines={months.next.lines} onOpen={() => turn(1)} />
                )}
            </div>
        </div>
    );
}

/** Under the grid, so the column beside it is matched by the grid and its
 *  key rather than leaving a blank under the dates. */
function Legend() {
    return (
        <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-label text-graphite">
            <li className="inline-flex items-center gap-1.5">
                <span aria-hidden className="h-2 w-2 rounded-full bg-ink" />
                Programado
            </li>
            <li className="inline-flex items-center gap-1.5">
                <span aria-hidden className="h-2 w-2 rounded-full bg-muted" />
                Registrado
            </li>
        </ul>
    );
}

function Day({
    cell,
    selected,
    onPick,
}: {
    cell: DayCell;
    selected: boolean;
    onPick: () => void;
}) {
    const hasDue = cell.due > 0 && !cell.outside;
    const hasReg = cell.registered > 0 && !cell.outside;
    const names = [...cell.dueLabels, ...cell.registeredLabels];
    const label = cell.outside
        ? undefined
        : `${fullDayLabel(cell.date)}${cell.today ? " · hoy" : ""}${
              hasDue ? ` · programado ${mxn(cell.due)}` : ""
          }${hasReg ? ` · registrado ${mxn(cell.registered)}` : ""}${
              names.length ? ` · ${names.join(", ")}` : ""
          }`;

    return (
        <button
            type="button"
            disabled={cell.outside}
            aria-label={label}
            aria-pressed={selected || undefined}
            onClick={onPick}
            className="flex h-10 flex-col items-center justify-start pt-1"
        >
            <span
                className={cn(
                    "tabular flex h-7 w-7 items-center justify-center rounded-full text-body-sm transition-colors duration-100",
                    cell.outside && "text-muted",
                    !cell.outside && cell.weekend && "text-graphite",
                    !cell.outside && !cell.weekend && "text-ink",
                    !cell.outside && !cell.today && !selected && "hover:bg-fog",
                    selected && !cell.today && "bg-mist text-ink",
                    cell.today && "bg-soot text-paper"
                )}
            >
                {cell.date.getDate()}
            </span>
            {/* One dot, whichever kind of charge the day holds: a projected one
                in Ink, a landed one in Muted. A day with both shows the one
                still ahead — that is the one that can still be acted on. */}
            {(hasDue || hasReg) && (
                <span
                    aria-hidden
                    className={cn("mt-0.5 h-1 w-1 rounded-full", hasDue ? "bg-ink" : "bg-muted")}
                />
            )}
        </button>
    );
}

/** The grid's month step. */
function MonthChevron({
    direction,
    disabled,
    onClick,
}: {
    direction: "back" | "forward";
    disabled: boolean;
    onClick: () => void;
}) {
    const Icon = direction === "back" ? ChevronLeft : ChevronRight;
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            aria-label={direction === "back" ? "Mes anterior" : "Mes siguiente"}
            className="rounded-control p-1 text-ash transition-colors duration-100 hover:bg-fog hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
        >
            <Icon size={16} aria-hidden />
        </button>
    );
}

/**
 * The month on the grid, in ink. Off the current month, the heading carries
 * the way back to it — the grid's chevrons step one month, this one returns.
 */
function MonthList({
    month,
    lines,
    selected,
    home,
    onHome,
}: {
    month: Date;
    lines: DueLine[];
    selected: string | null;
    /** The current month, when the grid has been turned away from it. */
    home: Date | null;
    onHome: () => void;
}) {
    return (
        <section>
            <div className="flex min-h-8 items-center justify-between gap-3">
                <p className="truncate text-body font-medium text-ink">{monthHeading(month)}</p>
                {home && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={onHome}
                        icon={<ChevronLeft size={14} aria-hidden />}
                        className="-mr-3 shrink-0"
                    >
                        Volver a {monthHeading(home).toLowerCase()}
                    </Button>
                )}
            </div>
            <ul className="mt-1 divide-y divide-mist border-b border-mist">
                {lines.length === 0 ? (
                    <li className="py-3 text-body-sm text-graphite">Nada en este mes.</li>
                ) : (
                    lines.map((line) => (
                        <li key={line.key}>
                            <Row line={line} marked={selected === line.iso} />
                        </li>
                    ))
                )}
            </ul>
        </section>
    );
}

/**
 * The month after, as a preview: its rows shaded, its heading saying "next
 * month", and the whole block one target that turns the grid to it. The
 * hover is a soft panel inset past the rows' edges rather than a fill on
 * each row, so it reads as one object being picked up.
 */
function NextMonth({ month, lines, onOpen }: { month: Date; lines: DueLine[]; onOpen: () => void }) {
    const name = monthHeading(month);
    return (
        <button
            type="button"
            onClick={onOpen}
            aria-label={`Mes siguiente, ${name}`}
            className="group -mx-3 block w-[calc(100%+1.5rem)] rounded-card px-3 pb-1 pt-2 text-left transition-colors duration-150 ease-out hover:bg-fog"
        >
            <span className="flex min-h-6 items-center justify-between gap-3">
                <span className="truncate text-body font-medium text-graphite transition-colors duration-150 group-hover:text-ink">
                    {name}
                </span>
                <span className="inline-flex shrink-0 items-center gap-0.5 text-label text-ash transition-colors duration-150 group-hover:text-ink">
                    Mes siguiente
                    <ChevronRight
                        size={14}
                        aria-hidden
                        className="transition-transform duration-150 ease-out group-hover:translate-x-0.5"
                    />
                </span>
            </span>
            <span className="mt-1 block divide-y divide-mist">
                {lines.length === 0 ? (
                    <span className="block py-3 text-body-sm text-ash">Nada programado.</span>
                ) : (
                    lines.map((line) => <Row key={line.key} line={line} quiet />)
                )}
            </span>
        </button>
    );
}

function Row({
    line,
    quiet,
    marked,
}: {
    line: DueLine;
    /** The month after: the same row, set back one step. */
    quiet?: boolean;
    /** The day chosen on the grid. */
    marked?: boolean;
}) {
    const landed = line.status === "registered";
    const tone = quiet || landed ? "text-graphite" : "text-ink";
    const amount = (
        <span className={cn("tabular shrink-0", quiet ? "text-body-sm" : "text-body", tone)}>
            {!landed && line.stable === false ? "~" : ""}
            {mxn(line.amount)}
        </span>
    );
    // A preview, so one line: what and when. The cadence is for the month
    // you are on.
    if (quiet) {
        return (
            <span className="flex min-h-9 items-center justify-between gap-3 py-1.5">
                <span className="flex min-w-0 items-baseline gap-2">
                    <span className={cn("truncate text-body-sm", tone)}>{line.label}</span>
                    <span className="shrink-0 text-label text-ash">{dayLabel(line.date)}</span>
                </span>
                {amount}
            </span>
        );
    }
    const meta = [
        dayLabel(line.date),
        landed ? "registrado" : line.frequency ? FREQUENCY[line.frequency] : null,
        !landed && line.stable === false ? "varía" : null,
    ]
        .filter(Boolean)
        .join(" · ");
    return (
        <span className="flex min-h-12 items-center justify-between gap-3 py-2">
            <span className="min-w-0">
                <span className={cn("block truncate text-body", tone, marked && "font-medium")}>{line.label}</span>
                {meta && <span className="block text-label text-ash">{meta}</span>}
            </span>
            {amount}
        </span>
    );
}

function monthLines(
    items: RecurringItem[],
    month: Date,
    card: CardPayment | null
): { month: Date; view: ReturnType<typeof buildDueMonth>; lines: DueLine[] } {
    const view = withCardPayment(buildDueMonth(items, month), card);
    const lines = [...view.registered, ...view.dueThisMonth].sort(
        (a, b) => a.date.getTime() - b.date.getTime() || a.label.localeCompare(b.label, "es-MX")
    );
    return { month, view, lines };
}

function monthTitle(date: Date): string {
    return date.toLocaleDateString("es-MX", { month: "long", year: "numeric" });
}

/** "Octubre" — the group heading on the column, beside the grid's full title. */
function monthHeading(date: Date): string {
    const name = date.toLocaleDateString("es-MX", { month: "long" });
    return name.charAt(0).toUpperCase() + name.slice(1);
}
