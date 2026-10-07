# Carguito Redesign — Architecture & UX Plan

> **Estado al 2026-09-05** (auditoría de producto; sustituye al header
> "proposal for review / nothing implemented" que quedó obsoleto).
>
> **Enviado**, según el propio §10 y el git log (`git log --oneline`):
> - Backend B0–B7: correctness foundation (9e798ac, 2026-07-27), metric
>   engine + dashboards B3–B4 (35b4735), PATCH transacciones B5 (0aef628),
>   tags + bridge B6 y flags de transferencia / retiro B7 (b626fd9,
>   2026-07-28). B8 (accounts/balances), B9–B10 (CFDI v2 + reconciliación)
>   y B11–B12 (recurrencia v2, anomalías) **no** se enviaron como se
>   describen aquí; la recurrencia sigue en `/api/analytics/recurring`
>   (legacy) y las "lecturas" de atención (`GET /api/transactions/attention`,
>   a9ba1a9, 2026-09-01) son un servicio aparte, no el ensamble de B12.
> - Frontend F0–F7: design foundation F0–F2 (057f959), shell F3 (6741c79),
>   command center F4 + retiro de páginas F5 (5630d8f), filtros F6
>   (8039217), widgets F7 (c48f681, 2026-07-28). Después, el restyle
>   "Seline" de §10 (2026-08-12) y la **reconstrucción onboarding-first**
>   (ce66e17, 2026-08-14) que retiró el command center.
>
> **No enviado / retirado**: `/inicio` (command center de widgets),
> `/inicio/catalogo`, `/w/[widgetId]` y `/ajustes` existieron entre F4 y
> ce66e17 y hoy son redirects a `/` (`frontend/next.config.mjs`). La IA que
> se envió **difiere de §4**: no hay grid de widgets ni picker; hay seis vistas
> fijas — Movimientos (`/`), Categorías, Fijos, Pronóstico, Precios,
> Documentos — más el menú "Lecturas" → `/workspace` (`components/AppShell.tsx`).
> Fijos e ingresos etiquetados persisten en `localStorage`, no en el backend.
>
> **Decisión revertida**: §8.1 "web only, Expo out of v1" se revirtió el
> 2026-08-14 con `docs/custody-plan.md` (el teléfono es el custodio; F1
> enviado en 192050a). Ver la nota en §8.
>
> Lo que sigue se conserva como registro histórico de la propuesta original.
> Companion: `docs/carguito-pipeline.excalidraw` (cómo funcionaba el sistema
> cuando se escribió).

## Context

Carguito today is a display layer over a Flask API: six pages, three of which are
essentially static, all reading a handful of bespoke analytics endpoints. The
home screen ("Resumen") shows three totals and a category breakdown.

Two things are wrong with that, and they are different kinds of wrong.

**Product-wrong.** A summary of totals doesn't tell anyone anything. The user
doesn't want "you spent $42,000"; they want to answer specific questions —
*am I on pace this month? which subscriptions am I still paying for? how much
of my spending can I deduct? how much cash am I burning?* Each question is a
different lens on the same transactions. The home screen should be a
**command center** the user composes from those lenses, not a fixed summary.

**Correctness-wrong.** Several numbers the app already shows are wrong, and
the redesign would make them *more* prominent. Details in §2. Building nine
new metrics on top of a double-counting fact table means shipping nine wrong
answers instead of three.

This plan covers both, plus the visual redesign (Brex-derived system,
ApexCharts) and a later Financial Advisor surface.

---

## 1. The core question: how to shape one dataset into many perspectives

**Recommendation: a closed, declarative metric registry with a generic query
endpoint — not one endpoint per metric, and not a full DSL.**

### Why not one endpoint per metric

That's what exists. Adding a metric today costs five files: a DTO in
`application/dtos/analytics.py`, a method on the `CubeReader` Protocol in
`application/ports/outbound/cube.py`, an implementation in
`adapters/outbound/cube/duckdb_cube.py`, a serializer in
`adapters/inbound/http/serialization.py`, and a route in
`adapters/inbound/http/blueprints/analytics.py`. Multiply by nine metrics,
then by period/grouping/filter variants.

