from __future__ import annotations

import csv
import io
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from .....application.use_cases.update_transaction import UNSET
from ..auth import current_user_id, get_container
from ..serialization import attention_json, transaction_json
from ._helpers import query_date, query_int

transactions_bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")


def _filters():
    category = request.args.get("category_id")
    # Repeatable: ?statement_id=a&statement_id=b scopes to those documents —
    # the seam the bank filter reaches through (ids are stable; bank labels
    # are user-editable).
    statement_ids = [UUID(v) for v in request.args.getlist("statement_id")]
    return {
        "start": query_date("start"),
        "end": query_date("end"),
        "category_id": UUID(category) if category else None,
        "search": request.args.get("search"),
        "statement_ids": statement_ids or None,
    }


@transactions_bp.get("")
def list_transactions():
    user_id = current_user_id()
    filters = _filters()
    page = get_container().list_transactions.execute(
        user_id=user_id,
        limit=query_int("limit", 100),
        offset=query_int("offset", 0),
        **filters,
    )
    return jsonify(
        items=[transaction_json(t) for t in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@transactions_bp.get("/attention")
def attention():
    """Charges in the window worth a second look — the rings on the scatter.

    Scoped like the list (``start``/``end``, repeatable ``statement_id``) so the
    rings sit on dots that are actually drawn; the baselines behind each
    reason come from the whole scoped history, not just the window.
    """
    user_id = current_user_id()
    filters = _filters()
    items = get_container().list_attention.execute(
        user_id=user_id,
        start=filters["start"],
        end=filters["end"],
        statement_ids=filters["statement_ids"],
    )
    return jsonify(items=[attention_json(i) for i in items])


@transactions_bp.get("/span")
def transaction_span():
    """Where the ledger starts and ends. The time filter anchors on ``last``.

    Scoped like the list (repeatable ``statement_id``) so "15 días" under a
    bank filter means the last 15 days *of that bank's* history.
    """
    statement_ids = [UUID(v) for v in request.args.getlist("statement_id")] or None
    first, last = get_container().transactions.span_for_user(
        current_user_id(), statement_ids=statement_ids
    )
    return jsonify(
        first=first.isoformat() if first else None,
        last=last.isoformat() if last else None,
    )


@transactions_bp.post("/recategorize")
def recategorize():
    """Apply a category to every similar machine-categorized transaction.

    Body: ``{"category_id", "label", "dry_run"?}``. With ``dry_run`` true,
    nothing is written and ``matched`` reports the blast radius — the client
    shows that number before the user commits. The real run also stores the
    label in the user's vocabulary so future uploads categorize themselves.
    """
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    raw_category = body.get("category_id")
    label = body.get("label")
    if not raw_category or not isinstance(label, str):
        return jsonify(error="Provide 'category_id' and 'label'"), 400

    result = get_container().recategorize.execute(
        user_id=user_id,
        category_id=UUID(raw_category),
        label=label,
        dry_run=bool(body.get("dry_run", False)),
    )
    return jsonify(matched=result.matched, updated=result.updated, label=result.label)


@transactions_bp.post("/realias")
def realias():
    """Rename every similar machine-named transaction, and remember the alias.

    Body: ``{"label", "alias", "dry_run"?}``. Matching is on
    ``raw_description``; only descriptions still equal to the bank's text (or
    to this label's previous alias) are rewritten — a name the user typed on
    one row by hand is never steamrolled. The real run stores the alias so
    ingest renames future uploads too.
    """
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    label = body.get("label")
    alias = body.get("alias")
    if not isinstance(label, str) or not isinstance(alias, str):
        return jsonify(error="Provide 'label' and 'alias'"), 400

    result = get_container().realias.execute(
        user_id=user_id,
        label=label,
        alias=alias,
        dry_run=bool(body.get("dry_run", False)),
    )
    return jsonify(matched=result.matched, updated=result.updated, label=result.label)


@transactions_bp.post("/mark-transfer")
def mark_transfer():
    """Flag every movement whose counterparty is the user themselves.

    Body: ``{"party", "dry_run"?}``. ``party`` is a name or account label the
    user vouches for ("eduardo enriquez"); matching is a substring of the
    normalized ``raw_description``, same discipline as recategorize/realias.
    With ``dry_run`` true nothing is written and ``matched`` reports the blast
    radius. The real run also remembers the party so ingest flags future
    uploads by itself. Rows the user corrected by hand are never touched.
    """
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    party = body.get("party")
    if not isinstance(party, str):
        return jsonify(error="Provide 'party'"), 400

    result = get_container().mark_transfer.execute(
        user_id=user_id,
        party=party,
        dry_run=bool(body.get("dry_run", False)),
    )
    return jsonify(matched=result.matched, updated=result.updated, party=result.party)


@transactions_bp.post("/pair-transfers")
def pair_transfers():
    """Find and flag mirrored self-transfer legs across the user's statements.

    Same amount, opposite directions, different statements, dates at most a
    few days apart, both legs transfer-worded. Runs automatically inside every
    ingest; this endpoint exists to backfill history uploaded before the rule.
    Body: ``{"dry_run"?}`` — with ``dry_run`` true, ``pairs`` reports how many
    would be flagged without writing.
    """
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    result = get_container().pair_transfers.execute(
        user_id=user_id, dry_run=bool(body.get("dry_run", False))
    )
    return jsonify(pairs=result.pairs, updated=result.updated)


@transactions_bp.patch("/<transaction_id>")
def update_transaction(transaction_id: str):
    """Apply a user's correction to one transaction.

    Only keys actually present in the body are applied. That distinction is
    load-bearing: ``{"category_id": null}`` means *clear the category*, whereas
    omitting the key means *leave it alone*, and a plain ``body.get()`` would
    collapse the two.
    """
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error="Body must be an object"), 400

    unknown = set(body) - _PATCHABLE
    if unknown:
        return jsonify(error=f"Unsupported fields: {sorted(unknown)}"), 400

    transaction = get_container().update_transaction.execute(
        user_id=user_id,
        transaction_id=UUID(transaction_id),
        category_id=_optional_uuid(body, "category_id"),
        description=body.get("description", UNSET),
        notes=body.get("notes", UNSET),
        excluded_from_stats=body.get("excluded_from_stats", UNSET),
        is_transfer=body.get("is_transfer", UNSET),
    )
    return jsonify(transaction_json(transaction))


#: The only fields a user may rewrite. Date, amount, currency and direction come
#: from the statement; letting a client edit them would make an ingest bug
#: indistinguishable from a correction. `is_transfer` is patchable because the
#: machine's answer is a guess only the user can truly settle.
_PATCHABLE = {"category_id", "description", "notes", "excluded_from_stats", "is_transfer"}


def _optional_uuid(body: dict, key: str):
    if key not in body:
        return UNSET
    raw = body[key]
    return UUID(raw) if raw is not None else None


@transactions_bp.put("/<transaction_id>/tags")
def set_transaction_tags(transaction_id: str):
    """Replace this transaction's tag list.

    PUT, not PATCH: the client edits the list as a unit, and "these are its
    tags now" is a simpler thing to get right than an add/remove diff.
    """
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    raw = body.get("tag_ids")
    if not isinstance(raw, list):
        return jsonify(error="'tag_ids' must be a list of ids"), 400

    tag_ids = get_container().manage_tags.set_for_transaction(
        user_id=user_id,
        transaction_id=UUID(transaction_id),
        tag_ids=[UUID(value) for value in raw],
    )
    return jsonify(
        transaction_id=transaction_id, tag_ids=[str(t) for t in tag_ids]
    )


@transactions_bp.get("/export.csv")
def export_csv():
    user_id = current_user_id()
    filters = _filters()
    page = get_container().list_transactions.execute(
        user_id=user_id, limit=100000, offset=0, **filters
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "description", "amount", "currency", "type", "status"])
    for t in page.items:
        writer.writerow(
            [t.tx_date.isoformat(), t.description, t.amount, t.currency,
             t.tx_type.value, t.status.value]
        )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )
