"""A user's saved lenses over the ledger.

Plain REST over a collection, unlike ``/api/dashboards/home``: there is exactly
one dashboard per user but a workstation is a thing you make several of, so the
id is in the path from the start.

The response carries ``filters`` -- the rule already translated into a metric
query -- alongside the rule itself. Without it every client would reimplement
``WorkstationRule.to_filters`` and one of them would eventually disagree about
what "between 10 and 300" means, which is the class of bug the whole closed
vocabulary exists to prevent.
"""

from __future__ import annotations

import json
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from .....application.dtos.metrics import Period
from .....application.ports.outbound.chat import ChatUnavailable
from .....application.use_cases.conversations import ConversationNotFound
from .....application.use_cases.workstations import WorkstationNotFound
from .....domain.entities import WorkstationRule
from ..auth import current_user_id, get_container
from ..serialization import conversation_json, conversation_turn_json, workstation_json

workstations_bp = Blueprint("workstations", __name__, url_prefix="/api/workstations")

#: Mirrors the transaction and tag patches: only declared fields are writable,
#: and an unrecognised key is a 400 rather than a silent no-op.
_PATCHABLE = {"name", "rule", "excluded_tx_ids"}


@workstations_bp.get("")
def list_workstations():
    items = get_container().manage_workstations.list(user_id=current_user_id())
    return jsonify(items=[workstation_json(w) for w in items], total=len(items))


@workstations_bp.post("")
def create_workstation():
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return jsonify(error="name is required"), 400

    # An unknown rule key, an empty needle, min above max, or a filter the
    # catalog would reject all raise ValueError subclasses and land on the
    # app-wide 400 handler. Failing here is the design: a rule that saves and
    # then returns nothing forever is worse than a rule that refuses to save.
    workstation = get_container().manage_workstations.create(
        user_id=current_user_id(),
        name=body["name"],
        rule=_rule(body.get("rule")),
        excluded_tx_ids=_uuids(body.get("excluded_tx_ids")),
    )
    return jsonify(workstation_json(workstation)), 201


@workstations_bp.get("/<workstation_id>")
def get_workstation(workstation_id: str):
    try:
        workstation = get_container().manage_workstations.get(
            user_id=current_user_id(), workstation_id=UUID(workstation_id)
        )
    except WorkstationNotFound:
        return jsonify(error="Workstation not found"), 404
    return jsonify(workstation_json(workstation))


@workstations_bp.patch("/<workstation_id>")
def update_workstation(workstation_id: str):
    body = request.get_json(silent=True) or {}
    unknown = set(body) - _PATCHABLE
    if unknown:
        return jsonify(error=f"Unsupported fields: {sorted(unknown)}"), 400

    try:
        workstation = get_container().manage_workstations.update(
            user_id=current_user_id(),
            workstation_id=UUID(workstation_id),
            name=body.get("name"),
            # A rule is replaced wholesale when given, never merged: a rule is
            # one thought, and half of a new one over half of an old one
            # describes a set nobody asked for.
            rule=_rule(body["rule"]) if "rule" in body else None,
            excluded_tx_ids=(
                _uuids(body["excluded_tx_ids"]) if "excluded_tx_ids" in body else None
            ),
        )
    except WorkstationNotFound:
        return jsonify(error="Workstation not found"), 404
    return jsonify(workstation_json(workstation))


@workstations_bp.delete("/<workstation_id>")
def delete_workstation(workstation_id: str):
    try:
        get_container().manage_workstations.delete(
            user_id=current_user_id(), workstation_id=UUID(workstation_id)
        )
    except WorkstationNotFound:
        return jsonify(error="Workstation not found"), 404
    # The movements survive; only the lens is gone.
    return jsonify(workstation_id=workstation_id, deleted=True)


@workstations_bp.get("/chat/status")
def chat_status():
    """Whether a model is configured, and which one.

    A GET of its own so the client can render the chat band disabled *with its
    reason* on first paint, rather than discovering the absence by asking a
    question and getting an error. `model` is named so the disclosure can say
    which third party the user's movements would be described to -- they are
    entitled to know before they type, not after.
    """
    chat = get_container().answer_workstation_question
    return jsonify(available=chat.available, model=chat.model_label)


@workstations_bp.get("/<workstation_id>/conversations")
def list_conversations(workstation_id: str):
    """This lens's chat threads, most recently touched first.

    Existence of the workstation is checked so an unknown lens is a 404 and
    not an empty list — the client tells those apart.
    """
    user_id = current_user_id()
    container = get_container()
    try:
        container.manage_workstations.get(
            user_id=user_id, workstation_id=UUID(workstation_id)
        )
    except WorkstationNotFound:
        return jsonify(error="Workstation not found"), 404
    items = container.manage_conversations.list(
        user_id=user_id, workstation_id=UUID(workstation_id)
    )
    return jsonify(items=[conversation_json(c) for c in items], total=len(items))


