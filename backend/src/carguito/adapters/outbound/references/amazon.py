"""Store listings from Amazon México's search page, read without a key.

Why this source, of everything that was tried: it is the only free, no-signup
place on the Mexican web that returns **structured prices over plain HTTP**.
Search-engine snippets carry no prices (retailers put marketing in their meta
descriptions), supermarket product pages are JavaScript shells or refuse bots,
Mercado Libre's API now wants a token, and every search API with a free tier
wants a card. Amazon's results page is server-rendered, with each item's price,
title and link in the markup.

What that buys and what it costs, stated plainly in every quote's labels: this
is a **marketplace**. A third-party seller can list a 7-litre jug at twice the
supermarket shelf price, and the page will show it without blinking. So a quote
from here is "a price someone is asking online today", never "what it costs" --
the model is told so (rule 9) and the user sees the URL to check it themselves.

No model is involved. Parsing is deterministic and a listing that lacks a price,
a size or a product link is dropped rather than guessed.
"""

from __future__ import annotations

import html
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from statistics import median

from ....application.ports.outbound.references import PriceQuote, UnitQuote
from .units import money, parse_size, rank_per_unit

logger = logging.getLogger(__name__)

_ENDPOINT = "https://www.amazon.com.mx/s"
_TIMEOUT = 15.0
_TTL_SECONDS = 3600.0
_MAX_ITEMS = 24
_PER_UNIT_EACH = 4

#: A browser's headers. The page is public and this is what a browser sends;
#: without a real user agent the site returns a robot check instead of results.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-MX,es;q=0.9",
}

_ITEM = re.compile(
    r'<div[^>]+data-component-type="s-search-result"[^>]*>(.*?)'
    r'(?=<div[^>]+data-component-type="s-search-result"|<span class="s-pagination-strip"|$)',
    re.S,
)
_TITLE = re.compile(r"<h2[^>]*>.*?<span[^>]*>(.*?)</span>", re.S)
_WHOLE = re.compile(r'a-price-whole">([\d,]+)')
_FRACTION = re.compile(r'a-price-fraction">(\d+)')
_LINK = re.compile(r'href="(/[^"]*?/dp/([A-Z0-9]{10})[^"]*)"')


class AmazonListingsReference:
    """Implements :class:`PriceReference` over the public search page."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, list[PriceQuote]]] = {}

    @property
    def available(self) -> bool:
        return True

    @property
    def source_label(self) -> str:
        return "listados en Amazon México"

    def lookup(self, terms: Sequence[str], *, hint: str = "") -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        for term in terms:
            cleaned = " ".join(f"{term} {hint}".strip().lower().split())
            if cleaned:
                quotes.extend(self._for_term(cleaned))
        return quotes

    def _for_term(self, term: str) -> list[PriceQuote]:
        hit = self._cache.get(term)
        if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
            return hit[1]
        quotes = build_quote(term, parse_results(self._fetch(term)), self.source_label)
        self._cache[term] = (time.monotonic(), quotes)
        return quotes

    def _fetch(self, term: str) -> str:
        request = urllib.request.Request(
            f"{_ENDPOINT}?{urllib.parse.urlencode({'k': term})}", headers=_HEADERS
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("amazon listings for %r failed: %s", term, exc)
            return ""


def parse_results(page: str) -> list[UnitQuote]:
    """Every item on the page that has a price, a size and a product link.

    Sponsored placements are kept but labelled: they are real prices, they are
    just the ones somebody paid to put first. Items are deduplicated by product
    id, and a robot-check page simply has no items and yields nothing.
    """
    out: list[UnitQuote] = []
    seen: set[str] = set()
    for chunk in _ITEM.findall(page)[:_MAX_ITEMS * 2]:
        title_m, whole, link = _TITLE.search(chunk), _WHOLE.search(chunk), _LINK.search(chunk)
        if not (title_m and whole and link):
            continue
        asin = link.group(2)
        if asin in seen:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
        parsed = parse_size(title)
        if not parsed:
            continue
        fraction = _FRACTION.search(chunk)
        price = money(f"{whole.group(1).replace(',', '')}.{fraction.group(1) if fraction else '00'}")
        if price is None:
            continue
        size, unit = parsed
        seen.add(asin)
        notes = ("marketplace: vendedores varios", "leído hoy, sin fecha de publicación")
        if "Patrocinado" in chunk or "AdHolder" in chunk:
            notes = ("patrocinado",) + notes
        out.append(UnitQuote(
            per_unit=(price / size).quantize(Decimal("0.01")), unit=unit, price=price, size=size,
            where="Amazon México", label=title[:120],
            url=f"https://www.amazon.com.mx/dp/{asin}", notes=notes,
        ))
        if len(out) == _MAX_ITEMS:
            break
    return out


def build_quote(term: str, units: Sequence[UnitQuote], source: str) -> list[PriceQuote]:
    if not units:
        return []
    prices = [u.price for u in units]
    cheapest, dearest = min(units, key=lambda u: u.price), max(units, key=lambda u: u.price)
    return [PriceQuote(
        term=term, kind=f"{term} (Amazon México)", observations=len(units),
        median=Decimal(median(prices)).quantize(Decimal("0.01")),
        low=cheapest.price, low_where=cheapest.where, low_label=cheapest.label,
        high=dearest.price, high_where=dearest.where,
        observed=date.today(), source=source,
        per_unit=rank_per_unit(units, each=_PER_UNIT_EACH),
    )]
