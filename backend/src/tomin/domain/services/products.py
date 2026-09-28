"""Turning a printed product name into something two tickets can be compared by.

A thermal printer has ~22 characters and no vowels to spare, so the same milk
is ``LECHE LALA ENT 1L`` at one store, ``LALA LECHE ENTERA 1 LT`` at another and
``7501020510010 LECHE LALA`` at a third. Comparing prices means deciding when
two of those are the same thing, and that decision is made *here*, once, so the
ingest that stores ``product_key`` and the comparison that groups on it can
never drift apart.

The rules are deliberately dumb and legible:

1. fold to the same normalisation the rest of the domain already uses
   (``categorization.normalize``: lowercase, no accents, no punctuation),
2. drop the store's own numbers — barcodes, PLU codes, line codes,
3. lift the size out of the name into a real quantity (``600 ml`` -> 0.6 l),
   because size is a *price* fact, not part of the product's identity,
4. expand the handful of abbreviations a Mexican ticket actually uses,
5. drop filler words that carry no identity (``pza``, ``c/u``, ``bolsa``).

What is *not* here: fuzzy matching, edit distance, embeddings. Two names that
survive this and still differ are treated as different products, and the user
sees them as separate rows. That is a visible, correctable outcome; a fuzzy
match that silently merges "leche entera" with "leche deslactosada" is a wrong
number presented as a fact, which this product does not do anywhere else.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

#: Base units everything is measured in. Volume folds to litres, weight to
#: kilos; anything else is a piece and compared as such.
_TO_BASE: dict[str, tuple[str, Decimal]] = {
    "ml": ("l", Decimal("0.001")),
    "mls": ("l", Decimal("0.001")),
    "cc": ("l", Decimal("0.001")),
    "l": ("l", Decimal("1")),
    "lt": ("l", Decimal("1")),
    "lts": ("l", Decimal("1")),
    "ltr": ("l", Decimal("1")),
    "litro": ("l", Decimal("1")),
    "litros": ("l", Decimal("1")),
    "g": ("kg", Decimal("0.001")),
    "gr": ("kg", Decimal("0.001")),
    "grs": ("kg", Decimal("0.001")),
    "gramos": ("kg", Decimal("0.001")),
    "kg": ("kg", Decimal("1")),
    "kgs": ("kg", Decimal("1")),
    "kilo": ("kg", Decimal("1")),
    "kilos": ("kg", Decimal("1")),
}

#: ``600 ml``, ``600ml``, ``1.5 lt``, ``900 g``. Anchored on a word boundary so
#: the ``1`` of "leche 1" and the ``500`` of a barcode are not read as sizes.
#: Runs over :func:`fold`, never over ``categorization.normalize`` -- that one
#: strips punctuation, which turns ``1.5 lt`` into ``1 5 lt`` and would have
#: this regex read a litre and a half as five litres.
_SIZE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(_TO_BASE, key=len, reverse=True)) + r")\b"
)

#: A multipack: ``6 pack``, ``12 pzas``, ``4 pz``. Recognised so it can be
#: *dropped* from the name — the pack count belongs to quantity, not identity.
_PACK = re.compile(r"\b\d+\s*(?:pack|pzas?|pz|piezas?|unid(?:ades?)?)\b")

#: A zero where a camera read the letter O: ``C0ST FRIJ0``, ``D0L0RES``.
#: Only a zero touching letters on both sides, or closing a token that has
#: no other digit, is a letter; the zeros of ``LALA900G`` and ``350G`` stay.
_ZERO_BETWEEN = re.compile(r"(?<=[a-z])0(?=[a-z])", re.IGNORECASE)
_ZERO_AT_END = re.compile(r"^([a-z]+)0$", re.IGNORECASE)


#: The name given to a ticket row whose price was read but whose name was
#: not (a crease, a smudge). It keeps the basket's arithmetic honest and is
#: excluded from the price book: ``product_key`` maps it to "", the key for
#: "no product here".
UNREADABLE_LINE = "(línea ilegible)"


def unzero(text: str) -> str:
    """OCR zeros back into the O's they were printed as."""
    out = []
    for token in text.split():
        fixed = _ZERO_BETWEEN.sub("O", token)
        fixed = _ZERO_BETWEEN.sub("O", fixed)  # ``C0L0R``: overlapping matches
        if not any(c.isdigit() for c in fixed[:-1]):
            fixed = _ZERO_AT_END.sub(lambda m: m.group(1) + "O", fixed)
        out.append(fixed)
    return " ".join(out)


#: Store numbers: barcodes (long), PLU/line codes (short, standalone digits).
_LONG_CODE = re.compile(r"\b\d{5,}\b")
_BARE_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")