The deeper problem: a **user-composed** dashboard needs metric metadata to
exist *as data* — a catalog the picker can enumerate, with declared
parameters, units, and requirements. Bespoke endpoints have nowhere to put
that.

### Why not a full DSL

Cube.js/MetricFlow-style arbitrary expressions means owning a query compiler,
an injection surface, and a per-expression permission model. For ~12 metrics
over one fact table — in an app where `auth_disabled=True` and multi-tenancy
has never been exercised — that's liability without leverage.

### The design

**Closed.** The client never sends SQL or expressions. It sends a metric id
plus dimensions/filters drawn from a declared vocabulary:

```json
POST /api/metrics/query
{ "period": {"start": "2026-01-01", "end": "2026-07-31"},
  "queries": [
    {"key": "w1", "metric": "spend_by_category", "dimensions": ["category"]},
    {"key": "w2", "metric": "cash_withdrawn"},
    {"key": "w3", "metric": "invoiceable_split"} ] }
```

Only whitelisted identifiers reach SQL; values are always bound parameters.
Anything outside the vocabulary is a 400.

**Batched.** The command center renders N widgets; N round trips per period
change is unacceptable. One request, results keyed by widget. Failures are
**per-query** — one broken metric returns an error object and the other
eleven still render.

**Bimodal.** This is the part a naive semantic layer gets wrong here. The nine
metrics split cleanly:

| Kind | Metrics | Executor |
|---|---|---|
| Aggregation (measure × dimension × filter) | spend-by-category, accumulated spend, cash withdrawn, tag totals, lifetime in/out | SQL compiler |
| Computed (a Python function) | investment projection, anomalies, recurrence, modeled returns | Resolver |

A SQL-only layer cannot express "project a balance forward at an annual rate"
(a function of two user-entered scalars) or "score this transaction for
anomaly". If you build SQL-only you bolt bespoke endpoints back on for those
and you're back where you started. So the catalog holds **both kinds behind
one envelope** — the client can't tell which is which, which means a metric
can migrate from resolver to SQL later with no client change.

### The property that pays for the whole abstraction

Default filters attach to the **measure**, not the metric:

```python
Measure(
    name="expense_amount", column="amount", agg="sum",
    default_filters=[
        Eq("is_transfer", False),          # credit-card payments aren't spend
        Eq("excluded_from_stats", False),  # deduped rows
        Eq("is_primary_in_group", True),
    ],
)
```

"Exclude transfers" is declared **once**. With nine bespoke endpoints, nine
places have to remember it, and one won't. Given §2, this is most of the
justification on its own.

### Where it lives (hexagonal placement)

```
domain/metrics/                      NEW — pure; no SQL, no Flask, no DuckDB
  spec.py        MetricSpec, Measure, Dimension, FilterDef, Grain
  catalog.py     METRIC_CATALOG — the declarations
application/ports/outbound/metrics.py   NEW — MetricEngine, MetricResolver
application/use_cases/metrics.py        NEW — RunMetricQuery, GetMetricCatalog
adapters/outbound/cube/duckdb_metric_engine.py   NEW — semantic name → column → SQL
adapters/outbound/metrics/resolvers/    NEW — projection, anomaly, recurrence
adapters/inbound/http/blueprints/metrics.py      NEW
```

The catalog is **domain** because "invoiceable spend excludes transfers" is a
business definition. It stays pure by referencing *semantic* names
(`measure="expense_amount"`); the adapter owns the name→column mapping. Same
shape as `domain/services/categorization.py`, which receives reference data
rather than reaching for a repository.

Note this also fixes an existing violation: `blueprints/analytics.py:28` and
`:37` call `get_container().cube.*` directly, skipping the application layer
entirely.

---

## 2. Correctness first — the numbers are currently wrong

These are not hypothetical. Each one makes a headline number wrong today.

**Double-counting: CFDI + bank statement.** Upload a Walmart CFDI *and* the
Banamex PDF covering it and Walmart is counted twice.
`adapters/outbound/parsing/sat_cfdi.py` emits a `ParsedTransaction`, which
becomes a real transaction row alongside the bank charge for the same money.
The only dedup that exists is file-level `sha256` (`process_file.py:75`).

