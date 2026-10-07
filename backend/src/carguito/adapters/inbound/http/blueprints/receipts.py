from __future__ import annotations

from uuid import UUID

from flask import Blueprint, jsonify, request

from .....application.ports.outbound import UnreadableImageError
from .....application.use_cases.receipts import (
    DuplicateReceiptError,
    NoTextInImageError,
    ReceiptNotFoundError,
    ReceiptOcrUnavailableError,
    TransactionAlreadyHasReceiptError,
    UnknownTransactionError,
)
from ..auth import current_user_id, get_container
from ..serialization import receipt_json
from ._helpers import query_int
from .ingest import _timestamp, receipt_result_json

#: A phone photo re-encoded by the browser is well under a megabyte; this
#: is a sanity cap, not a budget.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

receipts_bp = Blueprint("receipts", __name__, url_prefix="/api/receipts")


@receipts_bp.get("")
def list_receipts():
    receipts, total = get_container().manage_receipts.list(
        user_id=current_user_id(),
        limit=query_int("limit", 50),
        offset=query_int("offset", 0),
    )
    return jsonify(items=[receipt_json(r) for r in receipts], total=total)


@receipts_bp.post("/upload")
def upload_receipt():
    """A ticket photo from the web, read here and discarded.

    Multipart: ``file`` (the image), optional ``captured_at`` (ISO-8601, when
    the photo was taken) and ``transaction_id``. The bytes live for the
    length of the request: the OCR reads them in memory, the rows go through
    the same pipeline the phone's text does, and nothing of the image is
    kept — not on disk, not in a log line. Same answer shape as
    ``POST /api/ingest/receipt``.
    """
    container = get_container()
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(error="Falta la foto del ticket ('file')"), 400
    image = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(image) > MAX_UPLOAD_BYTES:
        return jsonify(error="La foto pesa demasiado; bájale la resolución"), 413

    raw_transaction = request.form.get("transaction_id") or None
    try:
        transaction_id = UUID(raw_transaction) if raw_transaction else None
    except ValueError:
        return jsonify(error="'transaction_id' must be a UUID"), 400

    try:
        result = container.ingest_receipt_image.execute(
            user_id=current_user_id(),
            image=image,
            captured_at=_timestamp(request.form.get("captured_at")),
            transaction_id=transaction_id,
        )
    except ReceiptOcrUnavailableError:
        return (
            jsonify(
                error="Este servidor no tiene OCR para tickets. "
                "Instala el extra: pip install '.[receipts]'"
            ),
            503,
        )
    except UnreadableImageError:
        return jsonify(error="No pude abrir esta imagen. Entran JPG, PNG o WebP."), 415
    except NoTextInImageError:
        return jsonify(error="No alcancé a leer texto en la foto. Prueba con más luz y la foto derecha."), 422
    except DuplicateReceiptError:
        return jsonify(error="Esta foto ya fue procesada"), 409
    except UnknownTransactionError:
        return jsonify(error="Movimiento no encontrado"), 404
    except TransactionAlreadyHasReceiptError:
        return jsonify(error="Ese movimiento ya tiene un ticket"), 409
    finally:
        image = b""

    return jsonify(receipt_result_json(result, container.settings.frontend_url)), 201


@receipts_bp.get("/for-transaction/<transaction_id>")
def receipt_for_transaction(transaction_id: str):
    """The ticket attached to a movement, or ``null``.

    ``null`` rather than 404: "this movement has no receipt" is the ordinary
    state of almost every row, and a client rendering a detail panel should not
    have to treat it as an error.
    """
    receipt = get_container().manage_receipts.for_transaction(
        user_id=current_user_id(), transaction_id=UUID(transaction_id)
    )
    return jsonify(receipt=receipt_json(receipt) if receipt else None)


@receipts_bp.get("/<receipt_id>")
def get_receipt(receipt_id: str):
    try:
        receipt = get_container().manage_receipts.get(
            user_id=current_user_id(), receipt_id=UUID(receipt_id)
        )
    except ReceiptNotFoundError:
        return jsonify(error="Receipt not found"), 404
    return jsonify(receipt_json(receipt))


@receipts_bp.patch("/<receipt_id>")
def attach_receipt(receipt_id: str):
    """Point the ticket at a movement, or detach it.

    Body: ``{"transaction_id": "…" | null}``. An explicit ``null`` is a real
    instruction ("this is not that purchase"), which is why the key must be
    present: an absent one would be indistinguishable from it.
    """
    body = request.get_json(silent=True) or {}
    if "transaction_id" not in body:
        return jsonify(error="Provide 'transaction_id' (or null to detach)"), 400
    raw = body["transaction_id"]
    try:
        transaction_id = UUID(raw) if raw else None
    except (TypeError, ValueError):
        return jsonify(error="'transaction_id' must be a UUID or null"), 400

    try:
        receipt = get_container().manage_receipts.attach(
            user_id=current_user_id(),
            receipt_id=UUID(receipt_id),
            transaction_id=transaction_id,
        )
    except ReceiptNotFoundError:
        return jsonify(error="Receipt not found"), 404
    except UnknownTransactionError:
        return jsonify(error="Movimiento no encontrado"), 404
    except TransactionAlreadyHasReceiptError:
        # 409, not 400: the request is well-formed and the conflict is a fact
        # about the world the user can resolve (delete the other ticket).
        return jsonify(error="Ese movimiento ya tiene un ticket"), 409
    return jsonify(receipt_json(receipt))


@receipts_bp.delete("/<receipt_id>")
def delete_receipt(receipt_id: str):
    try:
        get_container().manage_receipts.delete(
            user_id=current_user_id(), receipt_id=UUID(receipt_id)
        )
    except ReceiptNotFoundError:
        return jsonify(error="Receipt not found"), 404
    return jsonify(receipt_id=receipt_id, deleted=True)
