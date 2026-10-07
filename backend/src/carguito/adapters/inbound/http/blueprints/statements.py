from __future__ import annotations

from uuid import UUID

from flask import Blueprint, jsonify, request

from .....application.use_cases.statements import UNSET, UnsetType
from .....domain.value_objects.enums import AccountKind
from ..auth import current_user_id, get_container
from ..serialization import statement_json

statements_bp = Blueprint("statements", __name__, url_prefix="/api/statements")


@statements_bp.get("")
def list_statements():
    """List the statements ingested for the current user, newest first."""
    user_id = current_user_id()
    items = get_container().manage_statements.list(user_id=user_id)
    return jsonify(items=[statement_json(s) for s in items], total=len(items))


@statements_bp.post("")
def upload_statement():
    """Accept a transient statement upload (PDF or SAT XML) and process it.

    The raw file is parsed then discarded; only structured data is stored.
    """
    user_id = current_user_id()
    if "file" not in request.files:
        return jsonify(error="No file part named 'file'"), 400

    upload = request.files["file"]
    data = upload.read()
    if not data:
        return jsonify(error="Empty file"), 400

    # Only for encrypted PDFs. Used once to open the document, then dropped
    # with the rest of the request — it is never persisted or logged.
    password = request.form.get("password") or None

    container = get_container()
    result = container.process_file.execute(
        user_id=user_id,
        data=data,
        filename=upload.filename or "upload",
        mime=upload.mimetype,
        password=password,
    )
    # The full statement rides along so the onboarding review step can show
    # what the OCR understood (bank, period) without a second round trip.
    statement = container.manage_statements.get(
        user_id=user_id, statement_id=result.statement_id
    )
    return (
        jsonify(
            statement_id=str(result.statement_id),
            template=result.template,
            transactions_created=result.transactions_created,
            statement=statement_json(statement),
        ),
        201,
    )


@statements_bp.patch("/<statement_id>")
def update_statement(statement_id: str):
    """Update the user-editable fields of a statement.

    Exactly two: ``account_kind`` and ``bank``. Explicit ``null`` clears a
    field; an absent key leaves it alone; a body naming neither is a 400
    rather than a silent no-op.
    """
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    unknown = set(body) - {"account_kind", "bank"}
    if unknown:
        return jsonify(error=f"Unsupported fields: {sorted(unknown)}"), 400
    if not body:
        return jsonify(error="Provide 'account_kind' and/or 'bank'"), 400

    kind: AccountKind | None | UnsetType = UNSET
    if "account_kind" in body:
        raw = body["account_kind"]
        if raw is None:
            kind = None
        else:
            try:
                kind = AccountKind(raw)
            except ValueError:
                valid = ", ".join(k.value for k in AccountKind)
                return (
                    jsonify(error=f"Invalid account_kind {raw!r}; expected one of: {valid}"),
                    400,
                )

    bank: str | None | UnsetType = UNSET
    if "bank" in body:
        raw_bank = body["bank"]
        if raw_bank is not None:
            if not isinstance(raw_bank, str) or not raw_bank.strip():
                return jsonify(error="'bank' must be a non-empty string or null"), 400
            if len(raw_bank.strip()) > 120:
                return jsonify(error="'bank' must be 120 characters or fewer"), 400
            bank = raw_bank.strip()
        else:
            bank = None

    statement = get_container().manage_statements.update(
        user_id=user_id, statement_id=UUID(statement_id), kind=kind, bank=bank
    )
    return jsonify(statement_json(statement))


@statements_bp.delete("/<statement_id>")
def delete_statement(statement_id: str):
    """Delete a statement and every transaction derived from it.

    Only the server-side structured data is removed; the user's own copy of the
    raw file lives on their device.
    """
    user_id = current_user_id()
    result = get_container().manage_statements.delete(
        user_id=user_id, statement_id=UUID(statement_id)
    )
    return jsonify(
        statement_id=str(result.statement_id),
        transactions_deleted=result.transactions_deleted,
    )