#: What a ticket abbreviates. Only entries that are unambiguous in a grocery
#: context — "ent" is "entera" on a milk line and nothing else on any line.
_EXPAND = {
    "ent": "entera",
    "desl": "deslactosada",
    "deslac": "deslactosada",
    "choc": "chocolate",
    "ref": "refresco",
    "refr": "refresco",
    "jab": "jabon",
    "det": "detergente",
    "pap": "papel",
    "hig": "higienico",
    "tort": "tortilla",
    "tortis": "tortillas",
    "aceit": "aceite",
    "azuc": "azucar",
    "manz": "manzana",
    "nar": "naranja",
    "jit": "jitomate",
    "cebo": "cebolla",
    "pech": "pechuga",
    "sal": "sal",
    "chil": "chile",
    "yog": "yogurt",
    "yoghurt": "yogurt",
    "gall": "galleta",
    "galletas": "galleta",
    "cerv": "cerveza",
    "bco": "blanco",
    "bca": "blanca",
    "cja": "caja",
}

#: Words that survive normalisation but say nothing about *which* product this
#: is. Packaging, tax markers and the ticket's own furniture.
_FILLER = {
    # A unit with no number in front of it is leftover packaging talk:
    # "PECH POLLO KG" is the same product as "PECHUGA DE POLLO".
    "kg",
    "kgs",
    "g",
    "gr",
    "grs",
    "l",
    "lt",
    "lts",
    "ml",
    "pza",
    "pzas",
    "pz",
    "pieza",
    "piezas",
    "cu",
    "c",
    "u",
    "bolsa",
    "bol",
    "paq",
    "paquete",
    "caja",
    "cja",
    "lata",
    "bote",
    "botella",
    "pet",
    "iva",
    "t",
    "e",
    "a",
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "con",
    "sin",
    "y",
}


#: Everything that is not a letter, a digit, a space or a decimal separator.
_PUNCT = re.compile(r"[^a-z0-9 .,]+")
_WS = re.compile(r"\s+")


def fold(text: str) -> str:
    """Lowercase, strip accents, keep decimal separators.

    A near-twin of ``categorization.normalize``, and the difference is the
    whole point: descriptions are matched on words, but a *price* line is
    matched on numbers, and ``normalize`` deletes the dot in ``1.5 lt``.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT.sub(" ", text.lower())
    return _WS.sub(" ", text).strip()


def parse_size(text: str) -> tuple[Decimal | None, str | None]:
    """The size printed in a product name, in litres or kilos.

    Returns ``(None, None)`` when the name carries no size, which is the
    common case (fruit sold by weight, a loose bolillo, anything at a market).
    Callers must treat that as "compare by piece", never as "assume one".

    The *last* size wins: ``COCA 600ML 12 PACK 7.2L`` ends with the figure that
    describes what was actually bought.
    """
    if not text:
        return (None, None)
    matches = _SIZE.findall(fold(text))
    if not matches:
        return (None, None)
    raw, unit = matches[-1]
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return (None, None)
    base, factor = _TO_BASE[unit]
    size = (value * factor).normalize()
    # `normalize()` on 1E+0 style results would print as scientific notation;
    # quantizing back to a plain number keeps the stored string readable.
    return (size.quantize(Decimal("0.0001")).normalize(), base)


def product_key(description: str) -> str:
    """The identity two tickets are grouped by. Empty when nothing survives.

    An empty key is meaningful: it says "this line has no product in it" (a
    stray ``TOTAL`` the reader mistook for an item, a line of dashes), and the
    comparison skips those rather than inventing a product called "".
    """
    if description == UNREADABLE_LINE:
        return ""
    text = fold(unzero(description))
    if not text:
        return ""
    # Order matters: sizes and packs are read *before* the bare numbers that
    # spell them are deleted, or ``600 ml`` would become an orphan ``ml``.
    text = _SIZE.sub(" ", text)
    text = _PACK.sub(" ", text)
    text = _LONG_CODE.sub(" ", text)
    text = _BARE_NUMBER.sub(" ", text)
    # `fold` keeps decimal separators for the size regex above; past this
    # point they are just noise stuck to the end of a word ("ent." would miss
    # the expansion table by one character).
    words = [w.strip(".,") for w in text.split()]
    words = [_EXPAND.get(w, w) for w in words]
    words = [w for w in words if w and w not in _FILLER and len(w) > 1]
    return " ".join(words)


def display_name(description: str) -> str:
    """A readable name for a product group: the ticket's words, title-cased.

    The key is for machines ("leche lala entera"); this is what a person reads
    on the comparison screen. Derived from the *description* rather than the
    key so an expansion the key applied does not put a word on screen that the
    ticket never printed.
    """
    text = _WS.sub(" ", _LONG_CODE.sub(" ", fold(description))).strip()
    return text.title() if text else description.strip()
