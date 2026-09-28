"""Reading a ticket with the configured model, and checking its homework.

A thermal print read through a phone camera is the one input in this codebase
where a language model is genuinely better than a rule: it survives two
columns, a torn edge, a price that OCR split across lines, and abbreviations no
table will ever cover. So it gets to read.

It does not get to be believed. Every answer is checked against the arithmetic
the ticket itself prints — the items have to add up to the total — and the
heuristic reads the same lines in parallel. Whichever comes closer to the
printed total wins, and a model answer that will not parse loses by default.
That check is the whole reason this adapter can exist inside a product whose
posture is "nunca inventes una cifra": the model's output is a *proposal*,
scored against a number it did not produce.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from datetime import date, time
from decimal import Decimal, InvalidOperation

from ....application.dtos.receipts import ParsedReceipt, ParsedReceiptItem
from ....application.ports.outbound.chat import (
    ChatMessage,
    ChatOptions,
    ChatPort,
    ChatUnavailable,
    json_schema_format,
)
from .heuristic import HeuristicReceiptReader

logger = logging.getLogger(__name__)

#: Beyond this many lines the ticket is not a ticket (a mis-fired OCR of a
#: newspaper, a scanned book page). Refusing early keeps a pathological input
#: from turning into a very large request.
MAX_LINES = 400

_FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)

#: The answer's shape, sent as the request's ``response_format``. Providers that
#: honour it cannot return prose or a stray key; the prompt below still spells
#: the shape out for the ones that ignore the field, and ``_parse`` still checks
#: every value, because a schema constrains syntax, not truth.
RECEIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["store", "purchased_at", "purchased_time", "total", "items"],
    "properties": {
        "store": {"type": ["string", "null"]},
        "purchased_at": {"type": ["string", "null"]},
        "purchased_time": {"type": ["string", "null"]},
        "total": {"type": ["string", "null"]},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["line_no", "description", "amount", "quantity", "unit_price"],
                "properties": {
                    "line_no": {"type": "integer"},
                    "description": {"type": "string"},
                    "amount": {"type": "string"},
                    "quantity": {"type": ["string", "null"]},
                    "unit_price": {"type": ["string", "null"]},
                },
            },
        },
    },
}

#: Cold and pinned to the schema: reading a ticket is extraction, not prose.
OPTIONS = ChatOptions(
    temperature=0,
    # A sixty-line ticket is ~3k tokens of JSON, and a reasoning model spends
    # its budget thinking before it writes any of it. The default 4k was
    # being exhausted mid-list. Not higher: a metered provider *reserves* the
    # budget up front and refuses the call outright (402) when the account
    # cannot cover it, which is worse than a cut-short answer — that one
    # still salvages its complete items.
    max_tokens=6000,
    response_format=json_schema_format("ticket", RECEIPT_SCHEMA),
)

SYSTEM = """\
Lees tickets de compra mexicanos que un teléfono ya convirtió en texto por OCR.

Devuelves EXCLUSIVAMENTE un objeto JSON, sin explicación y sin markdown:

{
  "store": "SORIANA HIPER" | null,
  "purchased_at": "2026-08-22" | null,
  "purchased_time": "19:42" | null,
  "total": "141.60" | null,
  "items": [
    {"line_no": 4, "description": "LECHE LALA ENT 1L", "amount": "28.50",
     "quantity": "2" | null, "unit_price": "20.00" | null}
  ]
}

Reglas:

1. NUNCA inventes una línea, un precio ni un producto. Si el OCR dejó una línea
   ilegible, omítela: un ticket incompleto es correcto, uno inventado no.
2. `amount` es el importe de la línea (lo que se cobró por esa partida).
   `unit_price` es el precio de UNA pieza, solo si el ticket lo imprime o si
   imprime la cantidad. Si no lo sabes, usa null.
3. `line_no` es el índice (empezando en 0) de la línea del OCR de donde sacaste
   la partida. Si la partida ocupa dos líneas, usa el índice del nombre.
4. `description` es el nombre del producto tal como está impreso, sin el código
   de barras del inicio y sin el importe del final.
5. NO son partidas: SUBTOTAL, TOTAL, IVA, EFECTIVO, CAMBIO, TARJETA, PROPINA,
   AHORRO, DESCUENTO, puntos, folios, RFC, teléfonos ni direcciones.
