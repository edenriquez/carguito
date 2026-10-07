/**
 * Uploading a ticket photo from the browser.
 *
 * The phone reads its own photos and sends text (`mobile/src/lib/receipt.ts`).
 * The web tried to do the same with Tesseract in a worker, and on photographed
 * thermal paper it read a third of the prices — so the web's door is
 * different: the photo goes to the backend, which reads it with a recognizer
 * trained on photographs and keeps nothing but the rows. The same honesty the
 * web's statement upload already has, and this file says so wherever the user
 * can read it.
 *
 * What this file still does locally is the part a browser is good at: decode
 * whatever the picker handed over (HEIC included), turn it the way the camera
 * meant, and shrink it to what the recognizer wants, so a 12-megapixel photo
 * leaves as a sub-megabyte JPEG.
 */

import { API_URL } from "./api";
import type { Receipt } from "./prices";

export type ReceiptSuggestion = {
    transaction: { id: string; date: string; description: string | null; amount: number };
    score: number;
    reason: string;
};

/** The answer to a ticket that just came in: the same shape the phone gets. */
export type ReceiptUploadResponse = {
    receipt_id: string;
    receipt: Receipt;
    attached: boolean;
    suggestions: ReceiptSuggestion[];
    prices_url: string;
};

export type TicketErrorCode =
    /** The recognizer found no text: a blurry photo, or not a ticket. */
    | "no_text"
    /** The file could not be decoded as an image, here or on the server. */
    | "unreadable"
    /** The backend already has this photo (same bytes). */
    | "duplicate"
    /** The server has no OCR installed for tickets. */
    | "no_ocr"
    /** Anything else the server refused, with its own words. */
    | "rejected";

export class TicketError extends Error {
    readonly code: TicketErrorCode;
    constructor(code: TicketErrorCode, message: string) {
        super(message);
        this.name = "TicketError";
        this.code = code;
    }
}

/** What to tell the user, in the product's voice. */
export function ticketMessage(error: unknown): string {
    if (error instanceof TicketError) {
        switch (error.code) {
            case "no_text":
                return "No alcancé a leer el ticket. Prueba con más luz y la foto derecha.";
            case "unreadable":
                return "No pude abrir esta imagen. Entran JPG, PNG, WebP o HEIC.";
            case "duplicate":
                return "Este ticket ya estaba leído.";
            case "no_ocr":
                return "Este servidor no tiene lector de tickets instalado.";
            default:
                return error.message;
        }
    }
    return (error as Error).message;
}

/* -------------------------------------------------------------------------- */
/* The photo, made ready                                                       */
/* -------------------------------------------------------------------------- */

/** Longest side the photo is scaled to before upload. What the backend's
 *  recognizer reads at; anything larger is bytes on the wire for nothing. */
const MAX_SIDE = 2000;

/** An iPhone's default photo format. Chrome and Firefox cannot decode it,
 *  so it is turned into a JPEG here, in the browser, before anything else
 *  looks at it. Matched on the extension as well as the type: the browser
 *  often reports no type at all for a HEIC dropped in from a folder. */
export function isHeic(file: File): boolean {
    const type = file.type.toLowerCase();
    const name = file.name.toLowerCase();
    return (
        type === "image/heic" ||
        type === "image/heif" ||
        name.endsWith(".heic") ||
        name.endsWith(".heif")
    );
}

/** Whether the picker's file is something this uploader will try. */
export function isTicketImage(file: File): boolean {
    return file.type.startsWith("image/") || isHeic(file);
}

/**
 * Decode a HEIC into a JPEG blob with libheif compiled to wasm. Loaded on
 * first use: it is a megabyte nobody with a JPG pays for. Safari can decode
 * HEIC natively, but converting everywhere keeps one path rather than two
 * that could read the same photo differently.
 */
