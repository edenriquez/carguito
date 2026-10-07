"use client";

import { useMemo, useState } from "react";
import { ChevronRight, CircleDashed, RotateCw } from "lucide-react";
import type { AttentionKind, Transaction } from "@/lib/api";
import { LENS_KIND_LABELS } from "@/components/charts/lens/types";
import { cn } from "@/lib/cn";
import { useStatementBanks } from "@/lib/banks";
import {
    formatCategoryPath,
    useCategories,
    type CategoryInfo,
} from "@/lib/categories";
import { categoryIcon } from "@/lib/categoryIcons";
import { dayLabel, mxn2 } from "@/lib/format";
import { parsePeriodKey } from "@/lib/metrics";
import {
    pct,
    sliceColor,
    type CategorySlice,
    type SubGroup,
} from "@/lib/categoryComposition";

/**
 * One row per category; opening it shows what is inside, all the way down.
 *
 * Decisions worth keeping:
 *
 * - **Open is grey, not blue.** Signal marks the slice a widget is *about*;
 *   an open row is not a selection, it is a container with its lid off. The
 *   whole open block takes a Fog wash and heavier rules top and bottom, so
 *   the eye can see where the category starts and ends without counting
 *   indents.
 * - **Sin categoría is pinned, and it is the one row wearing Signal.** It is
 *   not a category, it is work: a Signal edge on the left, and the only
 *   button in the list.
 * - **Counts and shares at both levels.** The category says how many cargos
 *   it holds; each group says how many and what share *of that category* it
 *   is — the question at that depth is never "what share of everything".
 * - **The big subcategories open, the tail stays folded.** A category is
 *   opened to be read, but a category with nine subgroups opened flat is a
 *   wall. The groups that make up the first three quarters of it are shown
 *   in full; the rest wait as one line each, with their count and share on
 *   it, so nothing is hidden — only deferred.
 */
