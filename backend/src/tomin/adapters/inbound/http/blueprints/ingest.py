from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from flask import Blueprint, jsonify, request

from .....application.dtos.extraction import ExtractedDocument
from .....application.use_cases.receipts import (
    DuplicateReceiptError,
    TransactionAlreadyHasReceiptError,
    UnknownTransactionError,
)
from .....domain.value_objects.enums import StatementSource
from ....outbound.crypto import ALGORITHM, SealedEnvelopeError
from ..auth import current_user_id, get_container
from ..serialization import receipt_json, statement_json, transaction_json

logger = logging.getLogger(__name__)

ingest_bp = Blueprint("ingest", __name__, url_prefix="/api/ingest")

#: Protocol version. Both the envelope and the payload carry it so a future
#: change can be rejected loudly instead of misread quietly.
PROTOCOL_VERSION = 1

_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


class InvalidPayloadError(Exception):
    """The envelope opened but what was inside is not a v1 ingest payload."""


@ingest_bp.get("/key")
def ingest_key():
    """Publish the public half of the server's ingest keypair.

    Unauthenticated on purpose: it is a *public* key, and the phone needs it
    before it has anything to send. The client pins it on first use (TOFU) and
    refuses to send if it ever changes unannounced — which is exactly the MITM
    the sealed envelope exists to make visible (docs/custody-plan.md G3).
    """
    key = get_container().ingest_keyring.current
    return jsonify(
        key_id=key.key_id,
        algorithm=ALGORITHM,
        public_key=key.public_key_b64,
    )


@ingest_bp.post("/extracted")
def ingest_extracted():
    """Accept text a device extracted from a file that never left it.

    The body is opaque: a ``crypto_box`` sealed to this server's key with an
    ephemeral sender key the phone discards afterwards. It is opened **in
    memory only** — no transient file, no plaintext in any log line — and the
    resulting document enters the same pipeline a web upload would, one step
    later (extraction already happened, on the phone).
    """
    user_id = current_user_id()
    container = get_container()

    envelope = request.get_json(silent=True)
    error = _envelope_error(envelope)
    if error:
        return jsonify(error=error), 400

    try:
        plaintext = container.ingest_keyring.open_envelope(
            key_id=str(envelope["key_id"]),
            epk=envelope["epk"],
            nonce=envelope["nonce"],
            box=envelope["box"],
        )
        document, content_sha256, extractor = _read_payload(plaintext)
    except SealedEnvelopeError as exc:
        # 400, not 401: a box that will not open is a malformed request, and
        # there is no credential here to challenge.
        return jsonify(error="Could not open sealed payload", detail=str(exc)), 400
    except InvalidPayloadError as exc:
        return jsonify(error="Invalid ingest payload", detail=str(exc)), 400
    finally:
        # The plaintext's only reason to exist was the line above.
        plaintext = None

    # Metadata only: how it was read and how much of it there was. The lines
    # themselves are the user's bank statement and are never logged.
    logger.info(
        "ingest: device payload kind=%s extractor=%s size=%d",
        document.kind,
        extractor,
        len(document.lines) if document.kind == "text" else len(document.xml or ""),
    )

    # DuplicateStatementError rides the existing handler to a 409: re-sending
    # the same file from the phone is the same event as re-uploading it.
    result = container.process_extracted.execute(
        user_id=user_id,
        document=document,
        file_hash=content_sha256,
        source=StatementSource.DEVICE,
    )
    statement = container.manage_statements.get(
        user_id=user_id, statement_id=result.statement_id
    )
    return (
        jsonify(
            statement_id=str(result.statement_id),
            template=result.template,
            transactions_created=result.transactions_created,
            statement=statement_json(statement),
            # The handoff: the phone shows a button, the browser shows the
            # graphs. The backend is the only party that knows where the web
            # app lives, so it is the one that builds the link.
            dashboard_url=_dashboard_url(
                container.settings.frontend_url, result.statement_id
            ),
        ),
        201,
    )


