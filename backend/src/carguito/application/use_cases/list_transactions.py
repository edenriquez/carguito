from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.entities import Transaction
from ..ports.outbound import TransactionRepository


@dataclass(frozen=True)
class TransactionPage:
    items: list[Transaction]
    total: int
    limit: int
    offset: int


class ListTransactionsUseCase:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(
        self,
        *,
        user_id: UUID,
        start: date | None = None,
        end: date | None = None,
        category_id: UUID | None = None,
        search: str | None = None,
        statement_ids: list[UUID] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> TransactionPage:
        items = self._transactions.list_for_user(
            user_id,
            start=start,
            end=end,
            statement_ids=statement_ids,
            category_id=category_id,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = self._transactions.count_for_user(
            user_id,
            start=start,
            end=end,
            category_id=category_id,
            search=search,
            statement_ids=statement_ids,
        )
        return TransactionPage(items=items, total=total, limit=limit, offset=offset)