export function CategoryAccordion({
    slices,
    openKey,
    onToggle,
    onVerMas,
    attention,
    repeats,
    spend,
    movementCount,
    aux,
}: {
    slices: CategorySlice[];
    openKey: string | null;
    onToggle: (key: string) => void;
    onVerMas: (key: string) => void;
    /** Charges the backend flagged, by transaction id. */
    attention: Map<string, AttentionKind>;
    /** Charges whose merchant repeats inside this reading. */
    repeats: Set<string>;
    spend: number;
    /** Everything in this list, the foot included — the cargos in the rows
     *  above plus the abonos and transfers below the rule. It is the same
     *  number the reading header states, and it has to stay that way. */
    movementCount: number;
    /** What sits below the rule at the foot: abonos, and what was set aside. */
    aux: {
        abonos: Transaction[];
        income: number;
        aparte: Transaction[];
        aparteTotal: number;
    };
}) {
    const categories = useCategories();
    const banks = useStatementBanks();
    const rows = { categories, banks, attention, repeats };

    return (
        <>
            <header className="flex items-center justify-between gap-3 border-b border-mist px-5 py-4 sm:px-6">
                <h2 className="flex items-baseline gap-2 text-title-sm font-normal text-ink">
                    Movimientos
                    <span className="tabular font-sans text-body-sm text-graphite">
                        {movementCount.toLocaleString("es-MX")}
                    </span>
                </h2>
                <span className="tabular shrink-0 text-body-sm text-graphite">
                    {mxn2(spend)} en cargos
                </span>
            </header>

            <ul className="divide-y divide-mist">
                {slices.map((s) => {
                    const open = openKey === s.key;
                    // The category's own taxonomy color, as in the bar.
                    const color = sliceColor(s, categories);
                    const Icon = s.uncategorized
                        ? CircleDashed
                        : categoryIcon(categories, s.key);
                    return (
                        // The open block is marked by a Fog wash over the
                        // whole li, not by a heavier outline: `divide-y` owns
                        // the border colour of these children, so a border on
                        // the row itself would lose to it anyway.
                        <li key={s.key} className={cn(open && "bg-fog/60")}>
                            <div
                                className={cn(
                                    "flex min-h-12 items-center gap-3 px-5 py-2.5 transition-colors duration-100 sm:px-6",
                                    open
                                        ? "border-b border-muted/70 bg-fog"
                                        : "hover:bg-fog/50",
                                    s.uncategorized &&
                                        !open &&
                                        "border-l-2 border-l-signal bg-fog/40",
                                    s.uncategorized && open && "border-l-2 border-l-signal"
                                )}
                            >
                                <button
                                    type="button"
                                    aria-expanded={open}
                                    onClick={() => onToggle(s.key)}
                                    className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                                >
                                    <ChevronRight
                                        size={16}
                                        aria-hidden
                                        className={cn(
                                            "shrink-0 transition-transform duration-150",
                                            open ? "rotate-90 text-graphite" : "text-ash"
                                        )}
                                    />
                                    <Icon
                                        size={16}
                                        strokeWidth={1.75}
                                        aria-hidden
                                        className="shrink-0"
                                        style={{ color: s.uncategorized ? undefined : color }}
                                    />
                                    <span className="min-w-0 truncate text-body font-medium text-ink">
                                        {s.name}
                                    </span>
                                    <Count n={s.count} noun={s.uncategorized ? "movimiento" : "cargo"} />
                                </button>

                                <div className="flex shrink-0 items-center gap-3 sm:gap-4">
                                    {s.uncategorized ? (
                                        <>
                                            <span className="tabular w-24 text-right text-body font-medium text-ink sm:w-28">
                                                {mxn2(s.amount)}
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => onVerMas(s.key)}
                                                className="rounded-control border border-signal px-2.5 py-0.5 text-label font-medium text-ink transition-colors duration-100 hover:bg-wash/40"
                                            >
                                                Revisar {s.count}
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <span className="hidden h-1.5 w-28 overflow-hidden rounded-full bg-mist sm:block lg:w-40">
                                                <span
                                                    className="block h-full rounded-full"
                                                    style={{
                                                        width: `${Math.max(pct(s.share), 2)}%`,
                                                        background: color,
                                                    }}
                                                />
                                            </span>
                                            <span
                                                className={cn(
                                                    "tabular w-10 text-right text-body-sm",
                                                    open
                                                        ? "font-medium text-edge"
                                                        : "text-graphite"
                                                )}
                                            >
                                                {pct(s.share)}%
                                            </span>
                                            <span className="tabular w-24 text-right text-body font-medium text-ink sm:w-28">
                                                {mxn2(s.amount)}
                                            </span>
                                        </>
                                    )}
                                </div>
                            </div>

                            {open && (
                                <>
                                    {s.groups.length === 0 ? (
                                        <p className="px-5 py-4 text-body-sm text-graphite sm:px-6">
                                            Sin cargos en este grupo.
                                        </p>
                                    ) : (
                                        <Groups groups={s.groups} rows={rows} />
                                    )}
                                    <div className="flex justify-end border-t border-muted/70 px-5 py-2 sm:px-6">
                                        <button
                                            type="button"
                                            onClick={() => onVerMas(s.key)}
                                            className="rounded-control px-2 py-1 text-body-sm text-graphite underline decoration-mist underline-offset-4 transition-colors duration-100 hover:text-ink"
                                        >
                                            Ver en transacciones
                                        </button>
                                    </div>
                                </>
                            )}
                        </li>
                    );
                })}
            </ul>

            <AuxSection {...aux} rows={rows} />
        </>
    );
}

type RowContext = {
    categories: Map<string, CategoryInfo> | null;
    banks: Map<string, string>;
    attention: Map<string, AttentionKind>;
    repeats: Set<string>;
};

/** How much of a category is shown expanded before the tail folds into
 *  one-line rows. Three quarters: enough that the reading answers "what is
 *  this category made of" without unrolling its long tail. */
const OPEN_UNTIL = 0.75;

