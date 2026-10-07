"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Transaction } from "@/lib/api";
import { clusterIncome } from "@/lib/ingresos";
import { monthKeyOf, type MonthKey } from "@/lib/porMes";
import { useIngresos } from "@/components/pronostico/useIngresos";

const DECLARED_KEY = "carguito.lectura.ingreso";

export type IngresoSource = "declarado" | "etiquetado" | null;

function readDeclared(): number | null {
    try {
        const raw = window.localStorage.getItem(DECLARED_KEY);
        const n = raw === null ? NaN : Number(raw);
        return Number.isFinite(n) && n > 0 ? n : null;
    } catch {
        return null;
    }
}

/**
 * What comes in each month, for the readings that compare against it.
 *
 * A figure the user typed wins: it is the one they chose. Otherwise the
 * deposits they labeled nómina or extra in Plan, summed over the span and
 * spread over the months that hold cargos — the same months the spend
 * average is taken over, so the two are comparable. Nothing is inferred from
 * unlabeled deposits: a préstamo is not income until someone says so.
 */
export function useIngresoMensual(items: Transaction[] | null, keys: MonthKey[]) {
    const { state, hydrated } = useIngresos();
    const [declared, setDeclaredState] = useState<number | null>(null);

    useEffect(() => {
        setDeclaredState(readDeclared());
    }, []);

    const labeled = useMemo(() => {
        if (!items || !hydrated || state.labeled.length === 0) return null;
        const span = new Set(keys);
        const labeledKeys = new Set(state.labeled.map((l) => l.key));
        const inSpan = items.filter((t) => span.has(monthKeyOf(t.date)));
        const total = clusterIncome(inSpan)
            .filter((c) => labeledKeys.has(c.key))
            .reduce((s, c) => s + c.txs.reduce((a, t) => a + Math.abs(t.amount), 0), 0);
        const months = new Set(
            inSpan.filter((t) => t.type === "expense").map((t) => monthKeyOf(t.date))
        ).size;
        return total > 0 && months > 0 ? total / months : null;
    }, [items, hydrated, state.labeled, keys]);

    const setDeclared = useCallback((value: number | null) => {
        setDeclaredState(value);
        try {
            if (value === null) window.localStorage.removeItem(DECLARED_KEY);
            else window.localStorage.setItem(DECLARED_KEY, String(Math.round(value)));
        } catch {
            // Private mode: the figure still holds for this visit.
        }
    }, []);

    const income = declared ?? labeled;
    const source: IngresoSource = declared !== null ? "declarado" : labeled !== null ? "etiquetado" : null;
    return { income, source, labeled, setDeclared };
}
