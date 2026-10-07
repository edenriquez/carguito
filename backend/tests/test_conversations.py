"""Persisted chat threads: durable, plural, and owned.

The property under test is memory. A question asked about a set must survive a
reload, a second conversation must not bleed into the first, and the server —
not the client — is the record of what was said: the history the model sees is
replayed from storage, never echoed back by the browser.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from carguito.application.ports.outbound.chat import ChatMessage
from carguito.application.use_cases.workstation_chat import SYSTEM, TITLE_SYSTEM
from carguito.domain.entities.conversation import (
    MAX_TITLE_LENGTH,
    sanitize_inferred_title,
    title_from_question,
)

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


class RecordingChat:
    """A ChatPort that answers a fixed phrase and remembers what it was sent."""

    available = True
    model_label = "fake/model"

    def __init__(self, answer: str = "ok", title: str = "Nómina en Soriana") -> None:
        self.answer = answer
        self.title = title
        self.calls: list[list[ChatMessage]] = []
        self.systems: list[str] = []

    def stream(self, *, system, messages, options=None):
        self.calls.append(list(messages))
        self.systems.append(system)
        if system == TITLE_SYSTEM:
            yield self.title
            return
        yield self.answer


def _qa_calls(chat: RecordingChat) -> list[list[ChatMessage]]:
    """Answer streams only — the title call is a different conversation."""
    return [msgs for msgs, sys in zip(chat.calls, chat.systems) if sys != TITLE_SYSTEM]


@pytest.fixture
def chat(app):
    """Swap the container's chat for a fake before anything caches on it."""
    fake = RecordingChat()
    container = app.extensions["container"]
    container.__dict__["chat"] = fake  # pre-empt the cached_property
    container.__dict__.pop("answer_workstation_question", None)
    return fake


def _workstation(client) -> dict:
    return client.post(
        "/api/workstations",
        json={"name": "Retiros", "rule": {"description_contains": "retiro"}},
    ).get_json()


def _ask(client, workstation_id: str, question: str, conversation_id: str | None = None):
    resp = client.post(
        f"/api/workstations/{workstation_id}/chat",
        json={"question": question, "conversation_id": conversation_id},
    )
    assert resp.status_code == 200
    frames = [
        json.loads(line[5:])
        for line in resp.get_data(as_text=True).split("\n\n")
        if line.strip().startswith("data:")
    ]
    return frames


def _conversation_frame(frames) -> dict | None:
    for frame in frames:
        if "conversation" in frame:
            return frame["conversation"]
    return None


# --- the thread is durable --------------------------------------------------
def test_first_question_opens_a_thread_and_stores_both_turns(client, chat):
    ws = _workstation(client)
    frames = _ask(client, ws["id"], "¿Por qué mayo fue alto?")

    conversation = _conversation_frame(frames)
    assert conversation is not None, "a fresh ask must announce its new thread"
    # The opening frame still carries the question: the inferred name arrives
    # after the answer, once there is an exchange to name.
    assert conversation["title"] == "¿Por qué mayo fue alto?"
    titles = [f["title"] for f in frames if "title" in f and "conversation" not in f]
    assert titles == ["Nómina en Soriana"]

    listed = client.get(f"/api/workstations/{ws['id']}/conversations").get_json()
    assert [c["id"] for c in listed["items"]] == [conversation["id"]]
    assert listed["items"][0]["title"] == "Nómina en Soriana"

    thread = client.get(
        f"/api/workstations/conversations/{conversation['id']}"
    ).get_json()
    assert [(m["role"], m["content"]) for m in thread["messages"]] == [
        ("user", "¿Por qué mayo fue alto?"),
        ("assistant", "ok"),
    ]


