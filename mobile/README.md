# Carguito Mobile (Expo)

React Native app (Expo Router). The phone is the custodian: raw bank statements
and SAT XML are copied into the app's private storage and **never leave the
device**. Extraction happens here, on-device; only the extracted text travels,
sealed with NaCl `crypto_box` against the backend's public key, and the response
comes back as a link to the web dashboard.

## Run

```bash
cd mobile
npm install
npx expo start
```

Set the backend URL in `app.json` under `expo.extra.apiUrl` (defaults to
`http://localhost:8000`). On a physical device use your machine's LAN IP.

`expo-crypto` is a native module, so a JS-only reload is not enough after a
fresh install — rebuild the dev client (`npx expo run:ios` / `run:android`).

## Checks

```bash
npm run typecheck    # tsc --noEmit
npm run verify       # envelope math, content hashing, polyfills, pdf.js boot
```

`npm run verify` runs the two Node self-checks in `scripts/`. They cover the
parts of the custody path that are host-independent; everything else needs a
device (see the checklist at the bottom).

## Structure

```
app/            # expo-router screens
  _layout.tsx   # navigation stack
  index.tsx     # dashboard (Resumen)
  upload.tsx    # pick → store on-device → extract → send sealed → dashboard link
  receipt.tsx   # photograph a ticket → OCR here → send sealed → basket + attach
  transactions.tsx
src/lib/
  api.ts              # backend client (read + delete only — no file upload)
  storage.ts          # on-device statement store (source of truth)
  extract.ts          # on-device extraction: PDF text layer / SAT XML
  pdf-lines.ts        # pdf.js fragments → reading-order lines (pure, testable)
  receipt.ts          # on-device OCR of a ticket photo → sealed payload
  receipt-lines.ts    # OCR boxes → printed ticket lines (pure, testable)
  secure-transport.ts # server key TOFU pin, sealed envelope, POST
  polyfills.ts        # globals Hermes lacks (base64, structuredClone, TextDecoder)
scripts/
  verify-envelope.mjs      # crypto + hashing + polyfills, under Node
  verify-extraction.mjs    # pdf.js worker-less boot + line grouping, under Node
  verify-receipt-lines.mjs # OCR box → ticket line grouping, under Node
```

## Tickets

`receipt.tsx` is the same custody promise for a different document. The photo is
taken by this app, read by this app — `@react-native-ml-kit/text-recognition`
(ML Kit on Android, Vision on iOS) — and never uploaded. What travels is the
text, sealed, to `POST /api/ingest/receipt`.

The recognizer is a **native module**, so a JS reload is not enough after
installing it; rebuild the dev client (`npx expo run:ios` / `run:android`), the
same as `expo-crypto`. Until that rebuild, the screen says so instead of
failing silently, and every other screen keeps working.

The awkward part is not the OCR, it is the geometry: a recognizer returns
*boxes*, and on a two-column ticket the product name and its price are two of
them. `receipt-lines.ts` joins them back into printed lines — the backend's
reader has one rule ("a product line ends in money"), so a name and a price
arriving as separate lines breaks every basket. That grouping is pure and is
checked by `npm run verify`.

## The wire protocol (v1)

```
GET  /api/ingest/key        -> { key_id, algorithm, public_key }
POST /api/ingest/extracted  <- { v, key_id, epk, nonce, box }
                            -> 201 { statement_id, template, transactions_created,
                                     statement, dashboard_url }
                               409 ya procesado · 400 envelope/payload inválido
```

The server's public key is pinned on first use. If it ever changes, the app
refuses to send and asks before trusting the new one — a silent key swap is
exactly the interception this layer exists to catch.

## Native / device notes

- `pdfjs-dist` is patched (`patches/pdfjs-dist+4.2.67.patch`) four times, all of
  them found by running it on a device — none reproduce under Node:
  1. Remove a runtime `import(workerSrc)` Metro cannot bundle. pdf.js runs its
     worker on the JS thread via `globalThis.pdfjsWorker`; see
     `src/lib/extract.ts`.
  2. Remove the entry's *top-level await*, which Hermes reads as a call to a
     function named `await`; the namespace arrives via
     `globalThis.pdfjsLibPromise` instead.
  3. Expand the `\p{Mn}` / `\p{Cf}` classes in `SpecialCharRegExp` into explicit
     ranges. Hermes implements no Unicode property escapes, so building that
     regex threw while the worker module was still loading — the crash landed
     the moment a user picked a file. `verify-extraction.mjs` re-derives the
     ranges from Node's Unicode tables and fails if they ever drift.
  4. Stop `fetchStandardFontData` from asking the main thread for a font file.
     That `sendWithPromise` is the only *worker -> main thread* request pdf.js
     makes; over the fake worker's `LoopbackPort` on Hermes the reply never
     arrives, so `getTextContent()` hung forever on any PDF whose fonts are not
     embedded — a spinner with no error. We ship no standard font data, so the
     answer was always going to be a rejection; the patch skips to the fallback
     pdf.js already takes, and the extracted text is unchanged.

  The same worker -> main thread path is used by `FetchBuiltInCMap`, which is
  therefore still able to hang. No statement seen so far needs external CMaps,
  and the underlying reason that direction fails is not yet understood.
- `src/lib/polyfills.ts` fills what Hermes lacks: `structuredClone`,
  `TextDecoder`, `DOMException` (core-js inside pdf.js dereferences it while
  loading) and `ReadableStream` (`getTextContent` is delivered over a stream).
  `verify-extraction.mjs` deletes these from Node before loading pdf.js, so the
  script fails the same way a phone would.
- `metro.config.js` shims Node built-ins for the dead Node branches inside
  pdfjs-dist / tweetnacl / js-sha256.
- Scanned PDFs are refused with an honest message rather than uploaded. OCR on
  device is a later phase.
