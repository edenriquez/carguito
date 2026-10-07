"""Store pages searched *and rendered* through Firecrawl.

The piece every other free route lacked. Search-engine snippets carry no prices
and supermarket product pages are JavaScript shells to a plain HTTP client, so
"free search" kept yielding URLs and never a number. Firecrawl's search endpoint
runs the query and then loads each result in a real browser, returning the page
as markdown -- with the price the shopper would see on it.

Two things shape the adapter:

1. **Credits are the budget.** The free plan is 1,000 a month and a scraped page
   costs credits, so the query is pinned to store domains with ``site:`` clauses
   (a rendered news article is a credit spent on nothing), the limit is small,
   and answers are cached upstream for an hour.
2. **A rendered page is long** (15-40 K characters) and almost all of it is
   navigation. Only the lines that carry a price, with a line of context, travel
   on to the model -- see :func:`condense`. Cheaper, and harder to hallucinate
   from, because the noise is gone before the reader ever sees it.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Sequence

from .brave import STORE_DOMAINS, SearchHit, is_store

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.firecrawl.dev/v1/search"
#: Rendering five pages takes ~13 s; a wedged browser must not hold the chat
#: turn much longer than that.
_TIMEOUT = 40.0
_LIMIT = 5

#: The stores worth a credit. Fewer than the allowlist on purpose: each clause
#: widens the search, and the big four plus the two marketplaces cover what a
#: Mexican shopper can actually go and buy.
_SITES = (
    "walmart.com.mx", "bodegaaurrera.com.mx", "soriana.com", "chedraui.com.mx",
    "heb.com.mx", "lacomer.com.mx",
)

_MONEY_LINE = re.compile(r"\$\s?\d")
_MAX_SNIPPET = 2500


class FirecrawlSearch:
    """Same shape as :class:`BraveSearch`, so :class:`WebPriceReference` takes either."""

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    @property
    def available(self) -> bool:
        return bool(self._key)

    def search(self, query: str, *, count: int = _LIMIT) -> list[SearchHit]:
        sites = " OR ".join(f"site:{s}" for s in _SITES)
        body = json.dumps({
            "query": f"{query} {sites}",
            "limit": min(count, _LIMIT),
            "lang": "es",
            "country": "mx",
            "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
        }).encode()
        request = urllib.request.Request(
            _ENDPOINT, data=body, method="POST",
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.warning("firecrawl search for %r failed: %s", query, exc)
            return []
        if not payload.get("success"):
            logger.warning("firecrawl search for %r refused: %s", query, str(payload)[:200])
            return []

        hits: list[SearchHit] = []
        for row in payload.get("data") or []:
            url = str(row.get("url") or "")
            if not is_store(url, STORE_DOMAINS):
                continue  # the site: clauses should prevent this; belt and braces
            title = str(row.get("title") or (row.get("metadata") or {}).get("title") or "")
            snippet = condense(str(row.get("markdown") or row.get("description") or ""))
            if snippet:
                hits.append(SearchHit(url=url, title=title, snippet=snippet))
        return hits


def condense(markdown: str, *, limit: int = _MAX_SNIPPET) -> str:
    """The price-bearing lines of a rendered page, each with its neighbour.

    A store page shows the product's price next to its name, the regular price
    it was marked down from, and a rail of other sellers -- and around all that,
    thousands of characters of menu. Keeping only lines with a peso sign plus
    one line of context on each side preserves every number a reader could want
    and the words needed to tell which is which.
    """
    lines = [re.sub(r"\s+", " ", line).strip() for line in markdown.splitlines()]
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if _MONEY_LINE.search(line):
            keep.update((i - 1, i, i + 1))
    out: list[str] = []
    for i in sorted(k for k in keep if 0 <= k < len(lines)):
        if lines[i] and (not out or out[-1] != lines[i]):
            out.append(lines[i])
    return "\n".join(out)[:limit]
