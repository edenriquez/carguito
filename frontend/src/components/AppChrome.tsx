"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { track } from "@/lib/telemetry";
import { AppShell } from "@/components/AppShell";
import { LecturaHost } from "@/components/lectura/LecturaHost";
import { DocumentosModal } from "@/components/documentos/DocumentosModal";
import { MovimientosModal } from "@/components/movimientos/MovimientosModal";
import { PagosModal } from "@/components/pagos/PagosModal";
import {
    MovimientosQueryChips,
    MovimientosSearchTrigger,
} from "@/components/movimientos/MovimientosSearchTrigger";
import { useTimeWindow } from "@/components/TimeWindowProvider";
import type { Period } from "@/lib/metrics";
import type { TimeWindow, WindowBounds } from "@/lib/window";

/**
 * The frame every view shares: shell, and the inputs a view reads its data
 * through. The time selection itself lives above the page, in
 * `TimeWindowProvider`; this only hands it down alongside the data version.
 *
 * Views read their inputs through `useAppData()` instead of threading props
 * from every page.
 */

type AppData = {
    /** Bumped after each upload; views key their fetches on it. */
    dataVersion: number;
    /** Force every view to refetch — used after an edit inside the modal. */
    refresh: () => void;
    /** The selected span, as a value and in the shapes each API wants. */
    window: TimeWindow;
    /** Changes exactly when the selection does — the dependency to key on. */
    windowKey: string;
    bounds: WindowBounds;
    period: Period;
    grain: "day" | "month";
};

const AppDataContext = createContext<AppData | null>(null);

export function useAppData(): AppData {
    const ctx = useContext(AppDataContext);
    if (!ctx) throw new Error("useAppData must be used inside <AppChrome>");
    return ctx;
}

export function AppChrome({
    children,
    withWindow = false,
    onDataChanged,
}: {
    children: ReactNode;
    /** Whether this view reads through the time filter. Off for views that
     *  read the whole history (Plan, Precios) or manage the archive
     *  (Documentos); the bar still shows, and says it does not apply. */
    withWindow?: boolean;
    onDataChanged?: () => void;
}) {
    const [dataVersion, setDataVersion] = useState(0);
    const [pagosOpen, setPagosOpen] = useState(false);
    const [documentosOpen, setDocumentosOpen] = useState(false);
    const refresh = useCallback(() => setDataVersion((v) => v + 1), []);
    const tw = useTimeWindow();
    const pathname = usePathname();
    // Held in a ref so the callback the archive modal keeps does not change
    // identity on every render of the page above it.
    const onDataChangedRef = useRef(onDataChanged);
    onDataChangedRef.current = onDataChanged;
    const uploaded = useCallback(() => {
        setDataVersion((v) => v + 1);
        onDataChangedRef.current?.();
    }, []);

    // Every view, on arrival, with the context it is read under. `nav.view`
    // records the click; this records the landing — direct loads, redirects
    // from retired paths, deep links — so the per-view counts are complete.
    useEffect(() => {
        track("view.open", {
            path: pathname,
            time_scoped: withWindow,
            window: tw.window.kind === "preset" ? tw.window.id : "custom",
        });
        // Only the path: a window change is `window.select`, not a new view.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pathname]);

    // The newest transaction on record is where the rolling presets end. Read
    // after every upload, because that is when it moves; a failed read leaves
    // the previous anchor (or today) in place rather than blanking the filter.
    useEffect(() => {
        let stale = false;
        api.transactionSpan()
            .then((span) => !stale && tw.setAnchor(span.last))
            .catch(() => undefined);
        return () => {
            stale = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dataVersion]);

    const value = useMemo<AppData>(
        () => ({
            dataVersion,
            refresh,
            window: tw.window,
            windowKey: tw.key,
            bounds: tw.bounds,
            period: tw.period,
            grain: tw.grain,
        }),
        [dataVersion, refresh, tw]
    );

    return (
        <AppShell
            instrument={<MovimientosSearchTrigger />}
            dataVersion={dataVersion}
            pagos={{ open: pagosOpen, onOpen: () => setPagosOpen(true) }}
            documentos={{
                open: documentosOpen,
                onOpen: () => setDocumentosOpen(true),
            }}
        >
            <AppDataContext.Provider value={value}>
                {pathname === "/" && <MovimientosQueryChips />}
                {children}
                <MovimientosModal dataVersion={dataVersion} refresh={refresh} />
                <PagosModal open={pagosOpen} onClose={() => setPagosOpen(false)} />
                <DocumentosModal
                    open={documentosOpen}
                    onClose={() => setDocumentosOpen(false)}
                    onUploaded={uploaded}
                />
                <LecturaHost />
            </AppDataContext.Provider>
        </AppShell>
    );
}
