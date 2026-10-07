"""External price references: what a thing costs *out there*, not what you paid.

The one place in Tomin where a figure on screen does not come from a document
the user owns. That makes the contract narrower than it looks:

* A quote always carries **who observed it, where and when**. A reference price
  with no source and no date is a rumour, and the whole product rests on the
  opposite property.
* Failure is empty, never an exception. The reference is a garnish on an answer
  that is already complete without it, so a slow or unreachable source must
  degrade to "no reference" and never to a broken chat.
* Nothing here decides *how* a quote is compared to the user's own price. It
  cannot: the sizes differ, and a median across presentations is not a
  like-for-like price. The brief says so, in words, and the model is told.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class UnitQuote:
    """One observed presentation with a price per litre or per kilo.

    The figure that actually compares to a ticket line: a 7-litre jug and a
    3-litre bottle meet at "pesos por litre" and nowhere else. ``unit`` is the
    base -- "l" or "kg" -- and quotes in different bases must never be compared,
    which the brief states and the model is told.
    """

    per_unit: Decimal
    unit: str
    price: Decimal
    size: Decimal
    where: str
    label: str
    #: The page it was read from. Only web listings have one; the survey does
    #: not publish per-observation links.
    url: str | None = None
    #: Conditions a shopper needs to see before acting: "promoción", "requiere
    #: membresía", "solo en línea". Labels rather than a penalty score — a score
    #: mixes pesos with guesses into a number nobody can check.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PriceQuote:
    """One observed reference price for a kind of product.

    ``kind`` is the source's own category ("LECHE ULTRAPASTEURIZADA"), not the
    user's product name: the two vocabularies are different and pretending
    otherwise is how "tu leche" gets compared against powdered milk.
    """

    #: What the user asked about, echoed back so the brief can group by it.
    term: str
    kind: str
    observations: int
    median: Decimal
    low: Decimal
    low_where: str
    low_label: str
    high: Decimal
    high_where: str
    #: Most recent observation behind this line. Profeco's survey lags by weeks.
    observed: date | None
    #: Who says so, named in every line the user ever sees.
    source: str
    #: The cheapest presentations by litre and by kilo, when the survey printed
    #: a size. Empty for kinds (produce, pieces) where no size is stated.
    per_unit: tuple[UnitQuote, ...] = ()


@dataclass(frozen=True)
class ReferenceTerm:
    """A product's association with the word the outside world files it under.

    ``source`` is the whole reason this is not a cache: ``auto`` is a proposal a
    model made and may revise, ``user`` is an answer a person gave and nothing
    may overwrite.
    """

    product_key: str
    term: str
    source: str


@runtime_checkable
class ProductTermRepository(Protocol):
    """Stores what a ticket's shorthand is called out in the world."""

    def all_for_user(self, user_id) -> list[ReferenceTerm]: ...

    def get(self, user_id, product_key: str) -> ReferenceTerm | None: ...

    def upsert(self, user_id, product_key: str, term: str, source: str) -> None:
        """Writes the association. A ``user`` row is never replaced by ``auto``:
        that rule lives in the implementation because it is what makes a
        correction stick."""
        ...


@runtime_checkable
class PriceReference(Protocol):
    """Looks up reference prices for a handful of search terms."""

    @property
    def available(self) -> bool:
        """False when no source is configured, so the brief omits the section."""
        ...

    @property
    def source_label(self) -> str:
        """Named in the UI's disclosure: a second third party sees these terms."""
        ...

    def lookup(self, terms: Sequence[str], *, hint: str = "") -> list[PriceQuote]:
        """Quotes for those terms. Empty on any failure, never raising.

        ``hint`` is the user's presentation ("7 l"). A source that searches
        pages narrows with it -- "detergente 7 l" finds product pages where
        "detergente" finds category pages -- while a survey keyed on generic
        names ignores it.
        """
        ...


class NullPriceReference:
    """What the container injects when references are switched off.

    The normal state of a clone that does not want an outbound call on every
    question: the chat answers from the user's own tickets exactly as it did
    before this port existed.
    """

    @property
    def available(self) -> bool:
        return False

    @property
    def source_label(self) -> str:
        return ""

    def lookup(self, terms: Sequence[str], *, hint: str = "") -> list[PriceQuote]:
        return []


class CompositePriceReference:
    """Several sources asked at once, answering as one.

    Each source is a network call of a couple of seconds, so they run in
    parallel rather than in sequence; each source already fails to an empty
    list, so a slow or broken one costs its own timeout and nothing else. The
    quotes keep their own ``source`` label, which is how the brief and the user
    still know which figure came from where.
    """

    def __init__(self, sources: Sequence[PriceReference]) -> None:
        self._sources = [s for s in sources if s.available]

    @property
    def available(self) -> bool:
        return bool(self._sources)

    @property
    def source_label(self) -> str:
        return " · ".join(s.source_label for s in self._sources)

    def lookup(self, terms: Sequence[str], *, hint: str = "") -> list[PriceQuote]:
        if not self._sources:
            return []
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(self._sources)) as pool:
            results = pool.map(lambda s: _safe_lookup(s, terms, hint), self._sources)
        return [q for quotes in results for q in quotes]


def _safe_lookup(source: PriceReference, terms: Sequence[str], hint: str) -> list[PriceQuote]:
    try:
        return list(source.lookup(terms, hint=hint))
    except Exception:  # pragma: no cover - the contract says never raise; belt and braces
        return []
