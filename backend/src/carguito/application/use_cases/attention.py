from __future__ import annotations

from datetime import date
from uuid import UUID

from ...domain.services.attention import AttentionService
from ..dtos.attention import AttentionDTO
from ..ports.outbound import TransactionRepository

#: The chart rings one thing at a time and the chips list a handful; past this
#: the "lecturas" stop being a reading and become another list.
MAX_ITEMS = 20


class ListAttentionUseCase:
    """Charges in a window worth a second look, judged against the whole history."""

    def __init__(
        self, transactions: TransactionRepository, service: AttentionService | None = None
    ) -> None:
        self._transactions = transactions
        self._service = service or AttentionService()

    def execute(
        self,
        *,
        user_id: UUID,
        start: date | None = None,
        end: date | None = None,
        statement_ids: list[UUID] | None = None,
    ) -> list[AttentionDTO]:
        # The whole scoped ledger: "what you usually spend there" needs the
        # months before the window, and "first time" needs everything.
        history = self._transactions.list_for_user(
            user_id, statement_ids=statement_ids, limit=10000
        )
        items = self._service.detect(history, start=start, end=end)[:MAX_ITEMS]
        return [
            AttentionDTO(
                transaction_id=str(i.transaction_id),
                kind=i.kind,
                reason=i.reason,
                ratio=i.ratio,
                related_ids=tuple(str(r) for r in i.related_ids),
                severity=i.severity,
            )
            for i in items
        ]
