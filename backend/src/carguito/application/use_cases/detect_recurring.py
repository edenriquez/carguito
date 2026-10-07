from __future__ import annotations

from uuid import UUID

from ...domain.services.recurrence import RecurrenceService
from ..dtos.analytics import RecurringCharge, RecurringItem
from ..ports.outbound import TransactionRepository, UserAliasRepository


class DetectRecurringUseCase:
    """Detects recurring expenses / subscriptions for a user."""

    def __init__(
        self,
        transactions: TransactionRepository,
        user_aliases: UserAliasRepository,
        service: RecurrenceService | None = None,
    ) -> None:
        self._transactions = transactions
        self._user_aliases = user_aliases
        self._service = service or RecurrenceService()

    def execute(
        self, *, user_id: UUID, statement_ids: list[UUID] | None = None
    ) -> list[RecurringItem]:
        # Pull a generous window; recurrence needs history.
        txs = self._transactions.list_for_user(
            user_id, statement_ids=statement_ids, limit=10000
        )
        # Taught aliases outrank the text heuristic as series identity.
        groups = self._service.detect(txs, self._user_aliases.list_for_user(user_id))
        return [
            RecurringItem(
                key=g.key,
                label=g.label,
                occurrences=g.occurrences,
                frequency=g.frequency,
                typical_amount=g.typical_amount,
                monthly_equivalent=g.monthly_equivalent,
                amount_stable=g.amount_stable,
                last_date=g.last_date.isoformat(),
                next_expected=g.next_expected.isoformat(),
                category_id=str(g.category_id) if g.category_id else None,
                charges=tuple(
                    RecurringCharge(date=c.date.isoformat(), amount=c.amount)
                    for c in g.charges
                ),
            )
            for g in groups
        ]