6. `total` es lo que el cliente pagó por la mercancía (la línea TOTAL), no el
   efectivo entregado ni el cambio.
7. Los montos van como cadenas con punto decimal: "28.50", no 28.5.
8. Fecha en formato ISO (aaaa-mm-dd). El ticket la imprime dd/mm/aaaa o
   dd/mm/aa, casi siempre al FINAL del ticket, con la hora hh:mm a su derecha.
   Si hay varias fechas, la de compra es la que va junto a una hora. Devuelve
   esa hora en `purchased_time` ("14:32"); null si no la hay.

9. El OCR viene de una foto de papel térmico y es RUIDOSO: letras sueltas al
   inicio y al final de cada línea, códigos de barras partidos, y precios con
   la letra de impuesto pegada. Solo corrige lo que está escrito: "50.004"
   es "50.00" más la letra "A"; "784.D0A" es "784.00"; "46-001" es "46.00".
   Si en la línea (o en la siguiente, cuando el precio va debajo del nombre)
   NO hay un precio con sus dígitos legibles, OMITE la partida. Nunca
   deduzcas un precio del código de barras, de otra partida ni de memoria:
   una partida con precio inventado es peor que una partida faltante.
10. No devuelvas `items: []` por ruido. Si hay al menos una línea con un
   precio legible, extrae lo que sí se lea. Solo devuelve la lista vacía si
   el texto no tiene ningún precio.

