"""Store listings found on the web, read into prices per litre and per kilo.

The second reference source, next to Profeco. The two differ in what they are
evidence *of*: a survey row is a price somebody observed on a shelf on a date; a
listing is a price a store's page showed today. Both are worth having and they
must never be confused, so every quote from here says "listado en línea" and
carries the URL it was read from.

Two calls, deliberately separate from the one that writes the answer:

1. ``BraveSearch`` finds store pages (and only store pages) for the product.
2. The configured model reads the snippets and returns **only JSON**. It is a
   reader, not a searcher and not an oracle: it may report a price that appears
   in a snippet and nothing else, and everything it returns is validated here --
   the URL must be one it was handed, the size must parse, the unit must be one
   we compare by. Rejected rather than repaired, because a repaired listing is a
   number the user can no longer check against the page.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from statistics import median

from ....application.ports.outbound.chat import (
    ChatMessage,
    ChatOptions,
    ChatPort,
    json_schema_format,
)
from ....application.ports.outbound.references import PriceQuote, UnitQuote
from .brave import SearchHit
from .units import money, rank_per_unit, to_base

logger = logging.getLogger(__name__)

#: One listing, as the request's ``response_format`` pins it. ``size`` may come
#: as a number or as text ("1.5 kg"); ``_to_units`` parses either.
_LISTING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["listings"],
    "properties": {
        "listings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "url", "store", "product", "size", "unit", "price",
                    "promo", "membership", "online_only",
                ],
                "properties": {
                    "url": {"type": "string"},
                    "store": {"type": "string"},
                    "product": {"type": "string"},
                    "size": {"type": ["number", "string", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "price": {"type": ["number", "null"]},
                    "promo": {"type": "boolean"},
                    "membership": {"type": "boolean"},
                    "online_only": {"type": "boolean"},
                },
            },
        }
    },
}

OPTIONS = ChatOptions(temperature=0, response_format=json_schema_format("listings", _LISTING_SCHEMA))


_TTL_SECONDS = 3600.0
_MAX_HITS = 8
_PER_UNIT_EACH = 4

SYSTEM = """\
Lees resultados de búsqueda de tiendas mexicanas y extraes precios de productos.

Te dan una lista de resultados, cada uno con URL, título y texto. Responde SOLO
con un objeto JSON, sin texto alrededor, cuya clave "listings" es un arreglo con
un elemento por cada producto cuyo precio aparezca LITERALMENTE en el texto de
ese resultado:

{"listings": [{"url": "...", "store": "nombre de la tienda",
  "product": "nombre tal como aparece", "size": 7, "unit": "l", "price": 169.9,
  "promo": false, "membership": false, "online_only": false}]}

Reglas:
1. "url" debe ser exactamente una de las URLs que te dieron. Nunca inventes una.
   Un resultado da UN objeto: el producto del título de esa página, con el
   precio al que la tienda lo vende hoy. Si la página muestra un precio de
   oferta y uno regular, reporta el de oferta con "promo": true. Ignora los
   precios de "otros vendedores" o de productos relacionados.
2. Solo precios que estén escritos en el texto. Si un resultado no muestra
   precio, no lo incluyas. Si ninguno lo muestra, responde {"listings": []}.
3. "unit" es "l", "ml", "kg", "g" o "pz" (pieza). "size" es el número que
   acompaña a esa unidad en el nombre del producto. Si el tamaño no aparece,
   no incluyas el resultado.
