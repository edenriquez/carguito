"""Rename every similar transaction — the alias that sticks.

The sibling of :mod:`recategorize`: one taught label, applied over existing
history and remembered (``user_aliases``) so ingest renames future uploads.
Only ``description`` — the human-facing, editable field — is ever written;
``raw_description`` keeps the bank's text, so an alias never destroys
evidence and is always reversible.

The honesty rule for the bulk pass: a row is renamed only if its description
is still the bank's own text (``description == raw_description``) or is a
previous alias for this same label. A description the user typed by hand on
one specific row is theirs, and a bulk rename that steamrolls it would be the
same sin as recategorizing a human-corrected category.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from ...domain.entities import Transaction
from ...domain.services.categorization import normalize
from ..ports.outbound import CubeWriter, TransactionRepository, UserAliasRepository
from .recategorize import MIN_LABEL_LENGTH, InvalidLabelError


@dataclass(frozen=True)
class RealiasResult:
    matched: int
    updated: int
    label: str


class RealiasUseCase:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        user_aliases: UserAliasRepository,
        cube: CubeWriter,
    ) -> None:
        self._transactions = transactions
        self._user_aliases = user_aliases
        self._cube = cube

    def execute(
        self, *, user_id: UUID, label: str, alias: str, dry_run: bool = False
    ) -> RealiasResult:
        norm_label = normalize(label)
        if len(norm_label) < MIN_LABEL_LENGTH:
            raise InvalidLabelError(
                f"Label {label!r} is too short after normalization; "
                f"need at least {MIN_LABEL_LENGTH} characters"
            )
        clean_alias = alias.strip()
        if not clean_alias:
            raise InvalidLabelError("Alias must not be empty")

        # A previous alias for this label may sit on rows already — those are
        # machine-written and fair game for the replacement.
        previous = dict(self._user_aliases.list_for_user(user_id)).get(norm_label)

        matched: list[Transaction] = []
        for t in self._transactions.iter_for_user(user_id):
            if norm_label not in normalize(t.raw_description):
                continue
            if t.description == clean_alias:
                continue  # already reads right
            machine_owned = (
                t.description == t.raw_description
                or (previous is not None and t.description == previous)
            )
            if machine_owned:
                matched.append(t)

        if dry_run:
            return RealiasResult(matched=len(matched), updated=0, label=norm_label)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for t in matched:
            t.description = clean_alias
            t.updated_at = now
            self._transactions.update(t)
        if matched:
            self._cube.upsert_transactions(matched)

        # Remembered even when nothing matched today: the point is the next
        # statement, which hasn't been uploaded yet.
        self._user_aliases.upsert(user_id, norm_label, clean_alias)

        return RealiasResult(matched=len(matched), updated=len(matched), label=norm_label)
