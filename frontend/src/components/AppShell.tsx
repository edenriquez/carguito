"use client";

import Link from "next/link";
import { Flame, FileText } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { useBankScope } from "@/lib/banks";
import { BankFilter } from "@/components/BankFilter";
import { PagosBell } from "@/components/pagos/PagosBell";
import { track } from "@/lib/telemetry";

/**
 * Wordmark, the one action that opens the ledger, and two overlays: the
 * payments bell and the archive.
 *
 * Nothing here navigates any more. Readings (por categoría, cargos
 * recurrentes) live in the page; Pagos and Documentos open on top of whatever
 * is being read instead of taking the user somewhere with no way back but the
 * browser. "Subir documento" used to sit here too — the loudest control in the
 * app, on every screen, for something done a handful of times a year. It now
 * lives inside Documentos, next to the list of what uploading produces.
 */
export function AppShell({
    children,
    instrument,
    pagos,
    documentos,
    dataVersion = 0,
}: {
    children: ReactNode;
    /** The commit that opens the ledger (⌘K). */
    instrument?: ReactNode;
    /** The bell's state and its opener. The modal itself is mounted by the
     *  chrome, inside the data context the calendar reads through. */
    pagos: { open: boolean; onOpen: () => void };
    /** The archive's state and its opener — same arrangement as the bell. */
    documentos: { open: boolean; onOpen: () => void };
    /** Bumped on every upload; the bank filter rereads its accounts on it. */
    dataVersion?: number;
}) {
    const scope = useBankScope(dataVersion);

    return (
        <main className="mx-auto min-h-dvh w-full max-w-page px-5 pb-16 sm:px-8">
            {/* Three columns from `sm` up, the outer two equal: the search sits
                on the page's true centre whatever the wordmark and the actions
                weigh. On a phone it drops to a row of its own under them. */}
            <header className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-3 py-6 sm:grid-cols-[1fr_auto_1fr] sm:py-8">
                <Link
                    href="/"
                    aria-label="Tomin, inicio"
                    className="flex items-center gap-2 justify-self-start text-ink"
                >
                    <Flame size={16} className="text-signal" aria-hidden />
                    <span className="text-body font-medium">Tomin</span>
                </Link>

                {instrument && (
                    <div className="order-last col-span-2 flex justify-center sm:order-none sm:col-span-1">
                        {instrument}
                    </div>
                )}

                <div className="flex items-center gap-1.5 justify-self-end sm:gap-2">
                    <PagosBell
                        dataVersion={dataVersion}
                        active={pagos.open}
                        onOpen={pagos.onOpen}
                    />
                    <button
                        type="button"
                        onClick={() => {
                            track("nav.view", { to: "/documentos", source: "header" });
                            documentos.onOpen();
                        }}
                        aria-haspopup="dialog"
                        aria-expanded={documentos.open}
                        title="Documentos"
                        className={cn(
                            "inline-flex h-9 items-center gap-2 rounded-control px-3 text-body",
                            "transition-colors duration-100",
                            documentos.open
                                ? "bg-fog font-medium text-ink ring-1 ring-inset ring-mist"
                                : "text-graphite hover:text-ink"
                        )}
                    >
                        <FileText size={15} aria-hidden />
                        <span className="hidden sm:inline">Documentos</span>
                    </button>
                </div>
            </header>

            <div className="-mt-2 flex flex-wrap items-center gap-2 pb-6">
                <BankFilter scope={scope} />
            </div>

            {children}
        </main>
    );
}