*Fix, structural rather than filtered:* **stop creating transactions from
CFDIs.** The bank line is the money movement; the CFDI is *evidence*. A CFDI
upload becomes a `cfdi_documents` row and gets attached to an existing
transaction. Cash purchases with an invoice and no bank line become "orphan
CFDIs" the user can promote manually — never auto-promoted, since that
re-creates the double-count.

**Double-counting: credit-card payments.** "PAGO TC" on the debit statement is
an expense, *and* the card's own charges are expenses. Same money, twice. Needs
an `is_transfer` flag excluded by default from every spend measure.

**Double-counting: overlapping statements.** A re-exported PDF has different
bytes, so the file hash doesn't catch it. Needs a per-transaction
`fingerprint = sha256(user | account | date | abs(amount) | normalized description)`
with a ±1 day window. Duplicates are marked, not dropped — dropping makes
statement deletion lossy.

**Sign convention is unenforced.** `parse_amount` (`parsing/base.py:34`)
returns negatives for `-45.50` and `(99.00)`, while `infer_tx_type` classifies
direction independently by Spanish keyword and defaults to expense. Nothing
reconciles them. `TextStatementParser` happens to call `abs()`; `SatCfdiParser`
does not. A negative-signed expense therefore *reduces* `total_expense` in the
cube's `SUM(CASE WHEN tx_type='expense' THEN amount ...)`.

*Contract:* `amount` is always a non-negative magnitude; `tx_type` alone
carries direction; sign is reintroduced at aggregation as `signed_amount`.
Enforced in three places — the domain entity **raises** (not `abs()` — silent
absing hides parser bugs), the parser returns `(magnitude, sign_hint)` feeding
`infer_tx_type`, and a `CHECK (amount >= 0)` in the migration.

**Mixed-currency sums.** `duckdb_cube.py:190` adds MXN and USD together.

**CFDI types P and N are booked as expenses.** `sat_cfdi.py:43` sends
everything that isn't `E` to the else branch — so a *nómina* (payroll) CFDI,
which is **income**, is recorded as money going out.

### Blocking prerequisite

**There is no migration tooling.** `Database.create_all()` is the entire schema
story and never ALTERs. Meanwhile `models.py` and `supabase_setup.sql` have
already drifted (merchant labels, `created_at`, FKs, RLS). Nothing below ships
until Alembic exists, `models.py` becomes the single source of truth, and
`supabase_setup.sql` is demoted to auth + RLS only — with **RLS as a
dialect-guarded migration**, so new user-owned tables can't reach Supabase
unprotected.

---

## 3. Metric feasibility — blunt

| # | Metric | Status |
|---|---|---|
| 2 | Spend by category | **Works today.** One fix: stop hardcoding `tx_type='expense'` so income breaks down too |
| 7 | Accumulated spend to date | **Works today** — running SUM |
| 1 | Recurrent spends | **Works, low quality.** Groups by full description string, so `OXXO SUC 4412` ≠ `OXXO SUC 8891`; threshold is 2 occurrences; no amount-stability check; expenses only |
| 9 | Lifetime in vs out | **Arithmetically trivial, currently wrong** — every card payment inflates both sides. Do not ship before transfers are flagged |
| 4 | Cash withdrawn | **~1 day.** Derivable from descriptions, but must be a **flag**, not a category keyword. Split out `comision retiro` — the fee isn't withdrawn cash |
| 8 | Unusual transactions | **No new ingest; needs a model.** Start with an explainable rule ensemble (z-score per merchant, first-time merchant above p95, same merchant+amount twice in 24h), not ML. Every score needs a human-readable reason. Tune for **precision** — one false fraud alert and the feature gets disabled |
| 3 | Invoiceable vs not | **Largest chunk, and the real differentiator.** Full CFDI parser + `cfdi_documents` + matcher. Critical: *invoiceable ≠ invoiced ≠ deductible*. A CFDI-backed Netflix sub is invoiced but not deductible. Three separate fields |
| 5 | Tag groups — totals | **Easy** — CRUD + bridge table |
| 5 | Tag groups — **returns** | **Not computable.** Tagged transactions give you *contributions*, not market value. Show contributions plus a *modeled* return from the account rate, labelled as modeled. Do not compute an IRR from bank outflows and call it a return |
| 6 | Investment projection | **Needs user input.** A balance and a rate cannot be derived from statements (the parsers read no balances at all, and rates never appear). Build account/balance/rate CRUD first. The math already exists in `domain/services/forecasting.py` |