/** The subcategories of one open category, indented under it. */
function Groups({ groups, rows }: { groups: SubGroup[]; rows: RowContext }) {
    // The tail is folded by default, not hidden: which groups start open is
    // decided once per category, from its shape, and the user's clicks after
    // that are theirs to keep.
    const initial = useMemo(() => {
        const open = new Set<string>();
        let acc = 0;
        for (const g of groups) {
            if (open.size > 0 && acc >= OPEN_UNTIL) break;
            open.add(g.key);
            acc += g.share;
        }
        return open;
    }, [groups]);
    const [opened, setOpened] = useState<Set<string>>(initial);

    function toggle(key: string) {
        setOpened((cur) => {
            const next = new Set(cur);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    }

    return (
        <div className="space-y-4 py-3 pl-7 pr-5 sm:pl-12 sm:pr-6">
            {groups.map((g) =>
                opened.has(g.key) ? (
                    <section key={g.key}>
                        <header className="flex items-baseline justify-between gap-3 border-b border-muted/70 pb-1.5">
                            <button
                                type="button"
                                onClick={() => toggle(g.key)}
                                className="flex min-w-0 items-baseline gap-x-1.5 text-left"
                            >
                                <span className="truncate text-body-sm font-medium text-ink">
                                    {g.name}
                                </span>
                                <GroupMeta group={g} />
                            </button>
                            <span className="tabular shrink-0 text-body-sm font-medium text-ink">
                                {mxn2(g.amount)}
                            </span>
                        </header>
                        <ul className="divide-y divide-mist">
                            {g.charges.map((t) => (
                                <ChargeRow key={t.id} t={t} rows={rows} />
                            ))}
                        </ul>
                    </section>
                ) : (
                    <button
                        key={g.key}
                        type="button"
                        onClick={() => toggle(g.key)}
                        className="flex w-full items-center justify-between gap-3 border-t border-muted/50 py-1.5 text-left transition-colors duration-100 hover:text-ink"
                    >
                        <span className="flex min-w-0 items-baseline gap-1.5">
                            <ChevronRight
                                size={14}
                                aria-hidden
                                className="shrink-0 translate-y-0.5 text-ash"
                            />
                            <span className="truncate text-body-sm text-graphite">
                                {g.name}
                            </span>
                            <GroupMeta group={g} />
                        </span>
                        <span className="tabular shrink-0 text-body-sm text-ink">
                            {mxn2(g.amount)}
                        </span>
                    </button>
                )
            )}
        </div>
    );
}

function GroupMeta({ group }: { group: SubGroup }) {
    return (
        <span className="tabular whitespace-nowrap text-label font-normal text-ash">
            · {group.count.toLocaleString("es-MX")} cargo
            {group.count === 1 ? "" : "s"} · {pct(group.share)}% del grupo
        </span>
    );
}

/** "· 16 cargos". Quiet enough to sit beside a name without competing. */
function Count({ n, noun = "cargo" }: { n: number; noun?: string }) {
    return (
        <span className="tabular shrink-0 whitespace-nowrap text-label text-ash">
            · {n.toLocaleString("es-MX")} {noun}
            {n === 1 ? "" : "s"}
        </span>
    );
}

function ChargeRow({ t, rows }: { t: Transaction; rows: RowContext }) {
    const { categories, banks, attention, repeats } = rows;
    const path = formatCategoryPath(categories, t.category_id);
    const bank = t.statement_id ? banks.get(t.statement_id) : undefined;
    const d = parsePeriodKey(t.date);
    const flag = attention.get(t.id);

    return (
        <li className="flex min-h-14 items-center gap-3 py-2">
            <Initial label={t.description} />
            <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                    <span className="truncate text-body-sm text-ink">{t.description}</span>
                    {flag && <FlagTag kind={flag} />}
                    {repeats.has(t.id) && (
                        <RotateCw
                            size={12}
                            aria-label="Se repite en este periodo"
                            className="shrink-0 text-ash"
                        />
                    )}
                </span>
                <span className="tabular block text-label text-ash">
                    {d ? dayLabel(d) : t.date}
                    {bank ? ` · ${bank}` : ""}
                </span>
            </span>
            {path !== "Sin categoría" && (
                <span className="hidden shrink-0 rounded-input bg-fog px-2.5 py-0.5 text-label text-graphite md:inline">
                    {path}
                </span>
            )}
            <span
                className={cn(
                    "tabular w-20 shrink-0 text-right text-body-sm sm:w-24",
                    t.type === "income" ? "text-positive" : "text-ink"
                )}
            >
                {t.type === "income" ? "+" : ""}
                {mxn2(t.amount)}
            </span>
        </li>
    );
}

/** The reading, off the chart: a hairline tag in the accent, one word. Signal
 *  is a border here, never text on light — the label stays Ink. */
function FlagTag({ kind }: { kind: AttentionKind }) {
    const word = {
        unusual_amount: "inusual",
        possible_duplicate: "duplicado",
        new_merchant: "nuevo",
    }[kind];
    return (
        <span
            title={LENS_KIND_LABELS[kind]}
            className="shrink-0 rounded-tag border border-signal px-1.5 py-px text-caption font-medium uppercase text-ink"
        >
            {word}
        </span>
    );
}

/** The merchant's first letter, so a long list of amounts keeps a left edge. */
function Initial({ label }: { label: string }) {
    const letter = (label.match(/\p{L}|\p{N}/u)?.[0] ?? "?").toUpperCase();
    return (
        <span
            aria-hidden
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fog text-label font-medium text-graphite"
        >
            {letter}
        </span>
    );
}

/**
 * The quiet foot of the list: what came in, and what was set aside.
 *
 * Both are deliberately below a heavier rule and outside the percentages. An
 * abono is not a destination, and a transfer between your own accounts is not
 * spending — but leaving either off the screen entirely would make the list
 * disagree with the bank statement the user is holding.
 */
function AuxSection({
    abonos,
    income,
    aparte,
    aparteTotal,
    rows,
}: {
    abonos: Transaction[];
    income: number;
    aparte: Transaction[];
    aparteTotal: number;
    rows: RowContext;
}) {
    const [open, setOpen] = useState<string | null>(null);
    if (abonos.length === 0 && aparte.length === 0) return null;

    return (
        <div className="border-t-2 border-muted bg-fog/30">
            {abonos.length > 0 && (
                <AuxRow
                    id="abonos"
                    label="Abonos"
                    count={abonos.length}
                    amount={mxn2(income)}
                    tone="positive"
                    open={open === "abonos"}
                    onToggle={() => setOpen((c) => (c === "abonos" ? null : "abonos"))}
                    charges={abonos}
                    rows={rows}
                />
            )}
            {aparte.length > 0 && (
                <AuxRow
                    id="aparte"
                    label="Entre mis cuentas"
                    count={aparte.length}
                    amount={mxn2(aparteTotal)}
                    tone="quiet"
                    open={open === "aparte"}
                    onToggle={() => setOpen((c) => (c === "aparte" ? null : "aparte"))}
                    charges={aparte}
                    rows={rows}
                />
            )}
        </div>
    );
}

function AuxRow({
    label,
    count,
    amount,
    tone,
    open,
    onToggle,
    charges,
    rows,
}: {
    id: string;
    label: string;
    count: number;
    amount: string;
    tone: "positive" | "quiet";
    open: boolean;
    onToggle: () => void;
    charges: Transaction[];
    rows: RowContext;
}) {
    return (
        <div className="border-t border-mist first:border-t-0">
            <button
                type="button"
                aria-expanded={open}
                onClick={onToggle}
                className="flex min-h-11 w-full items-center justify-between gap-3 px-5 py-2 text-left transition-colors duration-100 hover:bg-fog/60 sm:px-6"
            >
                <span className="flex min-w-0 items-center gap-2.5">
                    <ChevronRight
                        size={16}
                        aria-hidden
                        className={cn(
                            "shrink-0 transition-transform duration-150",
                            open ? "rotate-90 text-graphite" : "text-ash"
                        )}
                    />
                    <span className="truncate text-body-sm font-medium text-ink">{label}</span>
                    <span className="tabular shrink-0 text-label text-ash">· {count}</span>
                </span>
                <span
                    className={cn(
                        "tabular shrink-0 text-body-sm",
                        tone === "positive" ? "font-medium text-positive" : "text-graphite"
                    )}
                >
                    {tone === "positive" ? "+" : ""}
                    {amount}
                </span>
            </button>
            {open && (
                <ul className="divide-y divide-mist border-t border-mist px-5 sm:px-6">
                    {charges.map((t) => (
                        <ChargeRow key={t.id} t={t} rows={rows} />
                    ))}
                </ul>
            )}
        </div>
    );
}
