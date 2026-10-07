"use client";

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode,
    type RefObject,
} from "react";
import { track } from "@/lib/telemetry";
import { EMPTY_QUERY, type MovimientosQuery } from "@/lib/movimientosQuery";

/**
 * The movimientos modal's open state and the criteria it commits on close.
 *
 * Lives above the routes so ⌘K works from Categorías or Plan, and so a
 * filter set on one face is still there when the user comes back. Date is
 * not stored here — it is the TimeWindow, written on close.
 */
type Api = {
    open: boolean;
    /** `seed` is the draft the modal must open on — setQuery alone can
     *  lose the race with the open flag. `seedGen` bumps so the modal
     *  effect re-runs even when the overlay was already open. */
    openModal: (source?: string, seed?: MovimientosQuery, opts?: OpenOptions) => void;
    closeModal: () => void;
    query: MovimientosQuery;
    setQuery: (next: MovimientosQuery) => void;
    seedGen: number;
    /** The modal was opened as a look at one category: its criterios stay in
     *  the modal, and closing leaves the faces' query as it was. */
    transient: boolean;
    /** Same-render seed for the modal draft. A ref can miss the first paint. */
    openingSeed: MovimientosQuery | null;
    searchInputRef: RefObject<HTMLInputElement>;
};

type OpenOptions = {
    /** Filter the modal only. Picking a category on a chart is a question
     *  about that category, not a decision to narrow every chart — so the
     *  seed is not written to the shared query, and closing commits nothing
     *  but explicit date edits. */
    transient?: boolean;
};

const Ctx = createContext<Api | null>(null);

export function useMovimientosSearch(): Api {
    const ctx = useContext(Ctx);
    if (!ctx) {
        throw new Error("useMovimientosSearch must be used inside <MovimientosSearchProvider>");
    }
    return ctx;
}

export function MovimientosSearchProvider({ children }: { children: ReactNode }) {
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState<MovimientosQuery>(EMPTY_QUERY);
    const [seedGen, setSeedGen] = useState(0);
    const [openingSeed, setOpeningSeed] = useState<MovimientosQuery | null>(null);
    const [transient, setTransient] = useState(false);
    const searchInputRef = useRef<HTMLInputElement>(null);

    const openModal = useCallback(
        (source = "unknown", seed?: MovimientosQuery, opts?: OpenOptions) => {
            const isTransient = Boolean(seed && opts?.transient);
            setOpeningSeed(seed ?? null);
            // A bare re-open (⌘K while open) keeps whatever mode is running.
            if (seed) setTransient(isTransient);
            if (seed && !isTransient) setQuery(seed);
            setSeedGen((n) => n + 1);
            setOpen((was) => {
                if (was) {
                    searchInputRef.current?.focus();
                    return was;
                }
                if (!seed) setTransient(false);
                track("movimientos.modal_open", { source });
                return true;
            });
        },
        []
    );

    const closeModal = useCallback(() => {
        setOpeningSeed(null);
        setTransient(false);
        setOpen(false);
    }, []);

    useEffect(() => {
        function onKey(e: KeyboardEvent) {
            if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "k") return;
            e.preventDefault();
            openModal(e.metaKey ? "cmdk" : "ctrlk");
        }
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [openModal]);

    const value = useMemo<Api>(
        () => ({
            open,
            openModal,
            closeModal,
            query,
            setQuery,
            seedGen,
            transient,
            openingSeed,
            searchInputRef,
        }),
        [open, openModal, closeModal, query, seedGen, transient, openingSeed]
    );

    return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
