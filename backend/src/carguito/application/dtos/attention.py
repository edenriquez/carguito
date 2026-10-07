from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AttentionDTO:
    """A charge the chart should ring, with the sentence that justifies it."""

    transaction_id: str
    kind: str  # unusual_amount | possible_duplicate | new_merchant
    reason: str
    ratio: Decimal | None
    related_ids: tuple[str, ...]
    severity: str  # warn | info
