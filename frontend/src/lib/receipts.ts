/**
 * Reading a ticket from the browser, the way the phone reads it.
 *
 * The phone's promise (`mobile/src/lib/receipt.ts`) is that the photo never
 * leaves the device: OCR runs locally and only the text travels, sealed. The
 * web keeps the same promise with the same protocol. The image is read here,
 * in a Tesseract worker inside the browser, and what goes to the backend is
 * the envelope `POST /api/ingest/receipt` already accepts from the phone — a
 * `crypto_box` sealed to the server's X25519 key with a fresh ephemeral
 * keypair. The backend does not learn which client sent it and does not need
 * to: the lines are the lines.
 *
 * What is different from the phone is trust in the key. The phone pins the
 * first key it sees; a browser has nowhere durable enough to pin, so the key is
 * fetched per session over the same TLS the rest of the app rides on. The
 * envelope still buys what it buys everywhere else — an opaque body past any
 * proxy that terminates TLS.
 */

import nacl from "tweetnacl";
import naclUtil from "tweetnacl-util";
import { API_URL, request } from "./api";
import type { Receipt } from "./prices";

export const ALGORITHM = "x25519-xsalsa20-poly1305";
export const ENVELOPE_VERSION = 1;
export const RECEIPT_EXTRACTOR = "tesseract-web";

/** What the backend's `POST /api/ingest/receipt` accepts, before sealing.
 *  Mirrors the phone's `ReceiptPayload` field for field. */
export type ReceiptPayload = {
    v: 1;
    kind: "receipt";
    filename: string;
    /** Hex SHA-256 of the ORIGINAL image bytes; the backend dedups on this. */
    content_sha256: string;
    lines: string[];
    captured_at: string;
    /** Which OCR read it, for tracing reading quality back to its engine. */
    extractor: string;
    transaction_id?: string | null;
};

export type ReceiptSuggestion = {
    transaction: { id: string; date: string; description: string | null; amount: number };
    score: number;
    reason: string;
};

export type ReceiptUploadResponse = {
    receipt_id: string;
    receipt: Receipt;
    attached: boolean;
    suggestions: ReceiptSuggestion[];
    prices_url: string;
};

type ServerKey = { key_id: string; algorithm: string; public_key: string };

export type TicketErrorCode =
    /** The recognizer found no text: a blurry photo, or not a ticket. */
    | "no_text"
    /** The browser could not decode the file as an image. */
    | "unreadable"
    /** The backend already has this photo (same bytes). */
    | "duplicate"
    /** Anything the server refused, with its own words. */
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
            default:
                return error.message;
        }
    }
    return (error as Error).message;
}

/* -------------------------------------------------------------------------- */
/* OCR, in the browser                                                         */
/* -------------------------------------------------------------------------- */

/** Longest side the photo is scaled to before OCR. A 12-megapixel phone
 *  photo is more than Tesseract wants and takes seconds longer to read; a
 *  ticket's print is legible well under this. */
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

/** Whether the picker's file is something this reader will try. */
export function isTicketImage(file: File): boolean {
    return file.type.startsWith("image/") || isHeic(file);
}

/**
 * Decode a HEIC into a JPEG blob with libheif compiled to wasm. Loaded on
 * first use, like the recognizer: it is a megabyte nobody with a JPG pays
 * for. Safari can decode HEIC natively, but converting everywhere keeps one
 * path rather than two that could read the same photo differently.
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
 * The photo as Tesseract reads best: scaled to a sane size and flattened to
 * grey. Done on a canvas so the bytes sent to the worker are already the
 * bytes it would have derived, and so an image format the browser decodes
 * works without the worker having to know it.
 */
async function prepare(file: File): Promise<Blob> {
    const source: Blob = isHeic(file) ? await decodeHeic(file) : file;
    let bitmap: ImageBitmap;
    try {
        bitmap = await createImageBitmap(source);
    } catch (e) {
        throw new TicketError("unreadable", (e as Error).message);
    }
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new TicketError("unreadable", "canvas unavailable");
    ctx.filter = "grayscale(1)";
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return new Promise((resolve, reject) =>
        canvas.toBlob(
            (blob) => (blob ? resolve(blob) : reject(new TicketError("unreadable", "toBlob"))),
            "image/png"
        )
    );
}

