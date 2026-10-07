"""What the user's own tickets know about what things cost.

This is the answer to "¿dónde está más barata la leche?" and it is computed,
not asked. Every figure here comes from a line the user photographed: a price
this module reports is a price they actually paid, on a date, at a named store.
Nothing is estimated, nothing is fetched, and a product bought once has no
comparison — it has one price, and the honest output says so.

The comparison unit is chosen, not assumed. Two 1-litre cartons compare per
piece; a 600 ml bottle against a 2-litre one only compares per litre, and only
when *every* purchase in the group printed a size. When they do not, the group
falls back to price-per-piece and says which it used, because "$18 vs $32" is
meaningless if one of them was three times the size.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ..entities.receipt import Receipt, ReceiptItem
from .products import display_name, product_key

#: What the compared figure means. ``unit`` is per litre or per kilo, ``each``
#: is per piece. Always reported next to the numbers.
Basis = str  # "unit" | "each"


@dataclass(frozen=True)
class PricePoint:
    """One purchase of one product: the atom of the whole comparison."""

    receipt_id: UUID
    transaction_id: UUID | None
    purchased_at: date | None
    store: str | None
    description: str
    amount: Decimal
    quantity: Decimal | None
    each: Decimal | None
    per_base_unit: Decimal | None
    size: Decimal | None
    size_unit: str | None
    #: When the photo was taken. Not the purchase date -- a ticket can be
    #: photographed days later -- but the nearest thing to one a reading has
    #: when the print carried no legible date, and a price history with no
    #: dates is a list. Clients that fall back to it say so.
    captured_at: datetime | None = None

    def value(self, basis: Basis) -> Decimal | None:
        return self.per_base_unit if basis == "unit" else self.each


@dataclass(frozen=True)
class ProductPrices:
    """Everything the ledger of tickets knows about one product.

    ``points`` keeps every purchase, including the ones that could not be
    priced (a line with no quantity and no size still happened, and hiding it
    would make the history look thinner than it was). The statistics below are
    computed only over the points that *do* carry the comparable figure, and
    ``priced`` says how many that was.
    """

    product_key: str
    name: str
    basis: Basis
    points: tuple[PricePoint, ...]
    priced: int
    median: Decimal | None
    cheapest: PricePoint | None
    dearest: PricePoint | None
    latest: PricePoint | None
    stores: tuple[str, ...]

    @property
    def times_bought(self) -> int:
        return len(self.points)

    @property
    def spread(self) -> Decimal | None:
        """How much more the dearest purchase cost than the cheapest, in %.

        ``None`` with fewer than two priced purchases: a single price has no
        spread, and reporting 0% would read as "always the same price".
        """
        if self.cheapest is None or self.dearest is None or self.priced < 2:
            return None
        low = self.cheapest.value(self.basis)
        high = self.dearest.value(self.basis)
        if low is None or high is None or low <= 0:
            return None
        return ((high - low) / low * 100).quantize(Decimal("0.1"))

    @property
    def latest_vs_median(self) -> Decimal | None:
        """The last purchase against the typical one, in %. Positive is worse."""
        if self.latest is None or self.median is None or self.median <= 0:
            return None
        value = self.latest.value(self.basis)
        if value is None:
            return None
        return ((value - self.median) / self.median * 100).quantize(Decimal("0.1"))


def build_price_book(receipts: Iterable[Receipt]) -> list[ProductPrices]:
    """Group every item of every receipt into per-product price histories.

    Sorted by how often the product was bought, then by name: the list opens on
    the things the user buys every week, which is where a price difference is
    worth acting on.
    """
    groups: dict[str, list[PricePoint]] = {}
    names: dict[str, tuple[date | None, str]] = {}

    for receipt in receipts:
        for item in receipt.items:
            key = item.product_key
            if not key:
                continue
            groups.setdefault(key, []).append(_point(receipt, item))
            # The freshest description wins the display name: product names get
            # re-printed and a store's newer wording is the one the user just
            # saw on the shelf.
            seen = names.get(key)
            when = receipt.purchased_at
            if seen is None or (when is not None and (seen[0] is None or when >= seen[0])):
                names[key] = (when, display_name(item.description))

    book = [_summarize(key, points, names[key][1]) for key, points in groups.items()]
    book.sort(key=lambda p: (-p.times_bought, p.name))
    return book


#: Words a price question is made of, which say nothing about *which* product
#: it is about. Without this list "¿dónde está más barata la leche?" matches
#: nothing (no product is called "dónde") and the model gets no detail at all.
_QUESTION_WORDS = frozenset(
    """
    donde esta estan como cuando cuanto cuanta cuantos cuantas cual cuales que
    quien porque por para pero mas menos barata barato baratas baratos cara caro
    caras caros precio precios cuesta cuestan cueste pague pagado pagar compre
    comprado comprar comprando tienda tiendas super mercado lugar sitio mejor
    peor conviene ahorro ahorrar ahorre gasto gastar gaste sale salio salir
    veces vez ultimo ultima ultimos ultimas mes mes ano ano semana dia dias
    promedio mediana total suele suelo siempre nunca ahora antes despues
    el la los las un una unos unas de del al en con sin y o mi mis tu tus su sus
    este esta estos estas eso esto ese esa aqui alli ahi hay ser es son fue
    litro litros kilo kilos gramo gramos pieza piezas paquete caja bolsa lata
    marca producto articulo cosa ticket tickets compra compras canasta lista
    todo toda todos todas nada algo cual quiero puedo dime dice sabes
    desde hasta entre sobre segun tambien solo mismo misma otra otro
    subio subido bajo bajado cambio cambiado encarecio caro barato
    """.split()
)


def mentioned_in(book: Sequence[ProductPrices], question: str) -> list[ProductPrices]:
    """The products a question is plausibly about, best match first.

    Deliberately looser than :func:`find_product`: a question is prose, so a
    product matching *any* of its meaningful words is a candidate, ranked by
    how many it matched. Getting this wrong in the generous direction costs a
    few extra lines in the brief; getting it wrong in the strict direction
    means the model answers about milk without ever seeing the milk.
    """
    words = {w for w in product_key(question).split() if w not in _QUESTION_WORDS}
    if not words:
        return []
    scored = []
    for product in book:
        hits = len(words & set(product.product_key.split()))
        if hits:
            scored.append((hits, product.times_bought, product))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return [product for _, _, product in scored]


def find_product(book: Sequence[ProductPrices], query: str) -> list[ProductPrices]:
    """The products whose name or key contains every word of the query.

    Substring-per-word rather than one substring: "leche lala" should find
    "lala leche entera", and a user typing two words means both. This is the
    search box; :func:`mentioned_in` is the one that reads questions.
    """
    words = [w for w in product_key(query).split() if w]
    if not words:
        return list(book)
    return [
        product
        for product in book
        if all(word in product.product_key or word in product.name.lower() for word in words)
    ]


# --- internals -----------------------------------------------------------
def _point(receipt: Receipt, item: ReceiptItem) -> PricePoint:
    return PricePoint(
        receipt_id=receipt.id,
        transaction_id=receipt.transaction_id,
        purchased_at=receipt.purchased_at,
        store=receipt.store,
        description=item.description,
        amount=item.amount,
        quantity=item.quantity,
        each=item.each,
        per_base_unit=item.per_base_unit,
        size=item.size,
        size_unit=item.size_unit,
        captured_at=receipt.captured_at,
    )


def _summarize(key: str, points: list[PricePoint], name: str) -> ProductPrices:
    ordered = sorted(
        points,
        # Undated purchases sort last: a receipt whose date OCR could not read
        # must not be presented as the most recent price.
        key=lambda p: (p.purchased_at is not None, p.purchased_at or date.min),
        reverse=True,
    )
    basis = _basis(ordered)
    priced = [p for p in ordered if p.value(basis) is not None]

    cheapest = min(priced, key=lambda p: p.value(basis)) if priced else None
    dearest = max(priced, key=lambda p: p.value(basis)) if priced else None
    latest = next((p for p in ordered if p.value(basis) is not None), None)

    stores = []
    for point in ordered:
        if point.store and point.store not in stores:
            stores.append(point.store)

    return ProductPrices(
        product_key=key,
        name=name,
        basis=basis,
        points=tuple(ordered),
        priced=len(priced),
        median=_median([p.value(basis) for p in priced]),
        cheapest=cheapest,
        dearest=dearest,
        latest=latest,
        stores=tuple(stores),
    )


def _basis(points: Sequence[PricePoint]) -> Basis:
    """Per-unit when every purchase can be, per-piece otherwise.

    "Every" and not "most": a basis that changes which purchases it can see
    would compare a subset against itself and call it a price history.
    """
    if len(points) > 1 and all(p.per_base_unit is not None for p in points):
        units = {p.size_unit for p in points}
        if len(units) == 1:
            return "unit"
    return "each"


def _median(values: Sequence[Decimal | None]) -> Decimal | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    middle = len(clean) // 2
    if len(clean) % 2:
        return clean[middle]
    return ((clean[middle - 1] + clean[middle]) / 2).quantize(Decimal("0.01"))
