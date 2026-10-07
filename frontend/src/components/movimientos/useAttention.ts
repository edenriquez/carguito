"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AttentionItem } from "@/lib/api";
import type { WindowBounds } from "@/lib/window";

const DISMISSED_KEY = "carguito.attention.dismissed";

function readDismissed(): Set<string> {
    try {
        const raw = window.sessionStorage.getItem(DISMISSED_KEY);
        return new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
        return new Set();
    }
}

/**
 * The window's charges worth a second look, fetched alongside the
 * transactions with the same scope so every ring has a dot under it.
 * Failure is silent by design: a chart that cannot fetch its rings is a
 * chart without rings, not a broken chart — the movements still load.
 *
 * "Es mío" dismissals live for the session: the user answered, the ring
 * goes, and it does not come back on the next window change. A durable
 * "never again" is a later feature (it belongs on the transaction, not in
 * the browser).
 */
export function useAttention(
    bounds: WindowBounds,
    dataVersion: number,
    statementIds: string[] | null = null,
    enabled = true
) {
    const [items, setItems] = useState<AttentionItem[]>([]);
    const [dismissed, setDismissed] = useState<Set<string>>(() =>
        typeof window === "undefined" ? new Set() : readDismissed()
    );
    const { start, end } = bounds;
    const scopeKey = statementIds?.join("|") ?? "";

    useEffect(() => {
        if (!enabled) return;
        let stale = false;
        const params = new URLSearchParams();
        if (start) params.set("start", start);
        if (end) params.set("end", end);
        for (const id of statementIds ?? []) params.append("statement_id", id);
        api.attention(`?${params}`)
            .then((res) => {
                if (!stale) setItems(res.items);
            })
            .catch(() => {
                if (!stale) setItems([]);
            });
        return () => {
            stale = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [start, end, scopeKey, dataVersion, enabled]);

    const dismiss = useCallback((transactionId: string) => {
        setDismissed((cur) => {
            const next = new Set(cur).add(transactionId);
            try {
                window.sessionStorage.setItem(DISMISSED_KEY, JSON.stringify(Array.from(next)));
            } catch {
                // Private mode or a full store: the dismissal still holds in memory.
            }
            return next;
        });
    }, []);

    const visible = useMemo(
        () => items.filter((i) => !dismissed.has(i.transaction_id)),
        [items, dismissed]
    );

    return { items: visible, dismiss };
}
