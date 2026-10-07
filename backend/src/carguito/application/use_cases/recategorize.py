"""Apply a category to every similar transaction — the correction that teaches.

One correction on one OXXO row is data entry; the same correction applied to
the other 40 OXXO rows, and remembered for the next upload, is a system that
learns. This use case does both: bulk-apply over the existing history and
persist the label into the user's vocabulary (``user_category_labels``), which
``ProcessFileUseCase`` feeds back into ``CategorizationService`` on every
subsequent upload.

`dry_run` exists because the client shows the blast radius before committing —
"«oxxo» aparece en 12 movimientos más" — and a preview that mutates is a trap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from ...domain.entities import Transaction
from ...domain.services.categorization import normalize
from ..ports.outbound import (
    CategoryRepository,
    CubeWriter,
    TransactionRepository,
    UserLabelRepository,
)
from .update_transaction import UnknownCategoryError


class InvalidLabelError(ValueError):
    """The label is too short to mean anything — it would match everything."""


#: Below this, a normalized label is noise ("a" matches half the ledger).
MIN_LABEL_LENGTH = 3


@dataclass(frozen=True)
class RecategorizeResult:
    matched: int
    updated: int
    label: str


class RecategorizeUseCase:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        categories: CategoryRepository,
        user_labels: UserLabelRepository,
        cube: CubeWriter,
    ) -> None:
        self._transactions = transactions
        self._categories = categories
        self._user_labels = user_labels
        self._cube = cube

    def execute(
        self, *, user_id: UUID, category_id: UUID, label: str, dry_run: bool = False
    ) -> RecategorizeResult:
        norm_label = normalize(label)
        if len(norm_label) < MIN_LABEL_LENGTH:
            raise InvalidLabelError(
                f"Label {label!r} is too short after normalization; "
                f"need at least {MIN_LABEL_LENGTH} characters"
            )
        if not any(c.id == category_id for c in self._categories.get_all()):
            raise UnknownCategoryError(str(category_id))

        matched: list[Transaction] = []
        for t in self._transactions.iter_for_user(user_id):
            # Human edits are sacred: only machine-assigned rows are touched.
            if t.category_source != "auto":
                continue
            if t.category_id == category_id:
                continue
            if norm_label in normalize(t.description or t.raw_description):
                matched.append(t)

        if dry_run:
            return RecategorizeResult(matched=len(matched), updated=0, label=norm_label)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for t in matched:
            t.category_id = category_id
            # Stays "auto": the machine applied it, and a later, more specific
            # label may legitimately re-touch it. Only a human edit locks a row.
            t.category_source = "auto"
            t.updated_at = now
            self._transactions.update(t)

        if matched:
            # One batched cube write, not one per row.
            self._cube.upsert_transactions(matched)

        # Remember the vocabulary even when nothing matched today — the point
        # is the NEXT statement, which hasn't been uploaded yet.
        self._user_labels.add(user_id, category_id, norm_label)

        return RecategorizeResult(matched=len(matched), updated=len(matched), label=norm_label)