4. "promo" true si el precio es de oferta o requiere comprar varias unidades;
   "membership" true si requiere membresía (Sam's, Costco); "online_only" true
   si el texto dice que es precio exclusivo en línea.
5. Nada de explicaciones. Solo el JSON."""


class WebPriceReference:
    """Implements :class:`PriceReference` over web search plus model extraction."""

    def __init__(
        self, search, chat: ChatPort, *, engine: str = "Brave", fallback: ChatPort | None = None
    ) -> None:
        # `search` is anything with `.available` and `.search(query) -> [SearchHit]`:
        # Brave (snippets) or Firecrawl (rendered pages). The reader is the same.
        self._search = search
        self._chat = chat
        # A second reader for when the first is rate-limited. Free-tier models
        # refuse in bursts, and the pages this call carries were paid for in
        # credits; a second model is cheaper than a second render.
        self._fallback = fallback
        self._engine = engine
        self._cache: dict[str, tuple[float, list[PriceQuote]]] = {}

    @property
    def available(self) -> bool:
        return self._search.available and self._chat.available

    @property
    def source_label(self) -> str:
        return f"listados en línea ({self._engine})"

    def lookup(self, terms: Sequence[str], *, hint: str = "") -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        for term in terms:
            # "detergente 7 l": the size is what turns a category page into a
            # product page, and a product page is the only one with a price.
            cleaned = " ".join(f"{term} {hint}".strip().lower().split())
            if cleaned:
                quotes.extend(self._for_term(cleaned))
        return quotes

    def _for_term(self, term: str) -> list[PriceQuote]:
        hit = self._cache.get(term)
        if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
            return hit[1]
        quotes = self._fresh(term)
        self._cache[term] = (time.monotonic(), quotes)
        return quotes

    def _fresh(self, term: str) -> list[PriceQuote]:
        hits = self._search.search(f"{term} precio")[:_MAX_HITS]
        if not hits:
            return []
        listings = self._extract(hits)
        units = _to_units(listings, {h.url for h in hits})
        if not units:
            return []
        prices = [u.price for u in units]
        cheapest = min(units, key=lambda u: u.price)
        dearest = max(units, key=lambda u: u.price)
        return [
            PriceQuote(
                term=term,
                kind=f"{term} (listados en línea)",
                observations=len(units),
                median=Decimal(median(prices)).quantize(Decimal("0.01")),
                low=cheapest.price, low_where=cheapest.where, low_label=cheapest.label,
                high=dearest.price, high_where=dearest.where,
                # The day the page was read, which is all a listing can claim.
                observed=date.today(),
                source=self.source_label,
                per_unit=rank_per_unit(units, each=_PER_UNIT_EACH),
            )
        ]

    def _extract(self, hits: Sequence[SearchHit]) -> list[dict]:
        prompt = "\n\n".join(
            f"URL: {h.url}\nTÍTULO: {h.title}\nTEXTO: {h.snippet[:2500]}" for h in hits
        )
        # Primary, retried once on a rate limit, then the fallback reader.
        # Free-tier models on shared gateways return 429 in bursts, and the
        # rendered pages this call carries were paid for in credits -- throwing
        # them away on the first refusal would be the expensive choice.
        readers = [self._chat, self._chat] + ([self._fallback] if self._fallback else [])
        for i, reader in enumerate(readers):
            if i == 1:
                time.sleep(3)
            try:
                answer = "".join(
                    reader.stream(
                        system=SYSTEM,
                        messages=[ChatMessage(role="user", content=prompt)],
                        options=OPTIONS,
                    )
                )
                return parse_listings(answer)
            except Exception as exc:  # pragma: no cover - never load-bearing
                if "429" in str(exc) and i < len(readers) - 1:
                    continue
                logger.warning("web listing extraction failed: %s", exc)
                return []
        return []


def parse_listings(answer: str) -> list[dict]:
    """The model's JSON, or nothing.

    Tolerates a code fence and either shape -- the bare array older prompts
    asked for, or the ``{"listings": [...]}`` object the schema pins -- and
    nothing else.
    """
    text = answer.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("listings")
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _to_units(listings: Sequence[dict], allowed_urls: set[str]) -> list[UnitQuote]:
    """Validated listings as unit quotes. Every rejection is silent and final."""
    out: list[UnitQuote] = []
    seen: set[tuple[str, str]] = set()
    for row in listings:
        url = str(row.get("url") or "")
        if url not in allowed_urls:
            continue  # a URL the model wrote but was not handed is an invention
        price = money(row.get("price"))
        unit = str(row.get("unit") or "").lower()
        if price is None:
            continue
        if unit == "pz":
            parsed = (Decimal(str(row.get("size") or 1)), "pz")
        else:
            parsed = to_base(row.get("size") or "", unit)
        if not parsed or parsed[0] <= 0:
            continue
        size, base = parsed
        store = str(row.get("store") or "tienda").strip()
        label = str(row.get("product") or "").strip() or store
        key = (label.lower(), store.lower())
        if key in seen:
            continue
        seen.add(key)
        notes = tuple(
            note for flag, note in (
                ("promo", "promoción"), ("membership", "requiere membresía"),
                ("online_only", "solo en línea"),
            ) if row.get(flag) is True
        ) + ("leído hoy, sin fecha de publicación",)
        out.append(UnitQuote(
            per_unit=(price / size).quantize(Decimal("0.01")), unit=base, price=price,
            size=size, where=store, label=label, url=url, notes=notes,
        ))
    return out

