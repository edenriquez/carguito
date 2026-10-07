from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from ..ports.outbound import CubeWriter, TagRepository, TransactionRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RebuildCubeResult:
    user_id: UUID
    rows: int


class RebuildCubeUseCase:
    """Re-derive one user's cube rows from the relational tables.

    The cube is derived state; the relational tables are the record of truth.
    Being able to rebuild on demand is what lets the cube be treated as
    disposable — every later backfill (transfer flags, dedup fingerprints,
    tags) becomes "change the projection, rebuild" instead of a bespoke
    migration against DuckDB.

    Orchestration lives here rather than inside the cube adapter so that the
    adapter never depends on a repository: the use case owns both ports.
    """

    def __init__(
        self,
        transactions: TransactionRepository,
        cube: CubeWriter,
        tags: TagRepository | None = None,
    ) -> None:
        self._transactions = transactions
        self._cube = cube
        self._tags = tags

    def execute(self, *, user_id: UUID) -> RebuildCubeResult:
        if self._tags is not None:
            # The tag dimension is derived too: a rebuild that restored the
            # bridge but not the labels would render a breakdown of
            # "Etiqueta eliminada".
            self._cube.sync_tags(self._tags.list_for_user(user_id))
        rows = self._cube.rebuild_for_user(user_id, self._transactions.iter_for_user(user_id))
        logger.info("Rebuilt cube for user %s: %s fact row(s).", user_id, rows)
        return RebuildCubeResult(user_id=user_id, rows=rows)
