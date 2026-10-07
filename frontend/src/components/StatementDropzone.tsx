"use client";

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { FileUp } from "lucide-react";
import { api, UploadError, type UploadResult } from "@/lib/api";
import { cn } from "@/lib/cn";
import { isEncryptedPdf } from "@/lib/pdf";
import { Button, useToast } from "@/components/ui";
import { PdfPasswordDialog } from "@/components/PdfPasswordDialog";
import { UploadChips, UploadMark } from "@/components/onboarding/UploadMark";
import { UploadQueue } from "@/components/onboarding/UploadQueue";

const ACCEPT = ".pdf,.xml";
const ACCEPTED_EXTENSIONS = [".pdf", ".xml"];

/** What one file is doing right now.
 *
 *  `sending` and `reading` are separate on purpose. The first is bytes on the
 *  wire and has a real fraction; the second is the backend parsing, where the
 *  only honest progress is "still going". Drawing one bar for both would mean
 *  inventing a percentage for the half that takes the longest. */
export type UploadPhase =
    | "queued"
    | "sending"
    | "reading"
    | "password"
    | "done"
    | "error";

export type UploadItem = {
    /** Stable for the row's lifetime; two files can share a name. */
    id: string;
    name: string;
    size: number;
    phase: UploadPhase;
    /** 0–1, bytes actually delivered. Only meaningful while `sending`. */
    sent: number;
    /** Kept so a password answer — or a retry — can re-run this exact file. */
    file: File;
    result?: UploadResult;
    error?: string;
    /** The PDF rejected a password already; the dialog says so on the retry. */
    wrongPassword?: boolean;
};

let seq = 0;
const nextId = () => `u${++seq}`;

