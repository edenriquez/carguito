"use client";

import { Suspense, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Upload, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button, Skeleton } from "@/components/ui";
import { useOverlay } from "@/components/ui/useOverlay";
import { usePortal } from "@/components/ui/usePortal";
import { useStatementUpload } from "@/components/StatementDropzone";
import { UploadQueue } from "@/components/onboarding/UploadQueue";
import { DocumentosView } from "./DocumentosView";

type Phase = "enter" | "open" | "leave";

/** How long the leave animation runs before the panel is unmounted. Must match
 *  `pagos-modal-out` in globals.css: cut it short and the modal blinks out. */
const LEAVE_MS = 190;
const REDUCED_LEAVE_MS = 60;

function prefersReducedMotion(): boolean {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The archive, over whatever you were reading — and the only place uploading
 * lives.
 *
 * It used to be split in two: a "Documentos" link that navigated away from the
 * reading, and a "Subir documento" button parked in the header of every screen
 * in the app. That button was the app's loudest control and the one a user
 * presses a handful of times a year, and it sat next to a link to the page
 * that shows what pressing it produced. So the two became one thing: the
 * archive opens on top of the reading, with uploading inside it, where the
 * result of the upload is already on screen.
 *
 * Motion and lifecycle follow the Pagos overlay exactly — same corner, same
 * growth, and the panel outlives `open` by one beat so closing is animated
 * too. The view inside reads `?statement=` (the deep link the phone hands out)
 * through `useSearchParams`, so it needs its own Suspense boundary; it is only
 * ever rendered while the modal is up, which keeps every prerendered route
 * that mounts this modal out of the bail-out.
 */
export function DocumentosModal({
    open,
    onClose,
    onUploaded,
}: {
    open: boolean;
    onClose: () => void;
    /** Fired after a successful upload, so the shell and every view refresh. */
    onUploaded?: () => void;
}) {
    const panelRef = useRef<HTMLDivElement>(null);
    const mounted = usePortal();
    const [render, setRender] = useState(false);
    const [phase, setPhase] = useState<Phase>("enter");
    const { pick, uploading, queue, retry, dismiss, clearSettled, input } =
        useStatementUpload(() => onUploaded?.());

    useOverlay(open, onClose, panelRef);

    if (open && !render) {
        setRender(true);
        setPhase("enter");
    }

    useLayoutEffect(() => {
        if (!render) return;
        if (open) {
            if (prefersReducedMotion()) {
                setPhase("open");
                return;
            }
            const settle = window.setTimeout(() => setPhase("open"), 300);
            return () => window.clearTimeout(settle);
        }
        setPhase("leave");
        const gone = window.setTimeout(
            () => setRender(false),
            prefersReducedMotion() ? REDUCED_LEAVE_MS : LEAVE_MS
        );
        return () => window.clearTimeout(gone);
    }, [open, render]);

    if (!mounted || !render) return null;

    return createPortal(
        <div className="fixed inset-0 z-modal flex items-center justify-center p-0 sm:p-6">
            <div
                onClick={onClose}
                aria-hidden
                className={cn(
                    "documentos-modal-scrim absolute inset-0 bg-soot/40",
                    phase === "enter" && "modal-enter",
                    phase === "leave" && "modal-leave",
                    phase === "open" && "is-open"
                )}
            />
            <div
                ref={panelRef}
                role="dialog"
                aria-modal="true"
                aria-label="Documentos"
                tabIndex={-1}
                className={cn(
                    "documentos-modal-panel relative flex h-dvh w-full flex-col overflow-hidden",
                    "bg-canvas outline-none sm:h-[min(860px,90dvh)] sm:max-w-[min(1080px,94vw)]",
                    "sm:rounded-panel sm:border sm:border-mist sm:shadow-float",
                    phase === "enter" && "modal-enter",
                    phase === "leave" && "modal-leave",
                    phase === "open" && "is-open"
                )}
            >
                <header className="flex shrink-0 items-start justify-between gap-4 border-b border-mist bg-paper px-5 py-4 sm:px-6">
                    <div className="min-w-0">
                        <h2 className="text-title-sm font-normal text-ink">Documentos</h2>
                        <p className="mt-0.5 text-body-sm text-graphite">
                            Cada PDF y XML que Carguito leyó. Aquí dices de qué cuenta viene
                            cada uno; si eliminas un documento, sus movimientos se van con
                            él.
                        </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                        <Button
                            variant="secondary"
                            loading={uploading}
                            onClick={() => {
                                clearSettled();
                                pick();
                            }}
                            icon={<Upload size={15} />}
                        >
                            <span className="hidden sm:inline">Subir documentos</span>
                            <span className="sm:hidden">Subir</span>
                        </Button>
                        <button
                            type="button"
                            onClick={onClose}
                            aria-label="Cerrar"
                            className="-mr-1 rounded-control p-1 text-graphite transition-colors duration-100 hover:bg-fog hover:text-ink"
                        >
                            <X size={18} />
                        </button>
                    </div>
                </header>

                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
                    {/* Above the archive, not inside it: the batch is what is
                        happening now, the list below is what is already kept. */}
                    <UploadQueue
                        items={queue}
                        onRetry={retry}
                        onDismiss={dismiss}
                        className="mb-5"
                    />
                    <Suspense
                        fallback={
                            <div className="space-y-4">
                                <Skeleton className="h-9 w-48" />
                                <Skeleton className="h-72" />
                            </div>
                        }
                    >
                        <DocumentosView embedded />
                    </Suspense>
                </div>
                {input}
            </div>
        </div>,
        document.body
    );
}