@ingest_bp.post("/receipt")
def ingest_receipt():
    """Accept the text a device read off a photo of a grocery ticket.

    Same envelope, same custody, one step later in a different pipeline: the
    photo stays on the device that took or holds it -- the phone's recognizer
    or a Tesseract worker in the browser tab (docs/custody-plan.md G1/G2) --
    and only the OCR lines travel, sealed. What comes back is the structured basket plus, when
    the ticket could not attach itself to a movement, the movements it might
    belong to — the phone asks, and a wrong attachment is never guessed into
    place.
    """
    user_id = current_user_id()
    container = get_container()

    envelope = request.get_json(silent=True)
    error = _envelope_error(envelope)
    if error:
        return jsonify(error=error), 400

    try:
        plaintext = container.ingest_keyring.open_envelope(
            key_id=str(envelope["key_id"]),
            epk=envelope["epk"],
            nonce=envelope["nonce"],
            box=envelope["box"],
        )
        payload = _read_receipt_payload(plaintext)
    except SealedEnvelopeError as exc:
        return jsonify(error="Could not open sealed payload", detail=str(exc)), 400
    except InvalidPayloadError as exc:
        return jsonify(error="Invalid receipt payload", detail=str(exc)), 400
    finally:
        plaintext = None

    # Metadata only: how it was read and how much of it there was. The lines
    # are the user's groceries and are never logged.
    logger.info(
        "ingest: receipt payload extractor=%s lines=%d",
        payload["extractor"],
        len(payload["lines"]),
    )

    try:
        result = container.ingest_receipt.execute(
            user_id=user_id,
            lines=payload["lines"],
            content_sha256=payload["content_sha256"],
            extractor=payload["extractor"],
            captured_at=payload["captured_at"],
            transaction_id=payload["transaction_id"],
        )
    except DuplicateReceiptError:
        # Same meaning as re-sending a statement: this photo is already read.
        return jsonify(error="Esta foto ya fue procesada"), 409
    except UnknownTransactionError:
        # The phone named a movement that is not there (or not theirs).
        return jsonify(error="Movimiento no encontrado"), 404
    except TransactionAlreadyHasReceiptError:
        return jsonify(error="Ese movimiento ya tiene un ticket"), 409

    receipt = result.receipt
    return (
        jsonify(
            receipt_id=str(receipt.id),
            receipt=receipt_json(receipt),
            attached=receipt.transaction_id is not None,
            # Present only when the receipt could not attach itself. Each entry
            # carries the movement *and* the reason it scored, because "same
            # amount, same day" is what makes the choice answerable.
            suggestions=[
                {
                    "transaction": transaction_json(s.transaction),
                    "score": s.candidate.score,
                    "reason": s.candidate.reason,
                }
                for s in result.suggestions
            ],
            prices_url=_prices_url(container.settings.frontend_url),
        ),
        201,
    )


def _envelope_error(envelope) -> str | None:
    """The shared envelope checks. Both ingest endpoints speak protocol v1."""
    if not isinstance(envelope, dict):
        return "Body must be a JSON object"
    if envelope.get("v") != PROTOCOL_VERSION:
        return f"Unsupported envelope version; expected {PROTOCOL_VERSION}"
    missing = [f for f in ("key_id", "epk", "nonce", "box") if not envelope.get(f)]
    if missing:
        return f"Envelope is missing: {', '.join(missing)}"
    return None