def test_second_question_replays_stored_history_to_the_model(client, chat):
    ws = _workstation(client)
    conversation = _conversation_frame(_ask(client, ws["id"], "¿Cuánto gasto?"))

    _ask(client, ws["id"], "¿Y al año?", conversation_id=conversation["id"])

    qa = _qa_calls(chat)
    # Second *answer* call: the stored exchange precedes the new question — the
    # client sent no history at all. The title inference in between is not this.
    roles = [m.role for m in qa[1]]
    assert roles == ["user", "assistant", "user"]
    # Stored history is the raw exchange; the brief rides only on the new turn.
    assert qa[1][0].content == "¿Cuánto gasto?"
    assert qa[1][1].content == "ok"
    assert qa[1][2].content.endswith("Pregunta: ¿Y al año?")

    thread = client.get(
        f"/api/workstations/conversations/{conversation['id']}"
    ).get_json()
    assert [m["role"] for m in thread["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_a_second_conversation_does_not_bleed_into_the_first(client, chat):
    ws = _workstation(client)
    first = _conversation_frame(_ask(client, ws["id"], "¿Por qué mayo fue alto?"))
    second = _conversation_frame(_ask(client, ws["id"], "¿Cuánto retirar los lunes?"))

    assert first["id"] != second["id"]
    # The second thread starts clean: brief + its own question, no history.
    qa = _qa_calls(chat)
    assert [m.role for m in qa[1]] == ["user"]

    listed = client.get(f"/api/workstations/{ws['id']}/conversations").get_json()
    assert listed["total"] == 2
    # Most recently touched first.
    assert [c["id"] for c in listed["items"]][0] == second["id"]


# --- scoping ------------------------------------------------------------------
def test_a_thread_cannot_continue_under_another_workstation(client, chat):
    ws_a = _workstation(client)
    ws_b = client.post(
        "/api/workstations",
        json={"name": "Recargas", "rule": {"description_contains": "recarga"}},
    ).get_json()
    conversation = _conversation_frame(_ask(client, ws_a["id"], "¿Cuánto gasto?"))

    resp = client.post(
        f"/api/workstations/{ws_b['id']}/chat",
        json={"question": "¿y aquí?", "conversation_id": conversation["id"]},
    )
    assert resp.status_code == 400


def test_unknown_conversation_is_a_404(client, chat):
    ws = _workstation(client)
    resp = client.post(
        f"/api/workstations/{ws['id']}/chat",
        json={"question": "hola", "conversation_id": str(uuid4())},
    )
    assert resp.status_code == 404
    assert client.get(f"/api/workstations/conversations/{uuid4()}").status_code == 404


# --- deletion -----------------------------------------------------------------
def test_deleting_a_conversation_removes_its_messages(client, chat):
    ws = _workstation(client)
    conversation = _conversation_frame(_ask(client, ws["id"], "¿Cuánto gasto?"))

    assert (
        client.delete(
            f"/api/workstations/conversations/{conversation['id']}"
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/workstations/conversations/{conversation['id']}").status_code
        == 404
    )


def test_a_deleted_lens_takes_its_conversations_with_it(client, chat):
    ws = _workstation(client)
    conversation = _conversation_frame(_ask(client, ws["id"], "¿Cuánto gasto?"))

    client.delete(f"/api/workstations/{ws['id']}")

    assert (
        client.get(f"/api/workstations/conversations/{conversation['id']}").status_code
        == 404
    )


# --- presentation contracts ----------------------------------------------------
def test_titles_cut_at_a_word_boundary():
    long = "palabra " * 30
    title = title_from_question(long)
    assert len(title) <= MAX_TITLE_LENGTH + 1  # the ellipsis
    assert title.endswith("…")
    assert " palabr…" not in title  # no mid-word cut


def test_inferred_title_is_a_few_words_not_a_caption():
    assert sanitize_inferred_title('«Nómina en Soriana.»') == "Nómina en Soriana"
    assert sanitize_inferred_title("uno dos tres cuatro cinco seis siete") == (
        "uno dos tres cuatro cinco"
    )
    assert sanitize_inferred_title("   ") == ""


def test_system_prompt_forbids_latex_and_allows_light_markdown():
    """The screen renders Markdown and nothing else; the prompt must say so."""
    assert "LaTeX" in SYSTEM
    assert "negritas" in SYSTEM