**Financial Advisor** (new): cohort placement needs population data. Two honest
paths — benchmark against public **INEGI ENIGH** household-expenditure deciles
(static reference data, shippable, defensible), or cohort-vs-our-own-users
(needs scale + a consent story). Do the former. Worth noting
**lifestyle-inflation detection is computable today**: trailing-3-month vs
prior-12-month category means, plus price-tier detection once CFDI line items
land.

Also: the current dashboard ships a **fake** "Carguito AI Insight" card that
string-interpolates `top_category`. Placeholder intelligence is a trust cost —
build it or delete it.

---

## 4. Frontend — the command center

### Information architecture

`/dashboard` dies. So do `/spending` and `/forecasts` as top-level pages —
each becomes the expanded view of a widget. This stops the nav growing one
entry per analysis.

```
/inicio               command center (composed widget grid)
/inicio/catalogo      widget picker (Sheet over /inicio)
/w/[widgetId]         widget detail — deep-linkable, own filters
/movimientos          transactions: real filters, pagination, tagging
/documentos           statements + upload
/ajustes              settings (currently 100% static, saves nothing)
```

Four nav items, Spanish throughout. The app currently mixes Spanish and
English within single screens. Permanent redirects from the old paths cost six
lines in `next.config.mjs`.

### The widget system

One registry, `src/widgets/catalog.ts`. Adding a metric is one file in
`src/widgets/defs/` plus one line in the registry; nothing else knows metric
names.

```ts
type WidgetDef<T> = {
  id: string; title: string; blurb: string;
  group: "Gasto" | "Ingreso" | "Patrimonio" | "Fiscal" | "Riesgo";
  sizes: WidgetSize[];              // sm=4 / md=6 / lg=12 cols
  requires: Requirement[];          // "transactions" | "months:3" | "cfdi" | "tags" | "balance"
  quality?: "estimate" | "beta";
  load: (ctx) => Promise<Result<T>>;
  Body: FC<{data: T; size: WidgetSize}>;
};
```

**States are the whole design.** Every metric can legitimately have no data
(the user just onboarded) and four of nine are backend-blocked. `load()`
returns a discriminated union and `WidgetFrame` switches on it:

- **loading** — skeleton at the exact final geometry, no spinner
- **empty** — *never render `$0`.* The current dashboard does exactly this:
  `mxn(summary?.total_expense ?? 0)` shows a confident `$0` when the backend is
  down. A zero is a claim about someone's finances; absence of data isn't
- **insufficient** — show partial data plus "Necesitas 3 meses. Llevas 1."
- **estimate/beta** — full render plus a header tag explaining the heuristic.
  Mandatory for cash withdrawals and anomalies
- **error** — the frame survives; one card failing never blanks the grid

**The picker shows locked widgets, dimmed, with their unlock condition** —
"Necesita una factura del SAT", "Necesita que etiquetes movimientos" — each
linking to the action that unlocks it. That turns the catalog into the
onboarding surface instead of hiding half the product from a new user.

**Persistence:** `localStorage` behind a `useLayout()` hook for v1 (there's no
auth, so a server-side layout would key off the dev user and be a lie). Move to
`profiles.ui_preferences` once auth lands — one file changes.

**Cut:** free 2-D resize (every chart would need to look right at every aspect
ratio; the payoff is decoration) and drag-and-drop grid libraries. Ship
declared sizes from the `⋯` menu and reorder via `@dnd-kit/sortable` (~12kb,
keyboard-accessible) if anyone asks.

**One mechanical gotcha:** every grid child needs `min-w-0`. CSS grid items
default to `min-width: auto` and an ApexCharts SVG inside one won't shrink
below its initial render width — the grid overflows the first time the window
narrows. Bake it into `WidgetFrame`'s root.

---

## 5. Charts — ApexCharts

`react-apexcharts@^1.4` (the React 18 line) + `apexcharts@^3.54`. ApexCharts
touches `window` at import, so **`dynamic(..., {ssr:false})` is mandatory**, not
a nicety — a static import breaks `next build`. One shared wrapper so the
chunk is shared, one `theme.ts` deep-merged into every chart.

