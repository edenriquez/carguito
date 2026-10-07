"use client";

import { FileText, RotateCw, X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { UploadItem } from "@/components/StatementDropzone";

/** "1.2 MB". Bank statements are KB-to-MB, so two steps is the whole range. */
function weight(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${Math.round(kb)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
}

/**
 * The batch in flight, one row per file.
 *
 * The bar answers a different question in each phase, and the row says which:
 * while the bytes go out it is a real fraction and reads as one; while the
 * backend parses there is no fraction to report, so the bar becomes an
 * indeterminate sweep rather than a number nobody measured. A finished row
 * keeps its result — how many movements came out of that document — because
 * that is the only number the user actually wanted from the upload.
 *
 * Failures stay on their own row instead of becoming a toast: with six files
 * a toast cannot say which one was a .docx, or which PDF wanted a password.
 */
export function UploadQueue({
    items,
    onRetry,
    onDismiss,
    className,
}: {
    items: UploadItem[];
    onRetry: (id: string) => void;
    onDismiss: (id: string) => void;
    className?: string;
}) {
    if (items.length === 0) return null;

    const pending = items.filter(
        (i) => i.phase === "queued" || i.phase === "sending" || i.phase === "reading"
    ).length;

    return (
        <div className={cn("text-left", className)}>
            <p className="mb-2 text-body-sm text-graphite">
                {pending > 0
                    ? `${pending} ${pending === 1 ? "documento" : "documentos"} en proceso…`
                    : `${items.length} ${items.length === 1 ? "documento" : "documentos"}`}
            </p>
            <ul className="space-y-2">
                {items.map((item) => (
                    <Row
                        key={item.id}
                        item={item}
                        onRetry={() => onRetry(item.id)}
                        onDismiss={() => onDismiss(item.id)}
                    />
                ))}
            </ul>
        </div>
    );
}

function Row({
    item,
    onRetry,
    onDismiss,
}: {
    item: UploadItem;
    onRetry: () => void;
    onDismiss: () => void;
}) {
    const failed = item.phase === "error";
    const done = item.phase === "done";

    return (
        <li
            className={cn(
                "flex items-center gap-3 rounded-card border bg-paper px-3 py-2.5",
                failed ? "border-negative/30" : "border-mist"
            )}
        >
            <span
                aria-hidden
                className={cn(
                    "grid h-8 w-8 shrink-0 place-items-center rounded-input border",
                    failed
                        ? "border-negative/30 text-negative"
                        : done
                          ? "border-mist text-positive"
                          : "border-mist text-graphite"
                )}
            >
                <FileText size={15} />
            </span>

            <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-3">
                    <span className="truncate text-body-sm text-ink">{item.name}</span>
                    <Status item={item} />
                </span>
                <span className="tabular mt-0.5 block text-label text-ash">
                    {weight(item.size)}
                    {item.error ? <span className="text-negative"> · {item.error}</span> : null}
                </span>
                <Bar item={item} />
            </span>

            <span className="flex shrink-0 items-center gap-1">
                {failed && item.file && (
                    <button
                        type="button"
                        onClick={onRetry}
                        aria-label={`Reintentar ${item.name}`}
                        title="Reintentar"
                        className="rounded-control p-1 text-graphite transition-colors duration-100 hover:bg-fog hover:text-ink"
                    >
                        <RotateCw size={14} />
                    </button>
                )}
                <button
                    type="button"
                    onClick={onDismiss}
                    aria-label={`Quitar ${item.name} de la lista`}
                    className="rounded-control p-1 text-ash transition-colors duration-100 hover:bg-fog hover:text-ink"
                >
                    <X size={14} />
                </button>
            </span>
        </li>
    );
}

/** The right-hand word or number. A percentage only while one is measured. */
function Status({ item }: { item: UploadItem }) {
    if (item.phase === "queued") {
        return <span className="shrink-0 text-label text-ash">En fila</span>;
    }
    if (item.phase === "sending") {
        return (
            <span className="tabular shrink-0 text-label text-graphite">
                {Math.round(item.sent * 100)}%
            </span>
        );
    }
    if (item.phase === "reading") {
        return <span className="shrink-0 text-label text-graphite">Leyendo…</span>;
    }
    if (item.phase === "password") {
        return <span className="shrink-0 text-label text-edge">Pide contraseña</span>;
    }
    if (item.phase === "error") {
        return <span className="shrink-0 text-label text-negative">No se pudo</span>;
    }
    const n = item.result?.transactions_created ?? 0;
    const skipped = item.result?.transactions_skipped ?? 0;
    // A re-upload of a period already in the ledger: say how much was new,
    // or "0 movimientos" reads as a failed parse.
    if (skipped > 0) {
        return (
            <span className="tabular shrink-0 text-label text-positive">
                {n.toLocaleString("es-MX")} nuevo{n === 1 ? "" : "s"}
                <span className="text-graphite">
                    {" "}· {skipped.toLocaleString("es-MX")} ya estaba{skipped === 1 ? "" : "n"}
                </span>
            </span>
        );
    }
    return (
        <span className="tabular shrink-0 text-label text-positive">
            {n.toLocaleString("es-MX")} movimiento{n === 1 ? "" : "s"}
        </span>
    );
}

function Bar({ item }: { item: UploadItem }) {
    if (item.phase === "error" || item.phase === "password") return null;

    if (item.phase === "reading") {
        return (
            <span
                aria-hidden
                className="mt-1.5 block h-1 overflow-hidden rounded-full bg-mist"
            >
                <span className="upload-bar-sweep block h-full w-1/3 rounded-full bg-signal" />
            </span>
        );
    }

    const width = item.phase === "done" ? 100 : Math.round(item.sent * 100);
    return (
        <span aria-hidden className="mt-1.5 block h-1 overflow-hidden rounded-full bg-mist">
            <span
                className={cn(
                    "block h-full rounded-full transition-[width] duration-200 ease-out",
                    item.phase === "done" ? "bg-positive" : "bg-signal"
                )}
                style={{ width: `${width}%` }}
            />
        </span>
    );
}
