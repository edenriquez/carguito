# Carguito

Financial visibility tool for the Mexican market.
Aggregates messy bank data into clear insights, forecasts, and goals.

The **phone is the durable source of truth** for raw statements: the mobile app
stores bank statements / SAT XML on-device and uploads only a *transient* copy
to the backend, which parses it, stores the structured data, discards the raw
file, and feeds an analytics cube. Web and mobile are display layers over that
cube.

## Architecture

```
landing/    Next.js marketing site (port 3001) - standalone, no backend; its own
            Vercel project (Root Directory = landing). "Comenzar" links to the app
            via NEXT_PUBLIC_APP_URL.
frontend/   Next.js web app (port 3000) - display layer over the cube. Six views:
            Movimientos (/), Categorías, Fijos, Pronóstico, Precios, Documentos,
            plus the "Lecturas" menu -> /workspace. Root (/) switches: no data ->
            its own marketing Landing.tsx -> Onboarding -> the app.
mobile/     React Native (Expo) app - on-device statement store + extraction +
            sealed upload (statements.source = "device"). Not distributed yet.
backend/    Flask hexagonal API (port 8000) - parse pipeline + DuckDB analytics cube
mocks/      Pre-rename design references from June 2026 (see mocks/README.md)
docs/       Plans and audits (redesign-plan, custody-plan, advisor-principles,
            audit/)
supabase_setup.sql   Postgres schema + RLS + auth trigger
```

Two ingestion routes reach the same pipeline
(`classify template -> parse -> categorize -> persist -> feed DuckDB cube`):

- **Web** (`POST /api/statements`): the browser uploads the PDF/XML; the
  backend extracts text from a *transient* copy and discards the file
  (`statements.source = "web"`). Password-protected PDFs take a `password`
  form field.
- **Device** (`POST /api/ingest/extracted`): the phone extracts the text
  itself and sends it sealed with `crypto_box` against the key from
  `GET /api/ingest/key`; the file never leaves the phone
  (`statements.source = "device"`). See `docs/custody-plan.md`.

Grocery tickets ride a second, shorter pipeline with the same custody rule: the
phone photographs a ticket, OCRs it **on device**, and sends only the lines,
sealed (`POST /api/ingest/receipt`) — `read into products -> match to the
movement it explains -> compare against your own price history`. A statement
can only say `SORIANA $1,412.60`; this is what turns that into "la leche te
subió 19%". There is no web route for tickets: the Precios view only fills up
from the mobile app.

- Backend: hexagonal (ports & adapters), Flask HTTP, SQLAlchemy (Supabase
  Postgres or SQLite), local OCR (pdfplumber + optional Tesseract), DuckDB cube.
  Dedicated parsers: Banamex, Banco Azteca, SAT CFDI; every other bank
  (Nu, BBVA, Santander, ...) is detected by name but parsed by `generic_bank`.
- Auth: Supabase (JWT verified server-side in
  `backend/src/carguito/adapters/inbound/http/auth.py`); **disabled by default**
  (`AUTH_DISABLED=true` in `.env.example`) and the web frontend does not send a
  bearer token yet, so any deployment is single-user and unauthenticated.
- Fijos (pinned recurring charges) and tagged incomes for Pronóstico live in the
  browser's `localStorage`, not in the backend.

### Known doc/config discrepancies (2026-09-05)

- `mobile/src/lib/api.ts` falls back to `http://127.0.0.1:8010` when
  `expo.extra.apiUrl` is missing, while `mobile/README.md` says the default is
  `http://localhost:8000` and `mobile/app.json` points at a LAN IP on `:8000`.
  The backend listens on **8000**; the `8010` fallback is stale. (Recorded
  here; `mobile/` untouched by the audit.)
- `frontend/src/components/Landing.tsx` duplicates the pitch in `landing/`
  with different copy (H1, feature count, bank list). See
  `docs/audit/2026-09-05/historia.md`.

## Quickstart

```bash
# Backend (Python 3.10+)
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && cp .env.example .env
python -m carguito.main               # http://localhost:8000

# Web app
cd frontend && npm install && npm run dev   # http://localhost:3000

# Landing (marketing site)
cd landing && npm install && npm run dev    # http://localhost:3001

# Mobile
cd mobile && npm install && npx expo start  # set expo.extra.apiUrl in app.json
```

See each package's `README.md` for details.