Recharts and both existing chart files get deleted (~95kb gzipped). Note
`DistributionChart` isn't a chart at all today — it's divs with `width: X%`.

| Widget | Chart |
|---|---|
| Gastos recurrentes | Mixed column+line: committed spend per month, line = active subscription count |
| Gasto por categoría | Treemap (widget) → mixed horizontal bar + prior-period markers (detail) |
| Gasto acumulado | Mixed column+line: daily columns, ember cumulative line, dashed last-month pacing. Best widget in the set — answers "am I on track" instantly |
| Efectivo retirado | Mixed column+line; heatmap (weekday × week) in detail |
| Facturable vs no | radialBar at sm; 100% stacked column + MXN line at md |
| Grupos/etiquetas | Mixed column+line per group; **small multiples**, never six series in one chart |
| Proyección | Mixed area+line+column with a goal annotation |
| Inusuales | **No chart at sm** — a list of 3 flagged transactions with "¿Es tuyo?". Charts don't help you spot fraud; scatter in detail |
| Entradas vs salidas | Mixed column+line, pattern-filled expense columns, cumulative net line |

Single numbers with a trend are not charts — `StatTile` with a 40px Apex
sparkline.

### The one-accent vs many-categories conflict

The brand permits exactly one accent. Categorical charts appear to need many
hues. Resolution: **stop using hue as the categorical channel.**

- **Nominal categories → neutral ramp ordered by value, Ember for focus.**
  `["#15191e","#2f343b","#4a4f57","#60646c","#767a83","#8b8d98"]` — six steps,
  each ≥3:1 on Paper, adjacent steps ~1.35× apart. Position and order carry
  identity; Ember marks the one series the widget is *about*. Cap at 6 series +
  "Otros" with drill-in — nobody reads a 14-slice legend anyway.
- **Quantitative encodings → Ember tint ramp.** Treemap and heatmap encode
  magnitude, not identity. `#ff5900 → #ff8c4d → #ffb083 → #ffd2b8 → #ffeade` is
  one colour, is the brand colour, and is the textbook-correct encoding for
  continuous value. Tile text flips to Ink below the third step.
- **Two-series comparison → texture, not hue.** Ingresos vs gastos = Abyss
  solid vs Graphite `pattern.style: "slantedLines"`. Colour-blind safe, prints
  in greyscale, adds zero colours. Projections use `stroke.dashArray`, not
  colour, to mean "not real yet".
- **Semantic red/green, narrowly.** Positive/negative deltas in transaction
  lists only, at text scale, `#0f7a4d` / `#b3261e` (both >4.5:1). Never chart
  fills, never backgrounds. The app already leans on `text-emerald-600` in four
  places; contain it in the token file rather than letting it spread.

### Contrast finding that conflicts with the style guide

Computed against the WCAG formula:

| Pair | Ratio | Verdict |
|---|---|---|
| Ember `#ff5900` on Paper | **3.13:1** | OK for UI/graphics (3:1), **fails** body text (4.5:1) |
| **White on Ember** | **3.13:1** | **Fails AA for button labels** at 14–16px |
| **Ink on Ember** | **6.68:1** | Passes |
| Graphite on Paper | 5.9:1 | Correct body token |
| Steel on Paper | 3.30:1 | Labels ≥18.66px only — not 12px captions |
| Mist on Paper | 1.93:1 | Hairlines and gridlines only, never a data mark |

The style guide specifies white text on the Ember button. That fails AA at
normal button sizes. **Recommendation: Ink text on Ember** — it passes at
6.68:1 and, as it happens, looks more like the precision-instrument register
the guide is after. Flagged as a deliberate deviation for sign-off.

---

## 6. Design system

`src/design/tokens.ts` as the single source of truth, imported by both
`tailwind.config.ts` (Tailwind compiles TS configs natively) and the Apex
theme, so charts and CSS cannot drift.

Tailwind v3.4 — **not** v4; the repo is on 3.4 and the style guide's `@theme`
block is v4 syntax.

**The load-bearing trick:** bake tracking into the `fontSize` scale so the
"-0.01em ≤24px / -0.02em at 36 / -0.03em at 72" rule is mechanical rather than
remembered.

