"use client";

import { useSyncExternalStore } from "react";

/**
 * «Gráficas v2»: the alternate reading of every chart, from the expressive
 * chart audit of 6-oct-2026 — titles that state the finding, a focus by
 * default, partial months marked, one meaning for Signal, touch tooltips.
 *
 * A flag, not a fork: each chart keeps one component and branches on
 * `useChartsV2()` where v2 differs, so both readings run on the same data and
 * can be compared by flipping the switch. Once one wins, the flag and the
 * losing branch are deleted.
 *
 * On by default since 6-oct-2026 (v2 won). `?graficas=v1` turns it off and
 * `?graficas=v2` back on, persisted in localStorage, until the v1 branches
 * are deleted.
 */

const KEY = "tomin.charts.v2";
const listeners = new Set<() => void>();

function read(): boolean {
    try {
        return localStorage.getItem(KEY) !== "0";
    } catch {
        return true;
    }
}

export function setChartsV2(on: boolean): void {
    try {
        if (on) localStorage.removeItem(KEY);
        else localStorage.setItem(KEY, "0");
    } catch {
        // Storage blocked: the switch still flips for this page.
    }
    snapshot = on;
    listeners.forEach((l) => l());
}

let snapshot: boolean | null = null;

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function getSnapshot(): boolean {
    if (snapshot === null) {
        const param = new URLSearchParams(window.location.search).get("graficas");
        if (param === "v2" || param === "v1") setChartsV2(param === "v2");
        else snapshot = read();
    }
    return snapshot ?? true;
}

export function useChartsV2(): boolean {
    return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
