"""Web search through Brave's Search API, narrowed to pages that sell things.

Search is the cheap half of a web listing and extraction is the expensive one,
so this module does the narrowing *before* a single token is spent: only results
whose domain is a store the product could actually be bought from go through.
That is also where the honesty lives — a news article about a promotion two
years ago is a real search result and a worthless price, and the domain is the
one signal that separates them without reading the page.

The free plan is 2,000 queries a month at one per second, which is why a lookup
is one query per product and results are cached upstream.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT = 10.0

#: Pages a price can be read from. Retailers only — no news, no deal
#: aggregators, no blogs — because a listing on a store's own page is the only
#: web price that is checkable by opening the link. Subdomains match
#: (despensa.bodegaaurrera.com.mx, super.walmart.com.mx).
STORE_DOMAINS: frozenset[str] = frozenset({
    "walmart.com.mx", "bodegaaurrera.com.mx", "soriana.com", "chedraui.com.mx",
    "heb.com.mx", "costco.com.mx", "sams.com.mx", "mercadolibre.com.mx",
    "amazon.com.mx", "lacomer.com.mx", "fresko.com.mx", "superama.com.mx",
    "farmaciasguadalajara.com", "farmaciasanpablo.com.mx", "liverpool.com.mx",
})


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str


class BraveSearch:
    def __init__(self, api_key: str, *, domains: frozenset[str] = STORE_DOMAINS) -> None:
        self._key = api_key
        self._domains = domains

    @property
    def available(self) -> bool:
        return bool(self._key)

    def search(self, query: str, *, count: int = 10) -> list[SearchHit]:
        """Store-page hits for the query. Empty on any failure, never raising."""
        params = urllib.parse.urlencode({
            "q": query, "country": "MX", "search_lang": "es", "count": count,
            # The extra snippets are where a price most often survives the
            # summarisation; without them the description is one sentence.
            "extra_snippets": "true",
        })
        request = urllib.request.Request(
            f"{_ENDPOINT}?{params}",
            headers={"Accept": "application/json", "X-Subscription-Token": self._key},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.warning("brave search for %r failed: %s", query, exc)
            return []

        hits: list[SearchHit] = []
        for row in (body.get("web") or {}).get("results") or []:
            url = str(row.get("url") or "")
            if not is_store(url, self._domains):
                continue
            snippet = " ".join(
                s for s in [row.get("description") or "", *(row.get("extra_snippets") or [])] if s
            )
            hits.append(SearchHit(url=url, title=str(row.get("title") or ""), snippet=snippet))
        return hits


def is_store(url: str, domains: frozenset[str] = STORE_DOMAINS) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)
