"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ImagePlus, RotateCw, X } from "lucide-react";
import { cn } from "@/lib/cn";
import {
    isTicketImage,
    ticketMessage,
    uploadTicket,
    type ReceiptUploadResponse,
} from "@/lib/receipts";
import { track } from "@/lib/telemetry";
import { Button, useToast } from "@/components/ui";

// HEIC spelled out: `image/*` alone leaves iPhone photos greyed out in the
// picker on browsers that cannot decode them, even though this reader can.
const ACCEPT = "image/*,.heic,.heif";

/** What one photo is doing right now.
 *
 *  `preparing` is the browser decoding and shrinking the photo; `sending` is
 *  the bytes on the wire and has a real fraction; `reading` is the backend
 *  recognizing and structuring the ticket, which takes a couple of seconds
 *  and reports nothing, so the only honest bar is an indeterminate one. */
type Phase = "queued" | "preparing" | "sending" | "reading" | "done" | "error";

type Item = {
    id: string;
    name: string;
    file: File;
    phase: Phase;
    /** 0–1, bytes actually delivered. Only meaningful while `sending`. */
    read: number;
    result?: ReceiptUploadResponse;
    error?: string;
};

let seq = 0;
const nextId = () => `t${++seq}`;

/**
 * Upload tickets from the browser: a picker, a queue, and the rows.
 *
 * Same shape as the statement upload (`useStatementUpload`), for the same
 * reasons — many files one at a time, every outcome on the file's own row.
 * The photo is decoded and shrunk here, then read on the backend; the queue
 * is sequential so the rows stay legible and the backend reads one ticket at
 * a time.
 */
export function useTicketUpload(onAdded?: (result: ReceiptUploadResponse) => void) {
    const inputRef = useRef<HTMLInputElement>(null);
    const [queue, setQueue] = useState<Item[]>([]);
    const { toast } = useToast();
    const running = useRef(false);
    const handlers = useRef({ onAdded });
    handlers.current = { onAdded };

    const patch = useCallback((id: string, next: Partial<Item>) => {
        setQueue((cur) => cur.map((it) => (it.id === id ? { ...it, ...next } : it)));
    }, []);

    useEffect(() => {
        if (running.current) return;
        const next = queue.find((it) => it.phase === "queued");
        if (!next) return;
        running.current = true;
        void (async () => {
            patch(next.id, { phase: "preparing", read: 0, error: undefined });
            try {
                const result = await uploadTicket(next.file, (fraction) =>
                    // Once the bytes are gone the bar stops being the truth:
                    // hand over to `reading`, which claims nothing.
                    patch(
                        next.id,
                        fraction >= 1 ? { phase: "reading", read: 1 } : { phase: "sending", read: fraction }
                    )
                );
                patch(next.id, { phase: "done", read: 1, result });
                track("precios.ticket_upload", {
                    lines: result.receipt.items.length,
                    attached: result.attached,
                });
                handlers.current.onAdded?.(result);
            } catch (e) {
                patch(next.id, { phase: "error", error: ticketMessage(e) });
            } finally {
                running.current = false;
                setQueue((cur) => [...cur]);
            }
        })();
    }, [queue, patch]);

    const enqueue = useCallback((files: File[]) => {
        if (files.length === 0) return;
        setQueue((cur) => [
            // A new batch: rows that already finished step aside so the list
            // is about the photos in hand.
            ...cur.filter((it) => it.phase !== "done" && it.phase !== "error"),
            ...files.map<Item>((file) => ({
                id: nextId(),
                name: file.name,
                file,
                read: 0,
                ...(isTicketImage(file)
                    ? { phase: "queued" as const }
                    : { phase: "error" as const, error: "Solo entran fotos: JPG, PNG, WebP o HEIC." }),
            })),
        ]);
    }, []);

    const retry = useCallback(
        (id: string) => patch(id, { phase: "queued", read: 0, error: undefined }),
        [patch]
    );
    const dismiss = useCallback(
        (id: string) => setQueue((cur) => cur.filter((it) => it.id !== id)),
        []
    );
    const pick = useCallback(() => inputRef.current?.click(), []);

    const busy = queue.some((it) => it.phase !== "done" && it.phase !== "error");

    // One toast per batch, when nothing is left in flight.
    const settledAt = useRef(0);
    useEffect(() => {
        const done = queue.filter((it) => it.phase === "done");
        if (busy || done.length === 0) {
            if (busy) settledAt.current = 0;
            return;
        }
        if (settledAt.current === done.length) return;
        settledAt.current = done.length;
        const lines = done.reduce((n, it) => n + (it.result?.receipt.items.length ?? 0), 0);
        toast(
            done.length === 1
                ? `Ticket leído: ${lines} línea${lines === 1 ? "" : "s"}`
                : `${done.length} tickets leídos · ${lines} líneas`,
            "positive"
        );
    }, [queue, busy, toast]);

    const input = (
        <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(e) => {
                enqueue(Array.from(e.target.files ?? []));
                // Without this, re-selecting the same photo fires no change.
                e.target.value = "";
            }}
        />
    );

    return { pick, enqueue, queue, retry, dismiss, busy, input };
}

