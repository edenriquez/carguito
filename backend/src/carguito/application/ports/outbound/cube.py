from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID

from ....domain.entities import Tag, Transaction
from ...dtos.analytics import CategorySpend, MonthlyPoint, SpendingSummary


@runtime_checkable
class CubeWriter(Protocol):
    """Feeds structured transactions into the analytics cube (DuckDB)."""

    def upsert_transactions(self, transactions: list[Transaction]) -> None: ...

    def delete_transactions(self, tx_ids: list[UUID]) -> None: ...

    def sync_tags(self, tags: list[Tag]) -> None:
        """Refresh the tag dimension so a breakdown by tag has labels."""
        ...

    def forget_tag(self, tag_id: UUID) -> None:
        """Drop a deleted tag from the dimension and the bridge."""
        ...

    def rebuild_for_user(self, user_id: UUID, transactions: Iterable[Transaction]) -> int:
        """Drop this user's facts and re-derive them from ``transactions``.

        Returns the number of rows written. The caller supplies the source data
        so that the cube adapter never depends on a repository.
        """
        ...


@runtime_checkable
class CubeReader(Protocol):
    """Fast analytical reads served from the cube."""

    # `currency` is not optional in meaning, only in syntax: aggregating across
    # currencies yields a number denominated in nothing.
    def spending_summary(
        self,
        user_id: UUID,
        start: date | None = None,
        end: date | None = None,
        currency: str = "MXN",
    ) -> SpendingSummary: ...

    def spending_by_category(
        self,
        user_id: UUID,
        start: date | None = None,
        end: date | None = None,
        currency: str = "MXN",
    ) -> list[CategorySpend]: ...

    def monthly_series(self, user_id: UUID, months: int = 12) -> list[MonthlyPoint]: ...
