"""Reference prices from Profeco's *Quién es Quién en los Precios*.

The public price survey the Mexican consumer agency runs: real observations,
each at a named store on a named date. That provenance is why this is the source
and not a web search — a scraped listing is a number somebody typed, while these
are the same kind of evidence a ticket is, collected by someone else.

Three things about the endpoint shape the whole adapter:

1. **It answers by search term, not by product.** ``busqueda=leche`` returns
   every milk-ish observation in the city — 15 000 rows, every presentation and
   every chain. So the adapter's real job is not fetching, it is *reducing*:
   15 000 rows become one line per ``tipo_producto``.
2. **It is large and it compresses.** Six megabytes of JSON, 150 KB gzipped.
   The request asks for gzip explicitly, because urllib does not.
3. **It is slow enough to notice** (~2 s) and stable enough to cache. A second
   question about milk in the same city must not pay for it again.

Failure is always an empty list. This is a garnish on an answer that is complete
without it.
"""

from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from statistics import median

from ....application.ports.outbound.references import PriceQuote, UnitQuote
from .units import parse_size

logger = logging.getLogger(__name__)

_ENDPOINT = "https://qqp.profeco.gob.mx/api/precios"

#: Published credentials of the public web client. Not a secret — they ship in
#: every page load of qqp.profeco.gob.mx — but the endpoint refuses without them.
_BASIC = "Basic cXFwd2ViOnFxcHdlYg=="

#: Longer than the ~2 s the survey takes, short enough that a wedged government
#: host cannot hold a chat turn open. On timeout the section is simply absent.
_TIMEOUT = 12.0

#: How many product *kinds* one term contributes to the brief. One: the kind
#: with the most observations is the one the word means to most shoppers, and
#: every extra kind is a paragraph of prices for something the user did not buy.
_KINDS_PER_TERM = 1

#: Kinds with fewer observations than this are dropped: a "median" over three
#: sightings is a number pretending to be a distribution.
_MIN_OBSERVATIONS = 5

#: How many *chains* per base unit each kind reports -- one line each, the
#: chain's cheapest per-litre (or per-kilo) presentation. Five stores is a
#: shopping decision; the full list is a catalogue nobody reads.
_CHAINS_PER_BASE = 5

#: How long a term's answer is reused. The survey publishes on a weekly-ish
#: cadence and the data is already weeks old when it arrives, so an hour of
#: staleness costs nothing and saves every repeat question.
_TTL_SECONDS = 3600.0