```ts
fontSize: {
  "display-lg": ["72px", { lineHeight: "1.0",  letterSpacing: "-0.03em" }],
  "title-lg":   ["36px", { lineHeight: "1.15", letterSpacing: "-0.02em" }],
  "body":       ["15px", { lineHeight: "1.5",  letterSpacing: "-0.01em" }],
  "metric":     ["32px", { lineHeight: "1.1",  letterSpacing: "-0.02em" }],
}
```

Also: delete `colors.brand` and set `boxShadow: { none: "none" }` in the same
commit. That turns the 21 `brand` references and every `shadow-sm` into
visible errors instead of silent violations.

`globals.css` gains `font-feature-settings: "calt" 0, "liga" 0, "tnum" 1` —
tabular numerals matter in a finance app; proportional digits make columns of
pesos wobble.

**Fonts.** `layout.tsx` currently loads **no font at all** — the entire app
renders in the system UI stack. Adding `next/font` Inter is the single most
visible improvement available. Flecha isn't freely available; substitute
**Instrument Serif** (high contrast, narrow, display-oriented, on Google
Fonts). Use it on the landing page and empty-state heroes only — a serif inside
a dense dashboard reads as a mistake.

**Components** (`src/components/ui/`): Button, Card, WidgetFrame, StatTile,
Tag, Input/Field, SearchInput, Table (+Empty/Skeleton/Pagination), Tabs, Sheet,
Modal, EmptyState, Toast, Skeleton, PageHeader, Slider. Four hand-rolled tables
and one `window.confirm()` get replaced.

---

## 7. Sequencing

Ordered so correctness precedes surface area. Each step is independently
shippable. Backend and frontend tracks run in parallel.

### Backend

| # | Step | Ships |
|---|---|---|
| B0 | **Alembic + schema convergence + RLS migration** | Nothing visible. Blocks everything |
| B1 | Sign contract, currency guard, backfill (logging how many rows were wrong) | Existing numbers stop being wrong |
| B2 | Delete dead rollups; add `rebuild_for_user` + admin endpoint | Faster uploads; cube becomes disposable — prerequisite for every later backfill |
| B3 | Metric engine skeleton; port the 3 working metrics to the catalog | Home renders 3 real widgets in one round trip |
| B4 | Dashboards CRUD, params validated against the catalog | Command center is user-composed — validates the abstraction early |
| B5 | `PATCH /api/transactions/{id}` + `category_source='user'` | Users can fix bad categorization. There is currently no way to correct anything |
| B6 | Tags + bridge table + `meta.overlapping` | Metric 5 totals |
| B7 | Transfer + cash-withdrawal flags, backfill | Metrics 4 and 9; every other number gets more correct |
| B8 | Accounts, balance and rate time series | Metric 6 |
| B9 | CFDI v2 parser; stop creating transactions from CFDIs; fix types P/N/T | CFDI double-count gone |
| B10 | `transaction_links`, matcher, review queue, fingerprint dedup | Metric 3 |
| B11 | Recurrence v2 (merchant_key grouping, amount stability, income support) | Metric 1 trustworthy |
| B12 | Anomaly rule ensemble with reasons | Metric 8 |
| B13+ | Line-item price trends, INEGI benchmarks, advisor | Later |

`rollup_monthly`/`rollup_category` are worth calling out: they're **never
read**, and `refresh_rollups(user_id)` **ignores its argument**, rebuilding
every user's rollups on every upload and every delete.

**Balances are a time series** (`account_balances`), not a column on
`accounts` — metric 6 needs "balance as of a date", and a mutable scalar would
be immediately wrong and unauditable.

**Tags in the cube go both ways:** a `tag_ids VARCHAR[]` column for filtering
(`list_contains`, no join) and a bridge table for grouping. When tag is a
*dimension*, `meta.overlapping = true` — a transaction with 3 tags appears in
3 rows and the sums don't partition the total. Without that flag you ship a
pie chart summing to 240%.

**Keep DuckDB, but make it provably disposable.** Single-writer/single-file
means one process today (`main.py` already defers bootstrap to dodge the
reloader taking the lock). `rebuild_for_user` plus the `MetricEngine` port
means switching to Postgres later touches one adapter file. Answer the
storage question by making it cheap to change your mind.

### Frontend

