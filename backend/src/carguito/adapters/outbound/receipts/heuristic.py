from __future__ import annotations

from collections.abc import Sequence

from ....application.dtos.receipts import ParsedReceipt
from ....domain.services.receipt_reading import read_receipt


class HeuristicReceiptReader:
    """The reader that always works: regexes, no key, no network.

    A thin adapter over ``domain/services/receipt_reading.py`` — the rules live
    in the domain because they are the product's opinion about what a ticket
    is, not an integration detail. What lives here is only the port shape.
    """

    label = "heuristic"

    def read(self, lines: Sequence[str]) -> ParsedReceipt:
        return read_receipt(list(lines))
