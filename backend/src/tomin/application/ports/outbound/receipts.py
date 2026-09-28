"""The seam between "someone read the ticket" and "the application stores it".

Two implementations ship, and the split is the same one the chat port makes:
the deterministic one always works, the model-backed one works better, and
nothing above this line knows which is wired.

* ``HeuristicReceiptReader`` — regexes over the OCR lines. No key, no network,
  no third party sees the basket.
* ``LlmReceiptReader`` — the configured model, which reads a mangled
  two-column thermal print far better than a regex can, and falls back to the
  heuristic whenever its answer does not survive checking.

Both are handed the *lines*, never an image. From the phone the photo stays
on the phone (docs/custody-plan.md G1/G2); from the web it is uploaded, read
by :class:`ReceiptImageOcr` below in memory, and discarded — the same honesty
the web's statement upload already has. Either way, what is stored is text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ...dtos.receipts import ParsedReceipt


@runtime_checkable
class ReceiptImageOcr(Protocol):
    """Turns a photo of a ticket into the printed rows, top to bottom.

    The web's way in. The phone reads its own photos; a browser has no
    recognizer worth the name (Tesseract on thermal print reads a third of
    the prices), so the web sends the image and the server reads it here,
    in memory, and keeps nothing but the rows.
    """

    #: Name of the engine, stored on the receipt as its ``extractor``.
    label: str

    def read(self, image: bytes) -> list[str]:
        """Rows of text in reading order; empty when nothing was found.

        Raises :class:`UnreadableImageError` only when the bytes are not an
        image at all — a photo of a table with no ticket on it returns ``[]``.
        """
        ...


class UnreadableImageError(Exception):
    """The upload could not be decoded as an image."""


@runtime_checkable
class ReceiptReader(Protocol):
    """Turns OCR lines into a store, a date, a total and product lines."""

    def read(self, lines: Sequence[str]) -> ParsedReceipt:
        """Never raises for unreadable input.

        A ticket that yields nothing returns an empty :class:`ParsedReceipt`,
        because "I could not read this photo" is an answer the user can act on
        (retake it) and an exception here would lose the upload instead.
        """
        ...
