"""Mark self-transfers the wording rules cannot see — and remember why.

Two entry points over the same idea (domain/services/transfers.py):

- ``MarkTransferPartyUseCase``: the user vouches that a counterparty is
  themselves ("Eduardo Enriquez"). Bulk-flags every matching movement and
  stores the party so ingest flags future uploads by itself — the same
  correct-once-learn-forever contract as recategorize/realias.

- ``PairTransfersUseCase``: finds mirrored legs across the user's statements
  (same amount, opposite directions, days apart) and flags both. Runs inside
  every ingest; exposed separately so existing history can be backfilled.

Both write ``transfer_source="auto"``: they are machine passes, and a later,
better pass may legitimately re-touch their work. Only a human edit locks a
row (``update_transaction`` writes ``"user"``), and both passes skip those.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from ...domain.entities import Transaction
from ...domain.services.categorization import normalize
from ...domain.services.transfers import TransferPartyService, pair_transfers
from ..ports.outbound import CubeWriter, TransactionRepository, UserTransferPartyRepository
from .recategorize import MIN_LABEL_LENGTH, InvalidLabelError


@dataclass(frozen=True)
class MarkTransferResult:
    matched: int
    updated: int
    party: str


@dataclass(frozen=True)
class PairTransfersResult:
    pairs: int
    updated: int


def _flag(t: Transaction, now: datetime) -> None:
    t.is_transfer = True
    # Domain rule (flags.py): a transfer is never a cash withdrawal — no bill
    # left an ATM when the money moved between the user's own accounts.
    t.is_cash_withdrawal = False
    t.transfer_source = "auto"
    t.updated_at = now


class MarkTransferPartyUseCase:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        transfer_parties: UserTransferPartyRepository,
        cube: CubeWriter,
    ) -> None:
        self._transactions = transactions
        self._transfer_parties = transfer_parties
        self._cube = cube

    def execute(
        self, *, user_id: UUID, party: str, dry_run: bool = False
    ) -> MarkTransferResult:
        norm_party = normalize(party)
        if len(norm_party) < MIN_LABEL_LENGTH:
            raise InvalidLabelError(
                f"Party {party!r} is too short after normalization; "
                f"need at least {MIN_LABEL_LENGTH} characters"
            )

        service = TransferPartyService([norm_party])
        matched: list[Transaction] = []
        for t in self._transactions.iter_for_user(user_id):
            if t.is_transfer:
                continue
            # A human said "this is real money" — that answer stands.
            if t.transfer_source == "user":
                continue
            if service.is_own(t.raw_description):
                matched.append(t)

        if dry_run:
            return MarkTransferResult(matched=len(matched), updated=0, party=norm_party)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for t in matched:
            _flag(t, now)
            self._transactions.update(t)
        if matched:
            self._cube.upsert_transactions(matched)

        # Remembered even when nothing matched today: the point is the NEXT
        # statement, which hasn't been uploaded yet.
        self._transfer_parties.add(user_id, norm_party)

        return MarkTransferResult(matched=len(matched), updated=len(matched), party=norm_party)


class PairTransfersUseCase:
    def __init__(
        self, *, transactions: TransactionRepository, cube: CubeWriter
    ) -> None:
        self._transactions = transactions
        self._cube = cube

    def execute(self, *, user_id: UUID, dry_run: bool = False) -> PairTransfersResult:
        ledger = list(self._transactions.iter_for_user(user_id))
        pairs = pair_transfers(ledger)
        if dry_run:
            return PairTransfersResult(pairs=len(pairs), updated=0)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        touched: list[Transaction] = []
        for out, into in pairs:
            for t in (out, into):
                # A pair may lean on an already-flagged anchor — only the
                # fresh leg needs writing.
                if t.is_transfer:
                    continue
                _flag(t, now)
                self._transactions.update(t)
                touched.append(t)
        if touched:
            self._cube.upsert_transactions(touched)

        return PairTransfersResult(pairs=len(pairs), updated=len(touched))