| # | Step | Ships |
|---|---|---|
| F0 | `tokens.ts`, tailwind config, `globals.css`, `next/font` | Whole app changes colour and type |
| F1 | UI primitives + a dev-only `/_kitchen-sink` route | Nothing wired yet |
| F2 | Apex wrapper, theme, formatters; port ProjectionChart as the pilot | Validates SSR, fonts-in-SVG, MXN, grid sizing on one chart before writing nine |
| F3 | Shell: sidebar, layout, Spanish nav, `useProfile()`, redirects | New chrome |
| F4 | `src/widgets/`, WidgetFrame, grid, picker, `/w/[id]` — **4 ready metrics** + honest locked states | The command center |
| F5 | Retire `/spending` and `/forecasts` into widgets | Two fewer pages |
| F6 | `/movimientos` filters + pagination, `/documentos`, `/ajustes` actually saving | The rest |
| F7 | Widgets for B6–B12 as they land — one file each | Remaining metrics |

**Migration approach: incremental, not big-bang.** The surface is small (21
`brand` refs, 17 `.card` usages, ~75 `slate-*` utilities across 12 files) and
four of nine metrics are backend-blocked — a rewrite would spend its budget
re-skinning pages whose data model is about to change.

**What breaks:** `slate-*` utilities still resolve (they're Tailwind defaults)
and will look wrong next to the new neutrals without erroring — grep after
each phase, don't trust the build.

---

## 8. Decisions (resolved)

1. **Scope: web only.** The Expo app is out of v1. ApexCharts is DOM/SVG and
   cannot run in React Native, so mobile would need a different chart library
   behind the shared tokens whenever it happens.

   > **Revertido el 2026-08-14.** `docs/custody-plan.md` hace del teléfono el
   > custodio del archivo (extracción en el dispositivo, envío sellado a
   > `POST /api/ingest/extracted`, `statements.source = "device"`); F1 se envió
   > en 192050a y el parser de Banco Azteca + hardening en 8b4247f
   > (2026-08-19). La app móvil sigue sin distribuirse y la web sigue
   > aceptando el PDF (ruta transitoria), así que hoy conviven ambas rutas.
   > La reversión no se había registrado aquí hasta la auditoría del
   > 2026-09-05.
2. **Ink text on the Ember button.** White measures 3.14:1 and fails AA at
   button sizes; Ink is 6.68:1. Deliberate deviation from the style guide.
3. **No auth in v1.** Validating the product hypothesis comes first. Widget
   layouts live in `localStorage` behind a `useLayout()` hook so the move to
   `profiles.ui_preferences` is one file. Supabase auth is v2.

   > **Vigente al 2026-09-05**, y ya es el bloqueo #1 para cualquier URL
   > pública: `AUTH_DISABLED=true` en `backend/.env.example`, el frontend no
   > envía `Authorization` y `landing/` manda a la app desde "Comenzar".
   > Ver `docs/audit/2026-09-05/historia.md`.
4. **All backend correctness work is in v1** — B0 through B12.

### Sequencing note given (3) + (4)

"Validate the hypothesis now" and "all the correctness work" pull in opposite
directions, so the order matters more than usual. **B9/B10 (CFDI parser +
reconciliation) is the long pole** — it's the largest single chunk in the plan
and the command center does not depend on it.

Recommended: get to a testable command center at **B0–B4 + F0–F4**, then
continue correctness (B5–B8, B11, B12) while the hypothesis is being tested,
and land B9/B10 last. Everything still ships in v1; the hypothesis just isn't
gated on the hardest part.

### v2 candidate: on-device PDF processing

Recorded from discussion. Technically feasible — Apple Vision and Google ML Kit
both do on-device Spanish text recognition. Three real obstacles:

- PDFs must be rasterized to images first (iOS PDFKit / Android `PdfRenderer`
  behind a custom Expo config plugin); ML Kit and Vision don't take PDFs.
- Most bank e-statements have a text layer, so the on-device equivalent of the
  current fast path is *text extraction*, not OCR. OCR is only the fallback.
- **The dominant cost is duplicating the parsers.** The template classifier,
  bank parsers, and `CategorizationService` are Python; going fully on-device
  means a second TypeScript implementation kept in sync forever.

Middle path: extract text on-device, upload the *text* rather than the PDF.
The raw file never leaves the phone (already the stated architecture), the
payload drops from MB to KB, and parsing stays in one language server-side.

## 9. Verification

- **Backend:** `cd backend && source .venv/bin/activate && python -m pytest tests/ -q`
  (22 tests today). Each metric needs a golden-data test; the sign fix needs a
  regression test with a negative-signed expense; dedup needs a test uploading
  the same purchase as both CFDI and bank line and asserting it counts once.
- **Frontend:** `npx tsc --noEmit && npx next build`. There is no test tooling
  in the frontend today — worth adding Playwright for the command center
  (add/remove widget, layout persists across reload, one failing widget doesn't
  blank the grid).
- **End to end:** backend on `0.0.0.0:8000`, `npm run dev`, upload a real
  Banamex PDF plus a CFDI for a purchase on it, and confirm the total counts
  it once.

---

## 10. Amendment (2026-08-12) — Seline restyle

§5 and §6 above describe the Ember system as shipped in F1–F7. The visual
layer was replaced; the *architecture* of §6 (tokens as single source of
truth, tracking baked into the scale, Apex reading the same file) is
unchanged and is what made the swap a token edit plus a rename sweep rather
than a rewrite.

**What changed**

| Was | Now | Why |
|---|---|---|
| Paper `#ffffff` page background | Canvas `#fafaf9`, Paper reserved for cards | Warm stone reads as paper, not screen; white is now an elevation step, not the ground |
| Ember `#ff5900` | Signal `#3ba6f1` / Edge `#3398e1` / Wash `#c1e1f7` | One accent still, different accent |
| `graphite` / `pewter` / `steel` | `graphite` `#78716c` + `ash` `#a8a29e` | Two recessive text values, not three — a third step only invites 3:1 captions |
| `abyss` / `carbon` | `soot` `#1c1917` | One dark surface |
| Headings at 600 | Display face at **400** | Weight-400 at large sizes is the brand voice; emphasis comes from size and the highlight span |
| Body 15px / 1.5 | Body **14px / 1.64** | The dominant UI rhythm of the reference system |
| `title-lg` 36px | 32px, `display` 52px replaces `display-md` 56px | Matches the reference scale |
| Buttons/tags `12px` radius | Pill `9999px`; inputs `6px`; cards `10px`; panels `16px` | `rounded-control` is now genuinely a pill, so every non-button use of it was reclassified |
| `boxShadow: { none, float }` | `subtle` / `card` / `chip` / `float` | Cards get a 16px-blur whisper on top of the hairline; `float` is still one element per screen |
| Instrument Serif display | **Inter Tight** | Roobert is a commercial licence; Inter Tight is the named substitute |

**Contrast findings that conflict with the new style guide** (same posture as
§5's finding against the old one):

| Pair | Ratio | Verdict |
|---|---|---|
| Signal `#3ba6f1` on Canvas | 2.36:1 | Fills, icons, borders only — never text |
| **White on Signal** | **2.36:1** | **Fails AA.** The guide specifies it; we do not ship it |
| **Ink on Signal** | **5.60:1** | Passes — this is the button label |
| Edge `#3398e1` on Wash `#c1e1f7` | 4.51:1 | Passes — the highlight span, and the only place the accent is text |
| Graphite on Canvas | 4.62:1 | Passes — body, labels, captions |
| Ash on Canvas | 2.42:1 | Decorative and disabled only |

**Deliberate deviation from the guide.** `positive` / `negative` survive, as
`#15704a` / `#a8322a`. The guide forbids a second accent; in a ledger the sign
of a number is information, not decoration, and rendering a loss in the same
grey as a gain costs the user more than the restraint buys. Both are
warm-shifted to sit inside the stone palette, and both stay scoped to deltas
and amounts at text scale — never a chart fill, never a background.

**Home screen states.** `/inicio` now branches on `useCapabilities()`:

1. probing → skeleton, *not* the onboarding hero (flashing "upload your first
   statement" at someone with three years of data is worse than a beat of grey);
2. probe succeeded and `!capabilities.transactions` → `<FirstStatement>`;
3. otherwise → the widget grid, which keeps its own "board is empty" state for
   an account that *has* data but no widgets.

A probe *error* falls through to the grid. An unreachable backend is not a
claim that the account is empty.