@workstations_bp.get("/conversations/<conversation_id>")
def get_conversation(conversation_id: str):
    """One thread with its full transcript, oldest message first."""
    user_id = current_user_id()
    manager = get_container().manage_conversations
    try:
        conversation = manager.get(user_id=user_id, conversation_id=UUID(conversation_id))
        turns = manager.turns(user_id=user_id, conversation_id=UUID(conversation_id))
    except ConversationNotFound:
        return jsonify(error="Conversation not found"), 404
    return jsonify(
        **conversation_json(conversation),
        messages=[conversation_turn_json(t) for t in turns],
    )


@workstations_bp.delete("/conversations/<conversation_id>")
def delete_conversation(conversation_id: str):
    try:
        get_container().manage_conversations.delete(
            user_id=current_user_id(), conversation_id=UUID(conversation_id)
        )
    except ConversationNotFound:
        return jsonify(error="Conversation not found"), 404
    return jsonify(conversation_id=conversation_id, deleted=True)


@workstations_bp.post("/<workstation_id>/chat")
def chat(workstation_id: str):
    """Answer a question about this lens, streamed, and remember the exchange.

    Server-sent events rather than one JSON body: a grounded answer over six
    months of movements takes seconds, and a blank panel for that long reads as
    a hang. Streaming also keeps the request under any proxy's idle timeout.

    The thread is durable. ``conversation_id`` continues an existing one; when
    absent, a new conversation is opened and announced in the first frame so
    the client can adopt its id. History comes from storage, never from the
    request — the stored thread is the one record of what was actually said.
    """
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify(error="question is required"), 400

    container = get_container()
    user_id = current_user_id()
    try:
        workstation = container.manage_workstations.get(
            user_id=user_id, workstation_id=UUID(workstation_id)
        )
    except WorkstationNotFound:
        return jsonify(error="Workstation not found"), 404

    answerer = container.answer_workstation_question
    if not answerer.available:
        # 503 rather than 500: nothing is broken, the integration is simply not
        # set up, and the client renders that as a disabled band with a reason.
        return jsonify(error="No hay un modelo configurado.", available=False), 503

    period = Period(start=body.get("start") or None, end=body.get("end") or None)

    manager = container.manage_conversations
    raw_conversation_id = body.get("conversation_id")
    created = None
    if raw_conversation_id:
        try:
            conversation = manager.get(
                user_id=user_id, conversation_id=UUID(raw_conversation_id)
            )
        except (ConversationNotFound, ValueError):
            return jsonify(error="Conversation not found"), 404
        if str(conversation.workstation_id) != str(workstation.id):
            # A thread about one set continued under another would ground the
            # model in numbers the transcript never saw.
            return jsonify(error="Conversation belongs to another workstation"), 400
    else:
        conversation = manager.start(
            user_id=user_id,
            workstation_id=workstation.id,
            first_question=question,
        )
        created = conversation

    history = manager.history(user_id=user_id, conversation_id=conversation.id)
    # The question is stored before the model speaks: a stream that dies
    # mid-answer still leaves the thread showing what was asked.
    manager.append(
        user_id=user_id,
        conversation_id=conversation.id,
        role="user",
        content=question,
    )

    def events():
        if created is not None:
            # First frame, so the client can adopt the id before any token.
            yield _sse({"conversation": conversation_json(created)})
        answer_pieces: list[str] = []
        try:
            for piece in answerer.stream(
                user_id=user_id,
                workstation=workstation,
                period=period,
                question=question,
                history=history,
            ):
                answer_pieces.append(piece)
                yield _sse({"delta": piece})
        except ChatUnavailable as exc:
            # The stream has already started, so the status code is spent. The
            # failure travels as a frame the client can render in place instead.
            yield _sse({"error": str(exc)})
        # Whatever arrived is what the user read; a partial answer on a dropped
        # stream is still part of the record. An empty one is not stored.
        manager.append(
            user_id=user_id,
            conversation_id=conversation.id,
            role="assistant",
            content="".join(answer_pieces),
        )
        if created is not None:
            inferred = answerer.infer_title(
                question=question, answer="".join(answer_pieces)
            )
            if inferred:
                renamed = manager.rename(
                    user_id=user_id,
                    conversation_id=conversation.id,
                    title=inferred,
                )
                yield _sse({"title": renamed.title, "conversation_id": str(renamed.id)})
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


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _rule(raw) -> WorkstationRule:
    """One filter, or `{"any_of": [...]}` for a group. Both parse in the domain.

    Every ValueError it raises is a 400 through the app-wide handler, which is
    the point: a rule the engine would reject must fail here, while the user is
    still looking at the editor.
    """
    return WorkstationRule.from_json(raw)


def _uuids(raw) -> list[UUID]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("'excluded_tx_ids' must be a list of ids")
    return [UUID(value) for value in raw]