Si el texto no parece un ticket de compra (ningún precio, ninguna tienda),
devuelve {"store": null, "purchased_at": null, "purchased_time": null,
"total": null, "items": []}."""


class LlmReceiptReader:
    """Implements :class:`ReceiptReader` against the configured chat model."""

    def __init__(self, chat: ChatPort, fallback: HeuristicReceiptReader | None = None) -> None:
        self._chat = chat
        self._fallback = fallback or HeuristicReceiptReader()

    @property
    def label(self) -> str:
        return f"llm:{self._chat.model_label}"

    def read(self, lines: Sequence[str]) -> ParsedReceipt:
        lines = list(lines)[:MAX_LINES]
        baseline = self._fallback.read(lines)
        if not self._chat.available or not lines:
            return baseline

        try:
            raw = "".join(
                self._chat.stream(
                    system=SYSTEM,
                    messages=[ChatMessage(role="user", content=_numbered(lines))],
                    options=OPTIONS,
                )
            )
        except ChatUnavailable as exc:
            # Not an error the user needs to see: the ticket was still read.
            logger.info("receipt: model unavailable, kept the heuristic read (%s)", exc)
            return baseline

        proposal = self._parse(raw, lines)
        if proposal is None:
            logger.info("receipt: model answer did not parse, kept the heuristic read")
            return baseline
        return _fill_gaps(_closer_to_total(proposal, baseline), baseline, proposal)

    # --- parsing ---------------------------------------------------------
    def _parse(self, raw: str, lines: list[str]) -> ParsedReceipt | None:
        text = _FENCE.sub("", raw).strip()
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            payload = _salvage(text)
            if payload is None:
                return None
        if not isinstance(payload, dict):
            return None

        items: list[ParsedReceiptItem] = []
        for entry in payload.get("items") or []:
            item = _item(entry, lines)
            if item is not None:
                items.append(item)

        return ParsedReceipt(
            store=_text(payload.get("store")),
            purchased_at=_date(payload.get("purchased_at")),
            purchased_time=_time(payload.get("purchased_time")),
            total=_amount(payload.get("total")),
            items=items,
            reader=self.label,
        )


def _salvage(text: str) -> dict | None:
    """What can be kept of an answer that stopped mid-list.

    A model that ran out of tokens leaves ``{"store": …, "items": [{…}, {…}, {"line``
    behind. Everything up to the last complete item is still the model's
    reading and still adds up, so the list is cut there and closed. Anything
    that does not start like the object we asked for is not salvaged: guessing
    at prose is how invented items get in.
    """
    if not text.startswith("{"):
        return None
    start = text.find('"items"')
    if start < 0:
        return None
    # The last item object that closed before the cut.
    end = text.rfind("}", start)
    while end > start:
        candidate = text[: end + 1] + "]}"
        try:
            payload = json.loads(candidate)
        except ValueError:
            end = text.rfind("}", start, end)
            continue
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            logger.info("receipt: model answer was cut short; kept %d item(s)", len(payload["items"]))
            return payload
        end = text.rfind("}", start, end)
    return None


def _numbered(lines: list[str]) -> str:
    """The OCR lines with their indices, which the model answers in terms of."""
    body = "\n".join(f"{i}: {line}" for i, line in enumerate(lines))
    return f"Líneas del OCR:\n{body}"


def _fill_gaps(
    chosen: ParsedReceipt, baseline: ParsedReceipt, proposal: ParsedReceipt
) -> ParsedReceipt:
    """The winning read, with the header facts the other one saw and it missed.

    The contest is about the *items*: which list adds up. The store, the date
    and the time are single facts either reader may find, and a model that
    read every line right but answered ``purchased_at: null`` should not cost
    the ticket the date the regexes had already found at its foot. ``reader``
    stays the winner's: the items are what that label vouches for.
    """
    other = baseline if chosen is proposal else proposal
    return ParsedReceipt(
        store=chosen.store or other.store,
        purchased_at=chosen.purchased_at or other.purchased_at,
        purchased_time=chosen.purchased_time or other.purchased_time,
        total=chosen.total if chosen.total is not None else other.total,
        items=chosen.items,
        reader=chosen.reader,
    )


def _closer_to_total(proposal: ParsedReceipt, baseline: ParsedReceipt) -> ParsedReceipt:
    """Pick the read whose items add up closest to the ticket's own total.

    With no total printed there is nothing to check against, and the model's
    read is preferred: it is better at the layout, and this is precisely the
    case where the heuristic has no anchor either.

    An empty item list never wins over a non-empty one. A model that returned
    nothing has not proven the ticket is empty, it has failed to read it.
    """
    total = proposal.total or baseline.total
    if not proposal.items:
        return baseline
    if not baseline.items or total is None:
        return proposal
    return min(
        (proposal, baseline),
        key=lambda parsed: abs(sum((i.amount for i in parsed.items), Decimal("0")) - total),
    )


def _item(entry, lines: list[str]) -> ParsedReceiptItem | None:
    if not isinstance(entry, dict):
        return None
    amount = _amount(entry.get("amount"))
    description = _text(entry.get("description"))
    if amount is None or amount <= 0 or not description:
        return None
    line_no = entry.get("line_no")
    line_no = line_no if isinstance(line_no, int) and 0 <= line_no < len(lines) else -1
    # The price has to be on the ticket. A model reading noisy OCR will,
    # asked for a number, produce one; requiring the digits it names to sit
    # on the line it cites (or the one under it, where printers put the
    # arithmetic) is what keeps a guessed price out of the price history.
    if line_no < 0 or not _evidenced(amount, lines[line_no : line_no + 2]):
        return None
    quantity = _amount(entry.get("quantity"))
    return ParsedReceiptItem(
        line_no=line_no,
        # The evidence is the OCR line, not the model's paraphrase of it. When
        # the model did not say which line it read, the paraphrase is all there
        # is and is marked as such.
        raw_text=lines[line_no] if line_no >= 0 else f"~ {description} {amount}",
        description=description,
        amount=amount,
        quantity=quantity if quantity and quantity > 0 else None,
        unit_price=_amount(entry.get("unit_price")),
    )


def _evidenced(amount: Decimal, evidence: list[str]) -> bool:
    """Whether the digits of ``amount`` appear on one of the cited lines.

    Compared as digit strings so "50.004", "50-00A" and "5000" all count for
    50.00; a leading barcode (eight or more digits) is dropped first so that
    "5" is not found inside "7501005117708".
    """
    wanted = f"{amount:.2f}".replace(".", "").lstrip("0") or "0"
    for line in evidence:
        stripped = _BARCODE.sub(" ", line)
        digits = "".join(c for c in stripped if c.isdigit())
        if wanted in digits:
            return True
    return False


_BARCODE = re.compile(r"\d{8,}")


def _text(value) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _amount(value) -> Decimal | None:
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    try:
        return Decimal(value.replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        return None


def _date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _time(value) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value.strip()[:5])
    except ValueError:
        return None