class ProfecoPriceReference:
    """Implements :class:`PriceReference` against the QQP survey."""

    def __init__(self, *, city: str, timeout: float = _TIMEOUT) -> None:
        self._city = city
        self._timeout = timeout
        # Process-local and unbounded by design: the key space is the terms this
        # deployment's users actually ask about, which is small, and entries
        # expire. A shared cache would be a dependency this repo does not have.
        self._cache: dict[str, tuple[float, list[PriceQuote]]] = {}

    @property
    def available(self) -> bool:
        return bool(self._city)

    @property
    def source_label(self) -> str:
        return "Profeco (Quién es Quién en los Precios)"

    def lookup(self, terms: Sequence[str], *, hint: str = "") -> list[PriceQuote]:
        # `hint` unused on purpose: the survey is keyed on generic names, and
        # "detergente 7 l" would match nothing where "detergente" matches all.
        quotes: list[PriceQuote] = []
        for term in terms:
            cleaned = term.strip().lower()
            if not cleaned:
                continue
            quotes.extend(self._for_term(cleaned))
        return quotes

    # --- one term ---------------------------------------------------------
    def _for_term(self, term: str) -> list[PriceQuote]:
        hit = self._cache.get(term)
        if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
            return hit[1]

        rows = self._fetch(term)
        quotes = _reduce(term, rows, self.source_label)
        self._cache[term] = (time.monotonic(), quotes)
        return quotes

    def _fetch(self, term: str) -> list[dict]:
        query = urllib.parse.urlencode({"clave_ciudad": self._city, "busqueda": term})
        request = urllib.request.Request(
            f"{_ENDPOINT}?{query}",
            headers={
                "accept": "*/*",
                # urllib does not negotiate compression on its own, and this is
                # the difference between 6 MB and 150 KB on every question.
                "accept-encoding": "gzip",
                "authorization": _BASIC,
                "user-agent": "tomin/0.2 (+https://github.com/tomin)",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                body = json.loads(raw.decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            # Logged, never raised: the answer is complete without the garnish,
            # and a government host having a bad afternoon is not the user's
            # problem to read about in a chat panel.
            logger.warning("profeco lookup for %r failed: %s", term, exc)
            return []

        if not body.get("success"):
            return []
        rows = (body.get("data") or {}).get("productos") or []
        return [r for r in rows if isinstance(r, dict)]


def _reduce(term: str, rows: Sequence[dict], source: str) -> list[PriceQuote]:
    """15 000 observations into at most four lines.

    Grouped by the survey's own ``tipo_producto`` because that is the only
    honest axis available: the rows mix 1-litre cartons with 360-gram tins, and
    nothing in the payload normalises size. Each line therefore says how many
    observations it rests on and names the cheapest one in full — including its
    presentation — so the one figure a reader might act on is checkable.
    """
    kinds: dict[str, list[dict]] = {}
    for row in rows:
        price = _decimal(row.get("precio"))
        if price is None or price <= 0:
            continue
        kinds.setdefault(str(row.get("tipo_producto") or "SIN CLASIFICAR"), []).append(row)

    ranked = sorted(kinds.items(), key=lambda kv: len(kv[1]), reverse=True)
    quotes: list[PriceQuote] = []
    for kind, group in ranked[:_KINDS_PER_TERM]:
        if len(group) < _MIN_OBSERVATIONS:
            continue
        priced = sorted(group, key=lambda r: _decimal(r["precio"]))
        low, high = priced[0], priced[-1]
        quotes.append(
            PriceQuote(
                term=term,
                kind=kind,
                observations=len(priced),
                median=_decimal(median([_decimal(r["precio"]) for r in priced])),
                low=_decimal(low["precio"]),
                low_where=str(low.get("cadena_comercial") or "tienda no registrada"),
                low_label=str(low.get("producto") or kind),
                high=_decimal(high["precio"]),
                high_where=str(high.get("cadena_comercial") or "tienda no registrada"),
                observed=_latest(priced),
                source=source,
                per_unit=_per_unit(priced),
            )
        )
    return quotes


def _per_unit(rows: Sequence[dict]) -> tuple[UnitQuote, ...]:
    """The cheapest presentations per litre and per kilo.

    This is the line the whole reference exists for. A kind-level median mixes
    a 500-gram bag with a 7-litre jug and says nothing a shopper can act on;
    pesos per litre, with the presentation named, is a number they can hold
    against their own ticket. One entry per (product, chain): the survey lists
    every branch, and six rows of the same bottle at six Bodegas is one price.
    """
    best: dict[str, UnitQuote] = {}  # one per chain: its cheapest per unit
    for row in rows:
        name = str(row.get("producto") or "")
        parsed = parse_size(name)
        if not parsed:
            continue
        size, unit = parsed
        price = _decimal(row["precio"])
        chain = str(row.get("cadena_comercial") or "tienda no registrada")
        quote = UnitQuote(
            per_unit=(price / size).quantize(Decimal("0.01")),
            unit=unit, price=price, size=size, where=chain, label=name,
        )
        key = f"{chain}|{unit}"
        if key not in best or quote.per_unit < best[key].per_unit:
            best[key] = quote
    out: list[UnitQuote] = []
    for unit in ("l", "kg"):
        ranked = sorted((q for q in best.values() if q.unit == unit), key=lambda q: q.per_unit)
        out.extend(ranked[:_CHAINS_PER_BASE])
    return tuple(out)


def _latest(rows: Sequence[dict]) -> date | None:
    seen = [d for d in (_day(r.get("fecha_observacion")) for r in rows) if d]
    return max(seen) if seen else None


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None