function isAccepted(name: string): boolean {
    const lower = name.toLowerCase();
    return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/**
 * Upload statements as a hook, so the dropzone, the archive and the header
 * button are the same behaviour with different chrome — same validation, same
 * queue, same completion callbacks.
 *
 * **Many files, one at a time.** The picker and the drop target both take a
 * whole selection, and the queue walks it sequentially rather than firing
 * every request at once. Three reasons, in order of how much they matter:
 * the slow half of an upload is the backend parsing a PDF, so five concurrent
 * requests finish no sooner and are likelier to time out; the password dialog
 * is modal, and two files asking at the same time have nowhere to ask; and a
 * queue that advances one row at a time is legible — you can see which file
 * is being read right now.
 *
 * **A rejected file is a row, not a toast.** With one file a toast could say
 * "that was a .docx". With six it cannot say *which*, so every outcome —
 * wrong extension included — lands on the file's own row and stays there
 * until it is dismissed.
 *
 * The extension is checked before the request goes out, and an encrypted PDF
 * is sniffed locally: learning "that was a .docx" or "this needs a password"
 * should not cost a round trip.
 */
export function useStatementUpload(
    onUploaded?: () => void,
    /** Richer sibling of `onUploaded`: receives the parse outcome of each
     *  file, so the onboarding review can show what the OCR understood. */
    onResult?: (result: UploadResult) => void
) {
    const inputRef = useRef<HTMLInputElement>(null);
    const [queue, setQueue] = useState<UploadItem[]>([]);
    /** The file whose password answer is in flight. The dialog stays up while
     *  it is verified: closing on submit and reopening on a wrong password
     *  would blink, and the answer is usually wrong the first time. */
    const [verifying, setVerifying] = useState<string | null>(null);
    const { toast } = useToast();

    // The queue is walked by an effect, so the work is driven by state rather
    // than by a loop holding its own copy of it: a file added mid-flight joins
    // the same run, and answering the password dialog is just another state
    // change that the walker picks up.
    const running = useRef(false);
    // Callbacks live in a ref so the walker does not restart when the parent
    // re-renders with a new closure — a restart mid-upload would double-send.
    const handlers = useRef({ onUploaded, onResult });
    handlers.current = { onUploaded, onResult };

    const patch = useCallback((id: string, next: Partial<UploadItem>) => {
        setQueue((cur) => cur.map((it) => (it.id === id ? { ...it, ...next } : it)));
    }, []);

    const send = useCallback(
        async (item: UploadItem, password?: string) => {
            patch(item.id, { phase: "sending", sent: 0, error: undefined });
            try {
                const result = await api.uploadStatement(item.file, password, (fraction) => {
                    // Once the bytes are gone the bar stops being the truth:
                    // hand over to `reading`, which claims nothing.
                    patch(item.id, fraction >= 1 ? { phase: "reading", sent: 1 } : { sent: fraction });
                });
                patch(item.id, { phase: "done", sent: 1, result, wrongPassword: false });
                handlers.current.onUploaded?.();
                handlers.current.onResult?.(result);
            } catch (e) {
                const code = e instanceof UploadError ? e.code : undefined;
                if (code === "pdf_password_required" || code === "pdf_password_incorrect") {
                    patch(item.id, {
                        phase: "password",
                        wrongPassword: code === "pdf_password_incorrect",
                    });
                    return;
                }
                patch(item.id, { phase: "error", error: (e as Error).message });
            }
        },
        [patch]
    );

    useEffect(() => {
        if (running.current) return;
        // Anything waiting on the user blocks the queue: the dialog is modal,
        // and starting the next file behind it would put a second upload under
        // a question the user has not answered yet. `verifying` holds the line
        // for the beat between submitting a password and learning whether it
        // was right — that send runs outside this walker, so without it the
        // next file would start alongside it.
        if (verifying !== null) return;
        if (queue.some((it) => it.phase === "password")) return;
        const next = queue.find((it) => it.phase === "queued");
        if (!next) return;

        running.current = true;
        void (async () => {
            try {
                if (next.file.name.toLowerCase().endsWith(".pdf")) {
                    const bytes = new Uint8Array(await next.file.arrayBuffer());
                    if (isEncryptedPdf(bytes)) {
                        patch(next.id, { phase: "password", wrongPassword: false });
                        return;
                    }
                }
                await send(next);
            } finally {
                running.current = false;
                // Nudge the effect: the state change from the line above may
                // have been committed before `running` was released.
                setQueue((cur) => [...cur]);
            }
        })();
    }, [queue, send, patch, verifying]);

    /** Hand the picker's or the drop's whole selection to the queue. */
    const enqueue = useCallback((files: File[]) => {
        if (files.length === 0) return;
        setQueue((cur) => [
            ...cur,
            ...files.map<UploadItem>((file) => ({
                id: nextId(),
                name: file.name,
                size: file.size,
                file,
                sent: 0,
                ...(isAccepted(file.name)
                    ? { phase: "queued" as const }
                    : {
                          phase: "error" as const,
                          error: "Solo entran PDF de tu banco o XML del SAT.",
                      }),
            })),
        ]);
    }, []);

    const answerPassword = useCallback(
        (id: string, password: string) => {
            const item = queue.find((it) => it.id === id);
            if (!item) return;
            setVerifying(id);
            void send(item, password).finally(() => setVerifying(null));
        },
        [queue, send]
    );

    const retry = useCallback(
        (id: string) => patch(id, { phase: "queued", sent: 0, error: undefined }),
        [patch]
    );

    const dismiss = useCallback(
        (id: string) => setQueue((cur) => cur.filter((it) => it.id !== id)),
        []
    );

    /** Everything that has finished, either way. The dropzone clears these
     *  when a new batch starts so the list is about the batch in hand. */
    const clearSettled = useCallback(
        () =>
            setQueue((cur) =>
                cur.filter((it) => it.phase !== "done" && it.phase !== "error")
            ),
        []
    );

    const pick = useCallback(() => inputRef.current?.click(), []);

    const uploading = queue.some(
        (it) => it.phase === "sending" || it.phase === "reading" || it.phase === "queued"
    );
    const asking =
        queue.find((it) => it.phase === "password") ??
        queue.find((it) => it.id === verifying) ??
        null;

    // The summary toast fires once per batch, when nothing is left in flight —
    // one per file would be a stack of six.
    const settledAt = useRef(0);
    useEffect(() => {
        const active = queue.filter(
            (it) => it.phase !== "done" && it.phase !== "error"
        ).length;
        const done = queue.filter((it) => it.phase === "done");
        if (active > 0 || done.length === 0) {
            if (active > 0) settledAt.current = 0;
            return;
        }
        if (settledAt.current === done.length) return;
        settledAt.current = done.length;
        const movements = done.reduce((n, it) => n + (it.result?.transactions_created ?? 0), 0);
        const skipped = done.reduce((n, it) => n + (it.result?.transactions_skipped ?? 0), 0);
        const already = skipped > 0 ? ` · ${skipped.toLocaleString("es-MX")} ya estaban` : "";
        toast(
            skipped > 0
                ? `Listo: ${movements.toLocaleString("es-MX")} movimiento${movements === 1 ? "" : "s"} nuevo${movements === 1 ? "" : "s"}${already}`
                : done.length === 1
                  ? `Listo: ${movements.toLocaleString("es-MX")} movimiento${movements === 1 ? "" : "s"} leídos`
                  : `Listo: ${done.length} documentos · ${movements.toLocaleString("es-MX")} movimientos`,
            "positive"
        );
    }, [queue, toast]);

    /** Render this once next to whatever triggers `pick()`. The password
     *  dialog rides along so every upload surface gets it for free. */
    const input = (
        <>
            <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                multiple
                hidden
                onChange={(e) => {
                    enqueue(Array.from(e.target.files ?? []));
                    // Without this, re-selecting the same file fires no change.
                    e.target.value = "";
                }}
            />
            <PdfPasswordDialog
                open={asking !== null}
                filename={asking?.name}
                wrong={asking?.wrongPassword}
                busy={verifying !== null}
                onCancel={() => {
                    if (!asking) return;
                    setVerifying(null);
                    patch(asking.id, {
                        phase: "error",
                        error: "Hace falta la contraseña del PDF.",
                    });
                }}
                onSubmit={(password) => asking && answerPassword(asking.id, password)}
            />
        </>
    );

    return {
        enqueue,
        pick,
        uploading,
        queue,
        retry,
        dismiss,
        clearSettled,
        input,
    };
}

/**
 * The upload surface for the first statement. A dropzone rather than a bare
 * button because this is the whole job on the whole screen — the target
 * should be the size of the decision, not the size of a toolbar control.
 * On touch devices the drop affordance is inert and the button is the path,
 * which is why the button is the filled primary and the drop copy is a hint.
 */
export function StatementDropzone({
    onUploaded,
    onResult,
    onSettled,
    className,
    autoFocus = false,
}: {
    /** Fires after a statement parses. The caller re-probes and swaps state. */
    onUploaded?: () => void;
    /** Receives the parse outcome — bank, period, template — for review UIs.
     *  Fires once per file. */
    onResult?: (result: UploadResult) => void;
    /** Fires once when the batch has nothing left in flight, with everything
     *  that parsed. A caller that has a next step — the onboarding's review —
     *  waits for this rather than for `onResult`, which with five files would
     *  move the screen on while four were still uploading. */
    onSettled?: (results: UploadResult[]) => void;
    className?: string;
    /** Put the "Elegir archivo" button in focus on mount: for arrivals whose
     *  previous click was already "Comenzar". Browsers refuse to open the file
     *  picker without a gesture, so focus (and Enter/Space) is as close as the
     *  web allows to "the picker is ready". */
    autoFocus?: boolean;
}) {
    const { enqueue, pick, uploading, queue, retry, dismiss, clearSettled, input } =
        useStatementUpload(onUploaded, onResult);
    const [dragging, setDragging] = useState(false);
    const pickRef = useRef<HTMLButtonElement>(null);

    // One call per batch. `settled` holds how many had finished the last time
    // it fired, so a re-render cannot replay it and a second batch can.
    const settled = useRef(0);
    const report = useRef(onSettled);
    report.current = onSettled;
    useEffect(() => {
        const done = queue.filter((i) => i.phase === "done");
        const active = queue.some((i) => i.phase !== "done" && i.phase !== "error");
        if (active) {
            settled.current = 0;
            return;
        }
        if (done.length === 0 || settled.current === done.length) return;
        settled.current = done.length;
        report.current?.(done.map((i) => i.result!));
    }, [queue]);

    useEffect(() => {
        if (!autoFocus) return;
        const el = pickRef.current;
        if (!el) return;
        el.focus({ preventScroll: true });
        el.scrollIntoView({ block: "center" });
    }, [autoFocus]);

    function onDrop(e: DragEvent<HTMLDivElement>) {
        e.preventDefault();
        setDragging(false);
        // A dropped selection is a batch, and it is a new one: rows from the
        // previous batch that are already settled step aside so the list is
        // about the files in hand.
        clearSettled();
        enqueue(Array.from(e.dataTransfer.files ?? []));
    }

    return (
        <div
            onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
                "rounded-panel border border-dashed bg-paper px-6 py-7 text-center sm:px-8 sm:py-8",
                "transition-colors duration-100",
                // Signal only while the file is actually over the target. A
                // dropzone that is permanently cyan is just a coloured box.
                dragging ? "border-signal bg-wash/20" : "border-muted",
                className
            )}
        >
            {/* The mark is centred on the card; the chips hang off its right
                edge, which is why they are positioned against this wrapper and
                not against the card — the card is 1100px wide here, and a lane
                pinned to its edge would be a metre from the thing it is flying
                into. They stop while a real file is over the target: the user
                is doing the thing, and a demo of it alongside is noise. */}
            <div className="relative mx-auto mb-3.5 w-20">
                <UploadMark
                    state={uploading ? "uploading" : dragging ? "dragging" : "idle"}
                />
                {!uploading && !dragging && <UploadChips />}
            </div>

            {/* Inter, like the app this opens. And kept compact on purpose:
                this box and the scene below it answer the same moment — "what
                do I do" and "what happens to my file" — so they have to be
                readable without scrolling between them. */}
            <p className="text-title-sm font-normal text-ink">
                {uploading ? "Leyendo tus documentos…" : "Suéltalos aquí"}
            </p>
            <p className="mx-auto mt-1.5 max-w-sm text-body-sm text-graphite">
                {uploading
                    ? "Tomin está sacando los movimientos, uno por uno."
                    : "PDF de tu banco o XML del SAT. Puedes soltar varios a la vez."}
            </p>

            <div className="mt-4">
                <Button
                    ref={pickRef}
                    loading={uploading}
                    onClick={() => {
                        clearSettled();
                        pick();
                    }}
                    icon={<FileUp size={16} />}
                    className="text-ink"
                >
                    Elegir archivos
                </Button>
            </div>
            <p className="mt-2.5 hidden text-label text-ash sm:block">
                …o arrástralos aquí desde tu carpeta de descargas.
            </p>

            <UploadQueue
                items={queue}
                onRetry={retry}
                onDismiss={dismiss}
                className="mx-auto mt-5 max-w-xl"
            />

            {input}
        </div>
    );
}
