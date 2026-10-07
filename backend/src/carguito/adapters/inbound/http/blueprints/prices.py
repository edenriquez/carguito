from __future__ import annotations

import json
import logging
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from .....application.ports.outbound.chat import ChatMessage, ChatUnavailable
from ..auth import current_user_id, get_container
from ..serialization import product_prices_json
from ._helpers import query_int

logger = logging.getLogger(__name__)

prices_bp = Blueprint("prices", __name__, url_prefix="/api/prices")

#: How many turns of the client's own transcript are allowed back in. The
#: thread is not stored server-side (see `ask` below), so this is the only
#: bound on how large a "conversation" can make one request.
MAX_HISTORY = 12


@prices_bp.get("")
def list_prices():
    """The price book: every product the user's tickets have priced.

    Summaries only — ``points`` is omitted here and served by the detail
    endpoint. A pantry of 300 products would otherwise ship every purchase of
    every one of them to draw 300 rows.
    """
    book = get_container().compare_prices.book(
        user_id=current_user_id(), query=request.args.get("q") or None
    )
    limit = query_int("limit", 200)
    offset = query_int("offset", 0)
    window = book[offset : offset + limit]
    return jsonify(
        items=[product_prices_json(p, include_points=False) for p in window],
        total=len(book),
        limit=limit,
        offset=offset,
    )


@prices_bp.get("/product")
def get_product():
    """One product with every purchase behind it.

    The key travels as a query parameter rather than a path segment because it
    is normalised prose ("leche lala entera"), spaces and all.
    """
    key = (request.args.get("key") or "").strip()
    if not key:
        return jsonify(error="Provide 'key'"), 400
    product = get_container().compare_prices.product(
        user_id=current_user_id(), product_key=key
    )
    if product is None:
        return jsonify(error="Producto no encontrado en tus tickets"), 404
    return jsonify(product_prices_json(product))


@prices_bp.get("/terms")
def list_terms():
    """Which of the user's products already know their word in the world.

    A map rather than a field on each receipt line: the association belongs to
    the *product*, so one fetch serves every ticket that ever printed it, and
    the client joins on `product_key` it already has.
    """
    terms = get_container().resolve_product_terms.all_for_user(user_id=current_user_id())
    return jsonify(
        items=[
            {"product_key": t.product_key, "term": t.term, "source": t.source}
            for t in terms
        ],
        total=len(terms),
    )


@prices_bp.put("/terms")
def set_term():
    """Associate a product with the word a price survey files it under.

    Always stored as ``user``: this endpoint exists because a person is
    correcting something, and from here on no automatic proposal may overwrite
    it.
    """
    body = request.get_json(silent=True) or {}
    product_key = (body.get("product_key") or "").strip()
    if not product_key:
        return jsonify(error="product_key is required"), 400

    term = get_container().resolve_product_terms.set(
        user_id=current_user_id(),
        product_key=product_key,
        term=body.get("term") or "",
    )
    return jsonify(product_key=term.product_key, term=term.term, source=term.source)


@prices_bp.get("/chat/status")
def chat_status():
    """Whether a model is configured, and which one.

    The panel reads this before it renders: no key is a normal state of a fresh
    clone, and it must show as a disabled band with its reason rather than as a
    failure. The model's name is disclosed because the user is entitled to know
    which third party their grocery list is about to be described to.
    """
    answerer = get_container().answer_price_question
    return jsonify(
        available=answerer.available,
        model=answerer.model_label,
        # The second third party, when there is one. Disclosed for the same
        # reason the model is: the user is entitled to know who receives what.
        reference=answerer.reference_label,
    )


@prices_bp.post("/chat")
def ask():
    """Answer a question about the user's own prices, streamed.

    Server-sent events for the same reason as the workstation chat: a grounded
    answer takes seconds and a blank panel for that long reads as a hang.

    Unlike that one, **no thread is stored**. A price question is a lookup
    ("¿dónde estaba más barata la leche?"), not an investigation with a history
    worth keeping, so the transcript lives in the panel and travels back in
    ``history``. If that stops being true, ``workstation_conversations`` is the
    shape to copy — not a second, subtly different one.
    """
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify(error="question is required"), 400

    # Optional: the question was asked from inside one ticket, so the brief is
    # that basket instead of the whole book. Ownership is not checked here —
    # the repository read is user-scoped, and an id that is not this user's
    # comes back as "no encontrado" rather than as someone else's basket.
    #
    # Validated *before* the availability check below, alongside the question:
    # whether the body is well-formed is a property of the request, and must
    # not depend on whether this deployment happens to have a model wired.
    # The lines the user attached to the question. Explicit is the design: a
    # reference lookup happens for these and for nothing guessed from prose.
    product_keys = body.get("product_keys") or []
    if not isinstance(product_keys, list) or not all(isinstance(k, str) for k in product_keys):
        return jsonify(error="product_keys must be a list of strings"), 400

    raw_receipt = body.get("receipt_id")
    try:
        receipt_id = UUID(raw_receipt) if raw_receipt else None
    except (TypeError, ValueError):
        return jsonify(error="receipt_id must be a uuid"), 400

    answerer = get_container().answer_price_question
    if not answerer.available:
        # 503 rather than 500: nothing is broken, the integration is simply not
        # set up, and the client renders that as a disabled band with a reason.
        return jsonify(error="No hay un modelo configurado.", available=False), 503

    user_id = current_user_id()
    history = _history(body.get("history"))

    def events():
        # The external lookup happens *inside* this stream and before the
        # model is called, but the client is told about it first: the frame
        # below is flushed, then the two seconds are spent, then the answer
        # arrives. That is the whole reason this endpoint streams — the panel
        # shows work in progress instead of a panel that appears to hang, and
        # no job table, job id or polling endpoint has to exist for it.
        quotes = []
        try:
            terms = answerer.reference_terms(user_id=user_id, product_keys=product_keys)
            if terms:
                # Rendering store pages and reading them takes ~30 s on the free
                # tiers; the panel has to say so or it reads as a hang.
                yield _sse({"status": f"Consultando Profeco y leyendo páginas de tiendas: {', '.join(terms)}… (puede tardar medio minuto)"})
                quotes = answerer.reference_quotes(terms, user_id=user_id, product_keys=product_keys)
        except Exception:  # pragma: no cover - the garnish must never break the dish
            logger.exception("price reference lookup failed")
            quotes = []

        try:
            for piece in answerer.stream(
                user_id=user_id,
                question=question,
                history=history,
                receipt_id=receipt_id,
                quotes=quotes,
                product_keys=product_keys,
            ):
                yield _sse({"delta": piece})
        except ChatUnavailable as exc:
            # The stream has already started, so the status code is spent. The
            # failure travels as a frame the client can render in place instead.
            yield _sse({"error": str(exc)})
        yield _sse({"done": True})

    return Response(
        events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx buffers text/event-stream by default and would hold the
            # whole answer until the end, undoing the streaming entirely.
            "X-Accel-Buffering": "no",
        },
    )


def _history(raw) -> list[ChatMessage]:
    """The client's transcript, trusted only as far as its shape.

    Roles other than user/assistant are dropped rather than passed through: the
    system prompt is this server's, and a "system" turn arriving from a browser
    is exactly the injection this narrow mapping exists to refuse.
    """
    if not isinstance(raw, list):
        return []
    turns = []
    for entry in raw[-MAX_HISTORY:]:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            turns.append(ChatMessage(role=role, content=content))
    return turns


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