async function decodeHeic(file: File): Promise<Blob> {
    const { default: heic2any } = await import("heic2any");
    let out: Blob | Blob[];
    try {
        out = await heic2any({ blob: file, toType: "image/jpeg", quality: 0.92 });
    } catch (e) {
        throw new TicketError("unreadable", (e as Error).message);
    }
    // A HEIC can hold several images (a burst); the first is the photo.
    return Array.isArray(out) ? out[0] : out;
}

/**
 * The photo as the recognizer wants it: the way up the camera meant (a phone
 * stores the sensor's pixels and an EXIF note saying which way is up), no
 * longer than `MAX_SIDE`, as a JPEG. Done on a canvas so a format only the
 * browser decodes works, and so the upload is small.
 */
export async function prepareTicket(file: File): Promise<Blob> {
    const source: Blob = isHeic(file) ? await decodeHeic(file) : file;
    let bitmap: ImageBitmap;
    try {
        bitmap = await createImageBitmap(source, { imageOrientation: "from-image" });
    } catch (e) {
        throw new TicketError("unreadable", (e as Error).message);
    }
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new TicketError("unreadable", "canvas unavailable");
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return new Promise((resolve, reject) =>
        canvas.toBlob(
            (blob) => (blob ? resolve(blob) : reject(new TicketError("unreadable", "toBlob"))),
            "image/jpeg",
            0.9
        )
    );
}

/* -------------------------------------------------------------------------- */
/* Send                                                                        */
/* -------------------------------------------------------------------------- */

function errorFor(status: number, body: string): TicketError {
    let detail = `HTTP ${status}`;
    try {
        const parsed = JSON.parse(body) as { error?: string };
        if (typeof parsed.error === "string") detail = parsed.error;
    } catch {
        // The status is the message.
    }
    if (status === 409) return new TicketError("duplicate", detail);
    if (status === 415) return new TicketError("unreadable", detail);
    if (status === 422) return new TicketError("no_text", detail);
    if (status === 503) return new TicketError("no_ocr", detail);
    return new TicketError("rejected", detail);
}

/**
 * Posts the prepared photo and reports the bytes as they go. XHR rather than
 * fetch for the one thing fetch cannot do: upload progress, which is the
 * only honest fraction this trip has — the read on the other side takes a
 * couple of seconds and reports nothing.
 */
export function sendTicket(
    image: Blob,
    filename: string,
    capturedAt: string,
    onProgress?: (fraction: number) => void
): Promise<ReceiptUploadResponse> {
    return new Promise((resolve, reject) => {
        const form = new FormData();
        form.append("file", image, filename);
        form.append("captured_at", capturedAt);
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API_URL}/api/receipts/upload`);
        if (onProgress) {
            xhr.upload.addEventListener("progress", (e) => {
                if (e.lengthComputable) onProgress(e.loaded / e.total);
            });
            xhr.upload.addEventListener("loadend", () => onProgress(1));
        }
        xhr.addEventListener("load", () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    resolve(JSON.parse(xhr.responseText) as ReceiptUploadResponse);
                } catch {
                    reject(new TicketError("rejected", "El servidor respondió algo ilegible."));
                }
                return;
            }
            reject(errorFor(xhr.status, xhr.responseText));
        });
        xhr.addEventListener("error", () =>
            reject(new TicketError("rejected", `No se pudo contactar al backend en ${API_URL}.`))
        );
        xhr.send(form);
    });
}

/** The whole trip for one photo: make it ready here, send it, get the basket. */
export async function uploadTicket(
    file: File,
    onProgress?: (fraction: number) => void
): Promise<ReceiptUploadResponse> {
    const image = await prepareTicket(file);
    const filename = file.name.replace(/\.[^.]+$/, "") + ".jpg";
    // The best guess at when the photo was taken: the file's own timestamp.
    // Off when the photo was copied from a phone, which is why the backend
    // treats it as a fallback and the print's date wins whenever it reads.
    const capturedAt = new Date(file.lastModified || Date.now()).toISOString();
    return sendTicket(image, filename, capturedAt, onProgress);
}
