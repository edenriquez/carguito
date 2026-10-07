"""Self-transfers the wording rules cannot see (docs/redesign-plan.md §2).

``flags.py`` is deliberately conservative: it flags only explicit
card-payment / traspaso wording, because a bare "TRANSFERENCIA SPEI" to a
third party is rent, or a friend — real money leaving. This module holds the
two mechanisms that catch what conservatism misses, without loosening it:

**Taught parties.** "Eduardo Enriquez Transferencia" is the user paying
themselves, and the signal is the *name*, which only its owner can vouch for.
:class:`TransferPartyService` matches the user's declared names against
descriptions, same substring-on-normalized discipline as categorization and
aliases.

**Mirror pairing.** A transfer between two uploaded accounts leaves two
mirrored rows: same amount, opposite directions, days apart, on different
statements. :func:`pair_transfers` finds those pairs. It stays conservative
on purpose — both legs must carry transfer-ish wording, amounts must match
exactly, and each row pairs at most once — because a false pair silently
deletes real income *and* real spending from every headline number.

Pure domain: entities in, decisions out. No repository, no I/O.
"""

from __future__ import annotations

import re
from datetime import timedelta

from ..entities import Transaction
from ..value_objects.enums import TxType
from .categorization import normalize
from .flags import normalize_description

#: Generic transfer wording — the kind ``flags.py`` refuses to auto-flag
#: because the counterparty is unknown. Here it only *gates* pairing: a row
#: must at least claim to be a transfer before a mirror can confirm it is.
_TRANSFERISH = re.compile(
    r"\b(?:"
    r"transferencia|transf"
    r"|spei"
    r"|traspaso"
    r"|enviad[ao]|recibid[ao]"
    r"|a su favor"
    r")\b"
)

#: How far apart the two legs of one transfer may land. SPEI is same-day, but
#: a card payment or an ATM deposit can post days later; beyond this, equal
#: amounts are coincidence, not identity.
MAX_PAIR_GAP_DAYS = 3


class TransferPartyService:
    """Matches taught own-account names against descriptions.

    Longest-party-first, same discipline as aliases: when both "eduardo" and
    "eduardo enriquez" are taught, the more specific one is the match that
    gets reported (either way the row is a transfer, but the caller may show
    which teaching fired).
    """

    def __init__(self, parties: list[str]) -> None:
        """`parties` arrive already normalized (the store's contract)."""
        self._parties = sorted((p for p in parties if p), key=len, reverse=True)

    def match(self, raw_description: str) -> str | None:
        # `normalize` (categorization's), not flags' `normalize_description`:
        # it also strips punctuation, and bank formatting varies exactly there
        # — "EDUARDO YAEL,ENRIQUEZ/TAPIA" and "Eduardo Yael Enriquez Tapia"
        # are the same person and must match the same taught party.
        norm = normalize(raw_description)
        for party in self._parties:
            if party in norm:
                return party
        return None

    def is_own(self, raw_description: str) -> bool:
        return self.match(raw_description) is not None


def _pairable(t: Transaction) -> bool:
    """A row the mirror search may flag.

    ``transfer_source == "user"`` rows are out: an unflagged one was a human
    saying "this is real money", and pairing over it would overrule them.
    """
    return (
        not t.is_transfer
        and t.transfer_source != "user"
        and not t.excluded_from_stats
        and bool(_TRANSFERISH.search(normalize_description(t.raw_description)))
    )


def _anchor(t: Transaction) -> bool:
    """A row already established as a transfer, usable as a mirror's evidence.

    No wording requirement: being flagged IS the evidence. When the taught
    party flags the Nu side of a send, the Azteca side ("TRANSFERENCIA SPEI A
    SU FAVOR", same amount, next day) is the other half of the same move —
    demanding it pair only with *unflagged* rows would leave it counted as
    income forever precisely because the system already understood its twin.
    """
    return t.is_transfer and not t.excluded_from_stats


def pair_transfers(transactions: list[Transaction]) -> list[tuple[Transaction, Transaction]]:
    """Mirrored self-transfer pairs among a user's rows.

    A pair is: exact same amount, opposite directions, different statements,
    dates at most :data:`MAX_PAIR_GAP_DAYS` apart. Both fresh legs must carry
    transfer wording; a leg already flagged as a transfer (an anchor) needs no
    wording — being flagged is the evidence — and confirms its unflagged
    mirror. Greedy nearest-date matching, one pair per row — a month with two
    identical 5,000 sends and one 5,000 receive pairs once and leaves the odd
    leg alone.

    Pairs may contain an already-flagged anchor: callers flag only the legs
    that need it.
    """
    fresh = [t for t in transactions if _pairable(t)]
    anchors = [t for t in transactions if _anchor(t)]

    by_amount: dict[str, tuple[list[Transaction], list[Transaction]]] = {}
    for t in fresh:
        outs, ins = by_amount.setdefault(str(t.amount), ([], []))
        (outs if t.tx_type is TxType.EXPENSE else ins).append(t)

    pairs: list[tuple[Transaction, Transaction]] = []
    for outs, ins in by_amount.values():
        _match_greedy(outs, ins, pairs)

    # Anything still unmatched gets one chance against an anchor mirror.
    matched = {id(t) for pair in pairs for t in pair}
    anchors_by_amount: dict[str, tuple[list[Transaction], list[Transaction]]] = {}
    for t in anchors:
        outs, ins = anchors_by_amount.setdefault(str(t.amount), ([], []))
        (outs if t.tx_type is TxType.EXPENSE else ins).append(t)
    for amount, (outs, ins) in by_amount.items():
        a_outs, a_ins = anchors_by_amount.get(amount, ([], []))
        _match_greedy([t for t in outs if id(t) not in matched], a_ins, pairs)
        _match_greedy(a_outs, [t for t in ins if id(t) not in matched], pairs)
    return pairs


def _match_greedy(
    outs: list[Transaction],
    ins: list[Transaction],
    pairs: list[tuple[Transaction, Transaction]],
) -> None:
    """Nearest-date one-to-one matching between two opposite-direction sets."""
    if not outs or not ins:
        return
    max_gap = timedelta(days=MAX_PAIR_GAP_DAYS)
    remaining = sorted(ins, key=lambda t: t.tx_date)
    for out in sorted(outs, key=lambda t: t.tx_date):
        best_i = -1
        best_gap = max_gap + timedelta(days=1)
        for i, cand in enumerate(remaining):
            if cand.statement_id == out.statement_id:
                continue
            gap = abs(cand.tx_date - out.tx_date)
            if gap <= max_gap and gap < best_gap:
                best_i, best_gap = i, gap
        if best_i >= 0:
            pairs.append((out, remaining.pop(best_i)))
