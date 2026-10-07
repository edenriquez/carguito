# Carguito Backend

Hexagonal (ports & adapters) Flask API.

Pipeline: transient upload -> extract (PDF text / OCR / SAT XML) -> classify template
-> parse -> categorize -> persist structured data (raw file discarded) -> feed DuckDB cube.

A second, shorter pipeline carries photographed grocery tickets: the phone OCRs
the image and only the lines travel -> read into products -> matched to the
movement they explain -> priced against the user's own history.

## Layout

```
src/carguito/
  domain/         # pure business model: entities, value objects, services
  application/    # use cases + outbound port interfaces + DTOs
  adapters/
    inbound/http/ # Flask blueprints (the HTTP inbound adapter)
    outbound/     # persistence, extraction, parsing, cube, storage adapters
  config/         # settings + composition root (DI container)
  main.py         # create_app()
```

The `domain` and `application` layers never import Flask, SQLAlchemy, DuckDB, etc.
All infrastructure is injected via interfaces defined in `application/ports/outbound`.

## Run

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # add ".[ocr]" for image OCR support
cp .env.example .env
flask --app carguito.main run --debug   # or: python -m carguito.main
```

Defaults to a local SQLite DB and disabled auth so it runs offline. Point
`DATABASE_URL` at Supabase Postgres and set `SUPABASE_JWT_SECRET` +
`AUTH_DISABLED=false` for a real deployment.

## The chat is optional, and provider-agnostic

Workspace can answer questions about one saved lens in words. It is the only
part of Carguito that is not deterministic, so it is deliberately the only thing
behind an optional integration:

```bash
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=...            # yours; never committed
LLM_MODEL=minimax/minimax-m3
LLM_FALLBACK_MODEL=nvidia/nemotron-3-ultra-550b-a55b
```

Any endpoint speaking OpenAI-shaped Chat Completions works — OpenRouter, Groq,
Together, a local Ollama (`http://localhost:11434/v1`). One adapter covers all
of them (`adapters/outbound/chat/`), so switching providers is these three
values and no code, and no vendor name appears above the adapter line.

**All three empty is a supported state**, not a broken one: the container
injects a null object, the chat band renders disabled with its reason, and every
other part of Workspace reads as normal. No test needs a key.

The model only ever sees one lens: that lens's own aggregates plus its
movements (date, description, amount), up to 2 000 rows in the prompt. Past
that, and for any sum or grouping the brief did not precompute, the model has
three *tools* -- `buscar_movimientos`, `agrupar_movimientos`,
`resumen_de_periodo` -- that this code runs over the same rows and answers in
`Decimal`. The model asks for a total; it never produces one. Tool rounds happen
inside the adapter, and the client sees one stream either way.

Beyond the messages a request may carry `temperature`, `max_tokens`, a
`response_format` and tools (`ChatOptions` on the port). Extraction -- the
ticket reader, the price-listing reader, the reference-term lookup -- runs cold
and pinned to a JSON Schema; the chat runs with the provider's defaults. Every
request carries an output cap (4 096 tokens unless the caller sets one) because
gateways reserve the model's whole output window against the balance first,
and refuse a paragraph-long answer with a 402 on an account that cannot pay
for 131k tokens.

`docs/custody-plan.md`
covers the statement PDF, not the extracted ledger — so this is not a
contradiction, but it *is* a disclosure, and the UI makes it before the first
question rather than after. Note that free tiers on some gateways train on
conversations; check the policy before pointing this at a real ledger.

## Tickets: the basket behind a charge

A statement can only ever say `SORIANA HIPER 4062 · $1,412.60`. A photographed
grocery ticket is the other half of that charge, and it arrives through the same
custody path as a statement (`docs/custody-plan.md` G1/G2): the phone runs OCR
on the photo, the photo stays there, and only the lines travel — sealed to this
server's X25519 key.

```
POST /api/ingest/receipt   <- { v, key_id, epk, nonce, box }   (same envelope)
   payload: { v, kind:"receipt", filename, content_sha256, lines[],
              captured_at, extractor, transaction_id? }
   -> 201 { receipt_id, receipt, attached, suggestions[], prices_url }
   -> 409 esa foto ya fue procesada · 404 movimiento no encontrado
```

Two things happen server-side, and both are written to decline rather than
guess:

**Reading the lines.** `ReceiptReader` has two implementations. The heuristic
(`domain/services/receipt_reading.py`) is regexes over the OCR text and always
works, with no key. When a model is configured, `LlmReceiptReader` reads the
same lines — it is genuinely better at a mangled two-column thermal print — and
then both reads are scored against the total the ticket itself prints. The one
whose items add up closer wins; an answer that will not parse loses by default.
Which reader wrote a basket is stored on the row.

**Attaching it to a movement.** `domain/services/receipt_matching.py` requires
the totals to match (±$1 for OCR noise), inside a four-day window, and uses the
store name only to break ties. Two identical charges on the same day leave the
receipt *unattached* with both offered to the user: a wrong attachment is
invisible and permanent, so it is a question, not a coin flip.

## Prices come from the user's own tickets, and nowhere else

`GET /api/prices` builds a price book out of the stored receipt lines: per
product, every purchase with its store and date, the median, the cheapest and
dearest, and the last one against the typical one.

Products are grouped by a normalised key (`domain/services/products.py`) that
folds accents, drops barcodes and lifts the size out of the name, so
`7501020510010 LECHE LALA ENT 1L` and `LALA LECHE ENTERA 1 LT` are one history.
No fuzzy matching: two names that survive normalisation and still differ stay
two products, which is visible and correctable, unlike a silent merge of
`leche entera` with `leche deslactosada`.

The comparison basis is chosen, never assumed. A group compares per litre or
per kilo only when *every* purchase in it printed a size; otherwise it compares
per piece. Both are reported, because "$18 vs $32" is a lie when one of them was
three times the size.

`POST /api/prices/chat` streams an answer over that book through the same
optional LLM seam as the workspace chat, with the same posture and one addition
stated three times in the prompt: it has no internet. It compares the tickets
the user photographed, and "solo puedo comparar los tickets que subiste" is a
correct answer rather than a failure.

## The analytics cube is disposable

The DuckDB cube holds only *derived* state; the relational tables are the
record of truth. `POST /api/admin/cube/rebuild` drops the calling user's rows
in `fact_transactions` and re-derives them by streaming the full transaction
history back through the projection.

That is deliberate leverage, not a debugging tool: every later change to the
fact table (transfer flags, dedup fingerprints, tags) becomes "change the
projection, rebuild" instead of a bespoke DuckDB migration — and it keeps the
cost of replacing DuckDB with Postgres down to one adapter.

There are no rollup tables. `rollup_monthly` and `rollup_category` were written
on every upload and delete, read by nothing, and `refresh_rollups` ignored its
`user_id` and rebuilt every user's rollups each time; they were deleted rather
than fixed.

## Database schema & migrations

`adapters/outbound/persistence/models.py` is the **single source of truth** for
the schema. Alembic (`backend/migrations/`) is how that truth reaches a
database. `../supabase_setup.sql` is reduced to what SQLAlchemy cannot express:
the `profiles` table, the `handle_new_user` trigger on `auth.users`, and grants.

`Container.bootstrap()` runs `alembic upgrade head` in-process on startup, so
there is no separate "remember to migrate" deploy step. Set
`RUN_MIGRATIONS=false` to manage the schema out of band.

`migrations/env.py` takes the URL from `get_settings().database_url`, not from
`alembic.ini`, so the CLI, the app and the tests can never disagree.

```bash
alembic upgrade head              # apply
alembic downgrade -1              # roll back one
alembic revision --autogenerate -m "add foo"   # after editing models.py
alembic current                   # where am I
```

### Existing databases created before Alembic (stamp, don't migrate)

Revision `0001` reproduces exactly what the old `Database.create_all()`
produced. A database built that way already *has* those tables, so running
`upgrade` against it would fail on "table already exists". Mark it instead:

```bash
alembic stamp 0001      # "you are already at the baseline"
alembic upgrade head    # now apply 0002+ (created_at, RLS, amount CHECK)
```

A brand-new database just runs `alembic upgrade head`.

### Tests use `create_all`, deliberately

Every test builds a throwaway SQLite file, so the fixture sets
`run_migrations=False` and calls `metadata.create_all` — replaying the
migration history per test would measure Alembic, not the app.
`tests/test_migrations.py` guards the seam by asserting that a migrated
database and a `create_all` database have identical tables and columns; if a
migration is ever forgotten after a `models.py` edit, that test fails.

## Test

```bash
pytest
```