/** The one button that opens the picker. Secondary: the primary on this
 *  screen is the reading, not the intake. */
export function TicketUploadButton({
    onPick,
    busy,
    variant = "secondary",
    className,
}: {
    onPick: () => void;
    busy: boolean;
    variant?: "primary" | "secondary";
    className?: string;
}) {
    return (
        <Button
            variant={variant}
            size="sm"
            loading={busy}
            onClick={onPick}
            icon={<ImagePlus size={15} />}
            className={cn("text-ink", className)}
        >
            Subir ticket
        </Button>
    );
}

/**
 * The photos in flight, one row each. The bar is the recognizer's own
 * progress while it reads, then an indeterminate sweep for the send. A
 * finished row says what came out — the store and how many lines — because
 * that is the only fact the user wanted from the upload. Failures stay on
 * their row, with the recognizer's reason, until dismissed.
 */
export function TicketQueue({
    items,
    onRetry,
    onDismiss,
    className,
}: {
    items: Item[];
    onRetry: (id: string) => void;
    onDismiss: (id: string) => void;
    className?: string;
}) {
    if (items.length === 0) return null;
    return (
        <ul className={cn("space-y-2", className)}>
            {items.map((item) => (
                <li
                    key={item.id}
                    className="rounded-input border border-mist bg-paper px-3 py-2 text-body-sm"
                >
                    <div className="flex items-center gap-3">
                        <span className="min-w-0 flex-1 truncate text-ink" title={item.name}>
                            {item.name}
                        </span>
                        <span
                            className={cn(
                                "shrink-0",
                                item.phase === "error" ? "text-negative" : "text-graphite"
                            )}
                        >
                            {label(item)}
                        </span>
                        {item.phase === "error" && (
                            <button
                                type="button"
                                onClick={() => onRetry(item.id)}
                                aria-label="Reintentar"
                                title="Reintentar"
                                className="rounded-control p-1 text-ash hover:bg-fog hover:text-ink"
                            >
                                <RotateCw size={14} aria-hidden />
                            </button>
                        )}
                        {(item.phase === "done" || item.phase === "error") && (
                            <button
                                type="button"
                                onClick={() => onDismiss(item.id)}
                                aria-label="Quitar"
                                title="Quitar"
                                className="rounded-control p-1 text-ash hover:bg-fog hover:text-ink"
                            >
                                <X size={14} aria-hidden />
                            </button>
                        )}
                    </div>
                    {(item.phase === "preparing" ||
                        item.phase === "sending" ||
                        item.phase === "reading") && (
                        <div
                            role="progressbar"
                            aria-valuemin={0}
                            aria-valuemax={1}
                            aria-valuenow={item.phase === "sending" ? item.read : undefined}
                            className="mt-2 h-1 overflow-hidden rounded-full bg-fog"
                        >
                            <div
                                className={cn(
                                    "h-full rounded-full bg-soot transition-[width] duration-200",
                                    item.phase !== "sending" && "animate-pulse"
                                )}
                                style={{
                                    width: `${Math.round((item.phase === "sending" ? item.read : 1) * 100)}%`,
                                }}
                            />
                        </div>
                    )}
                </li>
            ))}
        </ul>
    );
}

function label(item: Item): string {
    switch (item.phase) {
        case "queued":
            return "En espera";
        case "preparing":
            return "Preparando la foto…";
        case "sending":
            return `Subiendo · ${Math.round(item.read * 100)}%`;
        case "reading":
            return "Leyendo el ticket…";
        case "error":
            return item.error ?? "No se pudo";
        case "done": {
            const r = item.result;
            if (!r) return "Listo";
            const n = r.receipt.items.length;
            const where = r.receipt.store ? `${r.receipt.store} · ` : "";
            const tie = r.attached ? "ligado a un cargo" : "sin cargo ligado";
            return `${where}${n} línea${n === 1 ? "" : "s"} · ${tie}`;
        }
    }
}