def _read_receipt_payload(plaintext: bytes) -> dict:
    """Validate the decrypted receipt payload.

    Strict about the two things the pipeline cannot do without — the lines and
    the digest of the photo they came from — and lenient about everything else.
    Rejecting a correctly-read ticket over an unparseable capture timestamp
    would trade real data for bookkeeping.
    """
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InvalidPayloadError("Payload is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidPayloadError("Payload must be a JSON object")
    if payload.get("v") != PROTOCOL_VERSION:
        raise InvalidPayloadError(f"Unsupported payload version; expected {PROTOCOL_VERSION}")
    if payload.get("kind") != "receipt":
        raise InvalidPayloadError("'kind' must be 'receipt'")

    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        raise InvalidPayloadError("A receipt payload requires a non-empty 'lines' array")
    if not all(isinstance(line, str) for line in lines):
        raise InvalidPayloadError("'lines' must contain only strings")

    content_sha256 = payload.get("content_sha256")
    if not isinstance(content_sha256, str) or not _SHA256_RE.fullmatch(content_sha256.strip()):
        raise InvalidPayloadError("'content_sha256' must be a 64-character hex digest")

    extractor = payload.get("extractor") or "unknown"
    if not isinstance(extractor, str):
        raise InvalidPayloadError("'extractor' must be a string")

    raw_transaction = payload.get("transaction_id")
    try:
        transaction_id = UUID(raw_transaction) if raw_transaction else None
    except (TypeError, ValueError) as exc:
        raise InvalidPayloadError("'transaction_id' must be a UUID or null") from exc

    return {
        "lines": list(lines),
        "content_sha256": content_sha256.strip().lower(),
        "extractor": extractor,
        "captured_at": _timestamp(payload.get("captured_at")),
        "transaction_id": transaction_id,
    }


def _timestamp(value) -> datetime | None:
    """Best-effort ISO-8601, naive UTC. Unreadable means absent, never an error."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _prices_url(frontend_url: str) -> str:
    return f"{frontend_url.rstrip('/')}/precios"

def _read_payload(plaintext: bytes) -> tuple[ExtractedDocument, str, str]:
    """Validate the decrypted payload and turn it into an ``ExtractedDocument``.

    Strict about the three fields the pipeline cannot do without — ``kind``,
    the content for that kind, and ``content_sha256`` — and lenient about the
    provenance metadata (``extractor``, ``extracted_at``), which is there for
    quality telemetry. Rejecting a correctly-read statement over a missing
    timestamp would trade real data for bookkeeping.
    """
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InvalidPayloadError("Payload is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidPayloadError("Payload must be a JSON object")
    if payload.get("v") != PROTOCOL_VERSION:
        raise InvalidPayloadError(f"Unsupported payload version; expected {PROTOCOL_VERSION}")

    kind = payload.get("kind")
    if kind not in ("text", "xml"):
        raise InvalidPayloadError("'kind' must be 'text' or 'xml'")

    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        raise InvalidPayloadError("'filename' must be a non-empty string")

    content_sha256 = payload.get("content_sha256")
    if not isinstance(content_sha256, str) or not _SHA256_RE.fullmatch(content_sha256.strip()):
        raise InvalidPayloadError("'content_sha256' must be a 64-character hex digest")
    # Lowercased so a phone that spells the digest in uppercase still collides
    # with the same file uploaded through the web path, which hashes via
    # `hexdigest()`.
    content_sha256 = content_sha256.strip().lower()

    extractor = payload.get("extractor") or "unknown"
    if not isinstance(extractor, str):
        raise InvalidPayloadError("'extractor' must be a string")

    if kind == "text":
        lines = payload.get("lines")
        if not isinstance(lines, list) or not lines:
            raise InvalidPayloadError("kind='text' requires a non-empty 'lines' array")
        if not all(isinstance(line, str) for line in lines):
            raise InvalidPayloadError("'lines' must contain only strings")
        # `text` is the joined form the classifier scores over; `lines` is what
        # the parsers walk. The PDF extractor builds both the same way, so a
        # device document is indistinguishable from a server-extracted one.
        document = ExtractedDocument(
            kind="text",
            filename=filename.strip(),
            text="\n".join(lines),
            lines=list(lines),
        )
    else:
        xml = payload.get("xml")
        if not isinstance(xml, str) or not xml.strip():
            raise InvalidPayloadError("kind='xml' requires a non-empty 'xml' string")
        document = ExtractedDocument(kind="xml", filename=filename.strip(), xml=xml)

    return document, content_sha256, extractor


def _dashboard_url(frontend_url: str, statement_id: UUID) -> str:
    return f"{frontend_url.rstrip('/')}/?statement={statement_id}"
