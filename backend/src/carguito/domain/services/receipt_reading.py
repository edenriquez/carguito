"""Reading a grocery ticket that a phone camera turned into lines of text.

A ticket is not a bank statement. There are no columns to trust, no issuer to
classify, and OCR will hand us ``LECHE LALA ENT 1L 28,50`` on a good day and
``LECHE LALA ENT lL 28.5O`` on a bad one. So this reader is built on one
assumption only — **a product line ends in money** — and everything else is a
sequence of small, individually reversible decisions around it.

It is deliberately conservative in both directions:

* A line it cannot read is *dropped*, not guessed at. The receipt then shows a
  smaller basket than the printed total, and the UI says so out loud
  ("faltan $32.50"). A guessed line would poison a price history that the
  whole feature exists to make trustworthy.
* A line it *can* read keeps its raw text, so the user can see what it decided
  and correct it.

This is the fallback that always works, with no key and no network. When a
model is configured, ``adapters/outbound/receipts/llm.py`` reads the same lines
better — and falls back here the moment it returns something that does not
add up.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, time
from decimal import Decimal, InvalidOperation

from ...application.dtos.receipts import ParsedReceipt, ParsedReceiptItem
from .products import UNREADABLE_LINE, unzero

#: The chains a Mexican grocery ticket is most likely to come from. Used only
#: to *name* the store when the header is legible; an unknown store falls back
#: to the first readable header line, which is right far more often than not.
_CHAINS = (
    "mi bodega aurrera",
    "bodega aurrera",
    "walmart express",
    "walmart",
    "wal mart",
    "sams club",
    "sams",
    "costco",
    "soriana",
    "mega soriana",
    "chedraui",
    "la comer",
    "city market",
    "fresko",
    "superama",
    "heb",
    "casa ley",
    "calimax",
    "smart and final",
    "tiendas 3b",
    "bara",
    "merco",
    "alsuper",
    "oxxo",
    "seven eleven",
    "7 eleven",
    "circle k",
    "farmacia guadalajara",
    "farmacias similares",
    "waldos",
    "del sol",
    "elektra",
    "mercado soriana",
    "sumesa",
)

#: How a lens misspells the chains, on the space-less line.
_CHAIN_MISREADS = (("aurera", "aurrera"), ("walmar", "walmart"), ("walmartt", "walmart"))

_WS = re.compile(r"\s+")


def _clean(line: str) -> str:
    """Strip accents and collapse whitespace, keeping case and punctuation.

    Everything else in the domain folds punctuation away, and here that would
    be fatal twice over: ``22/08/2026`` becomes three numbers and ``28.50``
    becomes two. Case is kept because this string is what the user reads back
    as the product's name.
    """
    if not line:
        return ""
    text = unicodedata.normalize("NFKD", line)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _WS.sub(" ", text).strip()


#: An amount at the end of a line, with an optional currency mark and the tax
#: flag letter Mexican tickets print after the price ("28.50 T", "12.00 E").
_TRAILING_AMOUNT = re.compile(
    # After the cents: the tax marker Mexican printers stamp after the price
    # (``28.50 T``, ``28.50A``), which a phone camera reads as a letter, or
    # as a digit glued to the price (``14.001``, ``3.504``). One character
    # only, so a genuine ``1234.56`` is never split.
    r"(?:\$\s*)?(-?\d{1,3}(?:[.,]\d{3})+[.,]\d{2}|-?\d+\.\d{2}|-?\d+,\d{2})[a-z0-9]?\s*[a-z]?\s*$",
    re.IGNORECASE,
)

#: ``2 X 20.00`` / ``2 PZA X $20.00`` / ``0.850 KG X 32.00`` /
#: ``0.675KGSX17.00/KG``. The quantity and the price of one, however the
#: printer chose to spell it.
_QTY_TIMES_PRICE = re.compile(
    r"(?:^|\s)(\d+(?:[.,]\d+)?)\s*(?:kgs?|kilos?|pzas?|pz|piezas?)?\s*[x×@]\s*"
    r"(?:\$\s*)?(\d+(?:[.,]\d{1,2}))(?:\s*/\s*kgs?)?",
    re.IGNORECASE,
)

#: A line that is *only* a quantity clause. Printers put it under the product
#: name, and on its own it means "the line above was bought this many times".
_QTY_ONLY = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(?:kgs?|kilos?|pzas?|pz|piezas?)?\s*[x×@]\s*"
    r"(?:\$\s*)?(\d+(?:[.,]\d{1,2}))(?:\s*/\s*kgs?)?\s*[a-z]?\s*$",
    re.IGNORECASE,
)

#: A leading store code: the barcode or PLU printed before the name. Glued
#: or not (``7501030452553PAN ARTESA``, ``31BOLILLO``): a camera drops the
#: space as often as it keeps it, and no product name starts with digits
#: stuck to a capital letter.
_LEADING_CODE = re.compile(r"^\s*(?:\d{4,}\s*|\d{2,3}(?=[A-Z]))")
#: A barcode anywhere in the line. When a department header or a neighbour's
#: name got joined onto a product row, the product is what follows the last
#: barcode; everything before it belongs to something else.
_BARCODE_INSIDE = re.compile(r"\b\d{8,}\s*")
#: Every money-looking token on a row, for telling which of two the
#: arithmetic supports.
_MONEY_TOKEN = re.compile(r"\d+[.,]\d{2}(?![\d])")
#: Money that stayed in the name after the row's amount was taken off: a
#: neighbour's price joined onto the row, or a ``122.00x`` with the count
#: lost. Stripped from the name, never read as the amount.
_STRAY_MONEY = re.compile(r"(?:^|\s)\$?\d+[.,]\d{2}\s*[a-z×]?\d?(?=\s|$)", re.IGNORECASE)
#: A discount printed under the item it applies to. Its trailing amount is
#: what the item cost after the discount, which replaces the price above.
_DISCOUNT_LINE = re.compile(r"rebaja|reba[il]a|combina")
#: Past this line the ticket is totals and tender; a bare amount there is a
#: subtotal whose label went missing, never a product.
_TOTALS_ZONE = re.compile(r"\b(?:subtotal|total|importe|efectivo|cambio|tarjeta)\b")
#: ``13.50x2``, ``42.00×2``, ``45.00x1``: the price of one, times how many —
#: Walmart's spelling, price first. ``0.675KGSX17.00/KG`` is the by-weight
#: version, handled by ``_QTY_TIMES_PRICE``.
_PRICE_TIMES_QTY = re.compile(r"(?:^|\s)(\d+[.,]\d{2})\s*[x×]\s*(\d+(?:[.,]\d+)?)(?=\s|$)", re.IGNORECASE)

#: A short label followed by a long number: ``AUT 004512``, ``TDA 0451``. The
#: ticket's own bookkeeping, and indistinguishable from a product line by the
#: only rule this reader has (it ends in money). Matched narrowly — four digits
#: minimum — so that a genuine ``PAN 15.00`` or ``SAL 12.00`` survives.
_CODEISH = re.compile(r"^[a-z]{1,5}\.?\s*[\d\s]{4,}$", re.IGNORECASE)

#: Every way a Mexican printer spells a date, most specific first. Day-first
#: throughout except ISO. Separators are ``/``, ``-`` or ``.``, with the odd
#: OCR space around them (``28 /09/ 26``); the two-digit year is last because
#: it is the loosest. Month names cover ``28/SEP/26`` and ``28 SEP 2026``.
_SEP = r"\s?[/.\-]\s?"
_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}
_DATE_PATTERNS = (
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), ("y", "m", "d")),
    (re.compile(rf"\b(\d{{1,2}}){_SEP}(\d{{1,2}}){_SEP}(\d{{4}})\b"), ("d", "m", "y")),
    (re.compile(rf"\b(\d{{1,2}})[\s/.\-]+([a-z]{{3}})[a-z]*[\s/.\-]+(\d{{4}}|\d{{2}})\b"), ("d", "mon", "y")),
    (re.compile(rf"\b(\d{{1,2}}){_SEP}(\d{{1,2}}){_SEP}(\d{{2}})\b"), ("d", "m", "y")),
)
#: ``19:42`` or ``19:42:07``. Hours are checked, so a ``2 X 20.00`` line or a
#: barcode never reads as a time.
_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b")

#: Words that mean "this line is the ticket talking about itself". A line
#: carrying any of them is never a product, however much it looks like one.
_NOT_A_PRODUCT = (
    "subtotal",
    "total",
    "importe",
    "iva",
    "ieps",
    "impuesto",
    "efectivo",
    "cambio",
    "tarjeta",
    "cuenta",
    "credito",
    "debito",
    "vales",
    "propina",
    "descuento",
    "rebaja",
    "ahorro",
    "ahorraste",
    "monedero",
    "puntos",
    "saldo",
    "folio",
    "ticket",
    "caja",
    "cajero",
    "cajera",
    "atendio",
    "gracias",
    "vuelva",
    "rfc",
    "factura",
    "cfdi",
    "comprobante",
    "cliente",
    "sucursal",
    "suc ",
    "tel ",
    "telefono",
    "direccion",
    "www",
    "http",
    "articulos",
    "piezas totales",
    "no de art",
    "num art",
    "autorizacion",
    "terminal",
    "operacion",
    "referencia",
    "aprobada",
    "banco",
    "sat ",
    "regimen",
    "serie",
    "articulo ",
    "cant.",
)

#: Department headers a supermarket prints between groups of items:
#: ``ABARROTES BASICOS-``, ``QUESOS Y EMBUTIDOS-``, ``LACTEOS-``. A camera
#: joins them onto the row under or over them as often as it keeps them
#: apart, so they are not a reason to drop a row; they are words to take
#: out of it. Full words, unlike the abbreviations products get.
_DEPARTMENTS = frozenset(
    {
        "abarrotes", "basicos", "procesados", "lacteos", "quimicos", "mascotas",
        "salchichoneria", "panaderia", "tortilleria", "farmacia", "perfumeria",
        "tocador", "frutas", "verduras", "carnes", "pescados", "mariscos",
        "ferreteria", "jugueteria", "electronica", "cosmeticos", "cuidado",
        "bebe", "personal", "limpieza", "hogar", "quesos", "embutidos",
        "congelados", "bebidas", "vinos", "licores", "dulceria", "botanas",
        "desechables", "blancos", "ropa", "zapateria", "papeleria", "deportes",
        "automotriz", "jardin", "cerveza", "refrescos", "cereales",
    }
)


def _strip_departments(text: str) -> str:
    """The row without its department words and the dashes they leave.

    ``QUESOSY EMBUTIDOS- CHX TOCINO`` -> ``CHX TOCINO``. A token is a
    department word with or without its trailing dash, and with the ``Y``
    of "QUESOS Y" glued onto it.
    """
    kept = []
    for token in text.split():
        word = token.lower().rstrip("-")
        if not word or set(token) <= {"-"}:
            continue
        if word in _DEPARTMENTS or (word.endswith("y") and word[:-1] in _DEPARTMENTS):
            continue
        kept.append(token)
    return " ".join(kept)

#: The word that names the amount the user actually paid. ``subtotal`` and
#: "total de articulos" are excluded because both are true and neither is it.
_TOTAL_LINE = re.compile(r"(?<!sub)\btotal\b")
#: What the card was charged: the total again, on a line that survives when
#: the ``TOTAL`` row was read as words ("UN MIL QUINIENTOS SIETE PESOS").
_IMPORTE_LINE = re.compile(r"\bimporte\b")
#: The column header every Walmart ticket opens with. Not a store name.
_COLUMN_HEADER = re.compile(r"\b(?:articulo|cant|total)\b")
_TOTAL_EXCLUDE = ("articulo", "pieza", "unidad", "item", "descuento", "ahorro")


def read_receipt(lines: list[str]) -> ParsedReceipt:
    """Structure OCR lines into a store, a date, a total and line items."""
    clean = [_clean(line) for line in lines]
    # Keywords are matched with the camera's zeros read back as O's:
    # ``T0TAL`` and ``IMP0RTE`` are what a thermal print looks like to a
    # lens, and a total that hides behind one is a ticket with no total.
    folded = [unzero(line).lower() for line in clean]
    store = _detect_store(folded)
    purchased_at, purchased_time = _detect_date(folded)
    total = _detect_total(folded)
    items = _detect_items(clean, folded)
    return ParsedReceipt(
        store=store,
        purchased_at=purchased_at,
        purchased_time=purchased_time,
        total=total,
        items=items,
    )


# --- the pieces ----------------------------------------------------------
def _detect_store(folded: list[str]) -> str | None:
    """The chain name if we know it, else the first line that reads like one.

    Chains are checked over the *whole* ticket, not just the header: OCR
    frequently mangles a stylised logo at the top while the same name prints
    cleanly in the footer's fiscal block.
    """
    # The header first, then the whole ticket: a Bodega Aurrera ticket ends
    # with "NUEVA WAL MART DE MEXICO" in its fiscal block, and the chain that
    # names the store is the one printed at the top.
    for zone in (folded[:8], folded):
        for line in zone:
            # Spaces dropped too, and the camera's spellings mended: a
            # stylised logo reads as ``BodegaAurera``.
            squashed = line.replace(" ", "")
            for wrong, right in _CHAIN_MISREADS:
                squashed = squashed.replace(wrong, right)
            for chain in _CHAINS:
                if chain in line or chain.replace(" ", "") in squashed:
                    return chain.title()
    for line in folded[:6]:
        letters = sum(c.isalpha() for c in line)
        words = set(line.replace("-", " ").split())
        if (
            letters >= 4
            and not _TRAILING_AMOUNT.search(line)
            and not _COLUMN_HEADER.search(line)
            and not _BARCODE_INSIDE.search(line)
            and not any(word in line for word in _NOT_A_PRODUCT)
            and not words & _DEPARTMENTS
        ):
            return line.title()
    return None


def _detect_date(folded: list[str]) -> tuple[date | None, time | None]:
    """When the ticket was paid, read day-first.

    A ticket can print more than one date -- a promotion's expiry, a card's
    -- so the purchase is taken to be the date that shares its line with a
    clock time: on a Mexican ticket that is the ``28/09/26   14:32`` at the
    foot, and it is the only date the printer stamps at the moment of the
    sale. Only when no line carries both does the first date anywhere on the
    ticket stand in, without a time.

    Day-first because this is Mexico and every printer here spells
    ``dd/mm/aa``; the ISO pattern is matched separately and unambiguously.
    An impossible date (OCR read ``13/45/2026``) is skipped rather than
    clamped -- a wrong purchase date silently misfiles a price in history.
    """
    first: date | None = None
    for line in folded:
        found = _date_in(line)
        if found is None:
            continue
        clock = _time_in(line)
        if clock is not None:
            return found, clock
        if first is None:
            first = found
    return first, None


def _date_in(line: str) -> date | None:
    for pattern, order in _DATE_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        raw = dict(zip(order, match.groups()))
        year = int(raw["y"])
        if year < 100:
            year += 2000
        month = _MONTHS.get(raw["mon"]) if "mon" in raw else int(raw["m"])
        if month is None:
            continue
        try:
            return date(year, month, int(raw["d"]))
        except ValueError:
            continue
    return None


def _time_in(line: str) -> time | None:
    match = _TIME.search(line)
    return time(int(match.group(1)), int(match.group(2))) if match else None


def _detect_total(folded: list[str]) -> Decimal | None:
    """The last honest ``TOTAL`` line on the ticket.

    Last rather than largest: a ticket prints ``TOTAL`` once for the basket and
    then the tender lines (``EFECTIVO 500.00``) which can be bigger, and it
    prints the fiscal total again at the bottom, which is the same number.
    """
    found: Decimal | None = None
    for line in folded:
        if not _TOTAL_LINE.search(line):
            continue
        if any(word in line for word in _TOTAL_EXCLUDE):
            continue
        amount = _trailing_amount(line)
        if amount is not None:
            found = amount
    if found is not None:
        return found
    # No readable TOTAL row: the card slip's IMPORTE is the same figure.
    for line in folded:
        if _IMPORTE_LINE.search(line):
            amount = _trailing_amount(line)
            if amount is not None:
                found = amount
    return found


def _detect_items(clean: list[str], folded: list[str]) -> list[ParsedReceiptItem]:
    """Every line that ends in money and is not the ticket talking about itself.

    Two printer habits are handled beyond the obvious one-line-per-product:

    * ``COCA COLA 600ML`` / ``2 X 20.00  40.00`` — the name on one line and the
      arithmetic on the next. The price line has no words of its own, so it
      adopts the line above it.
    * ``PAN BIMBO 45.90`` / ``2 X 22.95`` — the arithmetic *after* a complete
      item line, which refines the item rather than adding one.
    """
    items: list[ParsedReceiptItem] = []
    #: The last line that read like a product name but carried no price. Only
    #: the immediately preceding line is ever adopted: a name and its price are
    #: adjacent on every printer, and reaching further back would let a
    #: header line ("SUCURSAL MIXCOAC") name somebody's groceries.
    pending: tuple[int, str] | None = None
    #: Once the totals begin, a bare amount is a label-less subtotal.
    totals_zone = False

    for index, (raw, line) in enumerate(zip(clean, folded)):
        if not line:
            pending = None
            continue
        # "subtotal" always comes first and is unmistakable; a bare "total"
        # is also the column header every Walmart ticket opens with, so it
        # only counts once it carries a figure.
        if "subtotal" in line or (
            _TOTALS_ZONE.search(line) and _trailing_amount(line) is not None
        ):
            totals_zone = True

        # ``Rebaja 1x$46-14.00x 46.00T`` under an item: the item cost 46, not
        # the 60 printed above it. Applied only downwards, and only when it
        # is a rebate: a "discount" that raises the price is another row.
        if items and _DISCOUNT_LINE.search(line):
            net = _trailing_amount(line)
            if net is not None and 0 < net < items[-1].amount:
                items[-1] = _reprice(items[-1], raw, net)
            pending = None
            continue

        noise = any(word in line for word in _NOT_A_PRODUCT)
        amount = None if noise else _trailing_amount(line)

        # A bare quantity clause after a finished item refines it in place.
        if amount is None and items and _QTY_ONLY.match(line):
            qty_only = _QTY_ONLY.match(line)
            items[-1] = _refine(items[-1], raw, qty_only)
            pending = None
            continue

        if amount is None or amount <= 0:
            # A name waiting for its price on the next row -- unless it is
            # the store's own name, which is never a product's.
            has_words = sum(c.isalpha() for c in raw) >= 3
            is_store = any(chain.replace(" ", "") in line.replace(" ", "") for chain in _CHAINS)
            pending = (index, raw) if has_words and not noise and not is_store else None
            continue

        rest = _TRAILING_AMOUNT.sub("", raw).strip()
        # A department header or a neighbour joined onto this row: the product
        # is what follows the last barcode, minus the department's words.
        codes = list(_BARCODE_INSIDE.finditer(rest))
        if codes:
            rest = rest[codes[-1].end() :].strip() or rest
        rest = _strip_departments(rest)
        # Whether the row was nothing but its amount (and a department name
        # the camera glued on): the one shape a nameless product row has.
        bare = not any(c.isdigit() for c in rest) and len(rest) <= 2
        quantity: Decimal | None = None
        unit_price: Decimal | None = None
        inline = _QTY_TIMES_PRICE.search(rest)
        if inline:
            quantity = _decimal(inline.group(1))
            unit_price = _decimal(inline.group(2))
            rest = (rest[: inline.start()] + " " + rest[inline.end() :]).strip()
        else:
            flipped = _PRICE_TIMES_QTY.search(rest)
            if flipped:
                unit_price = _decimal(flipped.group(1))
                quantity = _decimal(flipped.group(2))
                rest = (rest[: flipped.start()] + " " + rest[flipped.end() :]).strip()

        # Two rows the camera joined leave two prices on one; when the row's
        # own arithmetic (``42.00×2``) names one of them, that one is the
        # row's amount and the other belongs to the neighbour.
        if quantity is not None and unit_price is not None:
            product = (quantity * unit_price).quantize(Decimal("0.01"))
            printed = {_decimal(m) for m in _MONEY_TOKEN.findall(raw)}
            if product in printed and product != amount:
                amount = product
        rest = _STRAY_MONEY.sub(" ", rest).strip()
        description = unzero(_LEADING_CODE.sub("", rest).strip(" .-\u00b7"))
        line_no = index
        raw_text = raw

        # No words left: this line is the arithmetic for the name above it.
        # "Words" means three letters; "38.00 x" and a stray "S" are not a
        # product, they are the arithmetic and the noise around it.
        if sum(c.isalpha() for c in description) < 3:
            if pending is None or pending[0] != index - 1:
                pending = None
                # No name above it either. Inside the item area that is a
                # product whose name the camera lost (a crease, a smudge):
                # kept, nameless, so the basket still adds up and the gap
                # against the printed total says how much was not read.
                # Past the totals it is a label-less subtotal: dropped.
                # ...but only a *bare* amount qualifies. Digits left in
                # front of it (``0000 1234 5678 99.00``) make it a card or
                # fiscal number, which is dropped as before.
                # A nameless row over a thousand pesos is a subtotal whose
                # label was lost far more often than a product.
                if totals_zone or not bare or amount >= 1000:
                    continue
                items.append(
                    ParsedReceiptItem(
                        line_no=index,
                        raw_text=raw,
                        description=UNREADABLE_LINE,
                        amount=amount,
                    )
                )
                continue
            line_no, name = pending
            description = unzero(_LEADING_CODE.sub("", name).strip(" .-\u00b7"))
            raw_text = f"{name} \u00b7 {raw}"

        if _CODEISH.match(description):
            pending = None
            continue
        if quantity is not None and quantity <= 0:
            quantity = None

        items.append(
            ParsedReceiptItem(
                line_no=line_no,
                raw_text=raw_text,
                description=description,
                amount=amount,
                quantity=quantity,
                unit_price=unit_price,
            )
        )
        pending = None
    return items


def _reprice(item: ParsedReceiptItem, raw: str, net: Decimal) -> ParsedReceiptItem:
    """The item at the price the discount line under it says it cost."""
    return ParsedReceiptItem(
        line_no=item.line_no,
        raw_text=f"{item.raw_text} \u00b7 {raw}",
        description=item.description,
        amount=net,
        quantity=item.quantity,
        unit_price=item.unit_price,
    )


def _refine(
    item: ParsedReceiptItem, raw: str, qty_only: re.Match
) -> ParsedReceiptItem:
    """Fold a trailing ``2 X 20.00`` line into the item it describes."""
    quantity = _decimal(qty_only.group(1))
    unit_price = _decimal(qty_only.group(2))
    return ParsedReceiptItem(
        line_no=item.line_no,
        raw_text=f"{item.raw_text} \u00b7 {raw}",
        description=item.description,
        amount=item.amount,
        quantity=quantity if quantity and quantity > 0 else item.quantity,
        unit_price=unit_price or item.unit_price,
    )


def _trailing_amount(line: str) -> Decimal | None:
    match = _TRAILING_AMOUNT.search(line)
    return _decimal(match.group(1)) if match else None


def _decimal(raw: str) -> Decimal | None:
    """Parse a printed amount. ``1,234.56`` and ``28,50`` both occur.

    A comma is a thousands separator when a dot is also present, and a decimal
    separator when it is not — the only reading under which both spellings
    above mean what a human sees.
    """
    text = raw.strip()
    if text.count(".") > 1 and "," not in text:
        # ``1.575.68``: dots as thousands *and* decimals. The last one is
        # the decimal point; the rest are grouping.
        head, _, tail = text.rpartition(".")
        text = head.replace(".", "") + "." + tail
    if "." in text:
        text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None