/**
 * The lines Tesseract read, top to bottom, as the backend's reader wants
 * them: one printed row per string, nothing empty. A thermal print puts the
 * product and its price on the same row, and Tesseract keeps them on the
 * same line, which is the whole reason the reader can pair them.
 */
export async function recognizeTicket(
    file: File,
    onProgress?: (fraction: number) => void
): Promise<string[]> {
    const image = await prepare(file);
    // Loaded on first use: the worker, its wasm core and the Spanish model
    // are several megabytes nobody who never uploads a ticket should pay for.
    const { createWorker } = await import("tesseract.js");
    const worker = await createWorker("spa", 1, {
        logger: (m) => {
            if (m.status === "recognizing text" && onProgress) onProgress(m.progress);
        },
    });
    try {
        const { data } = await worker.recognize(image);
        const lines = data.text
            .split(/\r?\n/)
            .map((line) => line.replace(/\s+/g, " ").trim())
            .filter((line) => line.length > 0);
        if (lines.length === 0) {
            throw new TicketError("no_text", "The recognizer returned no lines");
        }
        return lines;
    } finally {
        await worker.terminate();
    }
}

/* -------------------------------------------------------------------------- */
/* seal + send                                                                 */
/* -------------------------------------------------------------------------- */

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

let cachedKey: ServerKey | null = null;

async function serverKey(): Promise<ServerKey> {
    if (cachedKey) return cachedKey;
    const key = await request<ServerKey>("/api/ingest/key");
    if (key.algorithm !== ALGORITHM) {
        throw new TicketError("rejected", `Algoritmo no soportado: ${key.algorithm}`);
    }
    if (naclUtil.decodeBase64(key.public_key).length !== nacl.box.publicKeyLength) {
        throw new TicketError("rejected", "La llave pública del servidor no mide 32 bytes");
    }
    cachedKey = key;
    return key;
}

/** Seals a payload for the server's key. Pure, so it can be tested offline. */
export function sealPayload(payload: ReceiptPayload, key: ServerKey) {
    const message = naclUtil.decodeUTF8(JSON.stringify(payload));
    const ephemeral = nacl.box.keyPair();
    const nonce = nacl.randomBytes(nacl.box.nonceLength);
    const box = nacl.box(message, nonce, naclUtil.decodeBase64(key.public_key), ephemeral.secretKey);
    ephemeral.secretKey.fill(0);
    message.fill(0);
    return {
        v: ENVELOPE_VERSION,
        key_id: key.key_id,
        epk: naclUtil.encodeBase64(ephemeral.publicKey),
        nonce: naclUtil.encodeBase64(nonce),
        box: naclUtil.encodeBase64(box),
    };
}

/**
 * Seals the ticket's text and posts it. The image is not a parameter: this
 * function has no way to send one, which is the point.
 */
export async function sendReceipt(payload: ReceiptPayload): Promise<ReceiptUploadResponse> {
    const envelope = sealPayload(payload, await serverKey());
    let res: Response;
    try {
        res = await fetch(`${API_URL}/api/ingest/receipt`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(envelope),
        });
    } catch (e) {
        throw new TicketError("rejected", `No se pudo enviar: ${(e as Error).message}`);
    }
    if (res.status === 409) {
        throw new TicketError("duplicate", "Esta foto ya fue procesada");
    }
    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const body = (await res.json()) as { error?: string };
            if (typeof body.error === "string") detail = body.error;
        } catch {
            // The status is the message.
        }
        throw new TicketError("rejected", detail);
    }
    return (await res.json()) as ReceiptUploadResponse;
}

/** The whole trip for one photo: read it here, seal the text, send it. */
export async function uploadTicket(
    file: File,
    onProgress?: (fraction: number) => void
): Promise<ReceiptUploadResponse> {
    const [contentSha256, lines] = await Promise.all([
        file.arrayBuffer().then(sha256Hex),
        recognizeTicket(file, onProgress),
    ]);
    return sendReceipt({
        v: 1,
        kind: "receipt",
        filename: file.name,
        content_sha256: contentSha256,
        lines,
        captured_at: new Date(file.lastModified || Date.now()).toISOString(),
        extractor: RECEIPT_EXTRACTOR,
        transaction_id: null,
    });
}
