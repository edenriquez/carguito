"""The chat seam. **No test here touches the network.**

Two things are worth proving and neither of them is "the model gives good
answers", which no test can assert:

1. **Unconfigured is a normal state.** A fresh clone has no key, and the
   Workspace view must still work with only the chat band disabled. If this
   suite ever needs a key to pass, the product needs one to run.
2. **The brief carries the same numbers the panel shows.** The chat and the
   screen read one `cohort_profile`; a brief that quietly omits or re-derives a
   figure is how they start disagreeing, and the user would believe the
   sentence over the tile.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from carguito.adapters.outbound.chat import NullChat
from carguito.adapters.outbound.metrics import CohortProfileResolver
from carguito.application.dtos.metrics import Period
from carguito.application.ports.outbound.chat import ChatMessage, ChatUnavailable
from carguito.application.use_cases import workstation_chat
from carguito.application.use_cases.workstation_chat import (
    SYSTEM,
    AnswerWorkstationQuestion,
)
from carguito.domain.entities import Transaction, Workstation, WorkstationRule
from carguito.domain.value_objects.enums import TxType

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


class RecordingChat:
    """A ChatPort that answers nothing and remembers everything."""

    available = True
    model_label = "fake/model"

    def __init__(self) -> None:
        self.system: str | None = None
        self.messages: list[ChatMessage] = []

    def stream(self, *, system, messages, options=None):
        self.system = system
        self.messages = list(messages)
        self.options = options
        yield "ok"


@pytest.fixture
def seeded(app):
    """Twelve weekly top-ups and one noise row, over three months."""
    container = app.extensions["container"]
    start = date(2024, 1, 1)
    txs = [
        Transaction(
            user_id=DEV_USER,
            tx_date=start + timedelta(days=7 * i),
            amount=Decimal("15"),
            raw_description="TELCEL RECARGA",
            tx_type=TxType.EXPENSE,
        )
        for i in range(12)
    ]
    txs.append(
        Transaction(
            user_id=DEV_USER,
            tx_date=start + timedelta(days=3),
            amount=Decimal("450"),
            raw_description="UBER TRIP",
            tx_type=TxType.EXPENSE,
        )
    )
    container.transactions.add_many(txs)
    container.cube.upsert_transactions(txs)
    return txs


@pytest.fixture
def workstation():
    return Workstation(
        user_id=DEV_USER,
        name="Recargas",
        rule=WorkstationRule(description_contains="recarga"),
    )


def _answerer(app, chat):
    container = app.extensions["container"]
    return AnswerWorkstationQuestion(
        chat=chat,
        engine=container.metric_engine,
        profile_resolver=CohortProfileResolver(container.metric_engine),
        transactions=container.transactions,
    )


# --- unconfigured is a normal state ---------------------------------------
def test_null_chat_reports_unavailable_rather_than_raising_on_construction():
    chat = NullChat()
    assert chat.available is False
    assert chat.model_label == ""


def test_fallback_chat_uses_the_second_model_when_the_first_refuses():
    from carguito.adapters.outbound.chat import FallbackChat

    class Dead:
        available = True
        model_label = "primary"

        def stream(self, *, system, messages, options=None):
            raise ChatUnavailable("429")
            yield  # pragma: no cover — makes this a generator

    class Alive:
        available = True
        model_label = "fallback"

        def stream(self, *, system, messages, options=None):
            yield "hola"

    chat = FallbackChat(Dead(), Alive())
    assert chat.model_label == "primary · fallback"
    assert "".join(chat.stream(system="s", messages=[])) == "hola"


def test_null_chat_explains_itself_when_actually_asked():
    with pytest.raises(ChatUnavailable) as exc:
        list(NullChat().stream(system="s", messages=[]))
    # The message names the three variables, because "unavailable" alone sends
    # the reader to the source.
    assert "LLM_BASE_URL" in str(exc.value)


def test_container_injects_the_null_chat_when_nothing_is_configured(app):
    container = app.extensions["container"]
    assert container.chat.available is False
    assert container.answer_workstation_question.available is False


def test_chat_status_endpoint_says_unavailable(client):
    body = client.get("/api/workstations/chat/status").get_json()
    assert body == {"available": False, "model": ""}


def test_asking_without_a_model_is_a_503_not_a_500(client):
    created = client.post(
        "/api/workstations",
        json={"name": "Recargas", "rule": {"description_contains": "recarga"}},
    ).get_json()

    resp = client.post(f"/api/workstations/{created['id']}/chat", json={"question": "¿y?"})
    # Nothing is broken; the integration is simply not set up.
    assert resp.status_code == 503
    assert resp.get_json()["available"] is False


def test_the_rest_of_the_workspace_works_without_a_model(client, seeded):
    """The load-bearing one: chat is optional, the view is not."""
    created = client.post(
        "/api/workstations",
        json={"name": "Recargas", "rule": {"description_contains": "recarga"}},
    ).get_json()
    assert created["filters"]["description_contains"] == "recarga"

    entry = client.post(
        "/api/metrics/query",
        json={
            "period": {"start": "2024-01-01", "end": "2024-12-31"},
            "queries": [
                {"key": "p", "metric": "cohort_profile", "filters": created["filters"]}
            ],
        },
    ).get_json()["results"]["p"]
    assert entry["rows"][0]["count"] == 12


# --- the brief ------------------------------------------------------------
def test_brief_carries_the_profile_figures(app, seeded, workstation):
    answerer = _answerer(app, RecordingChat())
    brief = answerer.build_brief(
        user_id=DEV_USER,
        workstation=workstation,
        period=Period(start="2024-01-01", end="2024-12-31"),
    )

    assert "Recargas" in brief
    assert "«recarga»" in brief
    assert "movimientos: 12" in brief
    assert "180.00" in brief  # 12 * 15, the total the tile also shows


def test_brief_excludes_what_the_rule_excludes(app, seeded, workstation):
    brief = _answerer(app, RecordingChat()).build_brief(
        user_id=DEV_USER,
        workstation=workstation,
        period=Period(start="2024-01-01", end="2024-12-31"),
    )
    # The Uber is in the ledger and out of the set. If it leaked into the rows,
    # the model would answer questions about a set the user never defined.
    assert "UBER" not in brief
    assert "450" not in brief


def test_brief_says_a_missing_figure_is_missing(app, workstation):
    """An absent field invites an estimate; an explicit absence forbids one."""
    container = app.extensions["container"]
    txs = [
        Transaction(
            user_id=DEV_USER,
            tx_date=date(2024, 5, d),
            amount=Decimal("15"),
            raw_description="RECARGA",
            tx_type=TxType.EXPENSE,
        )
        for d in (1, 3, 5)
    ]
    container.transactions.add_many(txs)
    container.cube.upsert_transactions(txs)

    brief = _answerer(app, RecordingChat()).build_brief(
        user_id=DEV_USER,
        workstation=workstation,
        period=Period(start="2024-01-01", end="2024-12-31"),
    )
    assert "movimientos por semana: no disponible (falta historia)" in brief


def test_brief_precomputes_the_weekday_histogram(app, seeded, workstation):
    # Handing the model 300 dates and expecting it to bucket them is asking it
    # to do the arithmetic it is worst at, on the question a list of dates most
    # invites.
    brief = _answerer(app, RecordingChat()).build_brief(
        user_id=DEV_USER,
        workstation=workstation,
        period=Period(start="2024-01-01", end="2024-12-31"),
    )
    assert "POR DIA DE LA SEMANA" in brief
    # Every top-up is a Monday: 7-day spacing from 2024-01-01.
    assert "lunes: 12" in brief


def test_brief_rides_on_the_user_turn_so_the_system_prompt_stays_identical(
    app, seeded, workstation
):
    chat = RecordingChat()
    answerer = _answerer(app, chat)
    list(
        answerer.stream(
            user_id=DEV_USER,
            workstation=workstation,
            period=Period(start="2024-01-01", end="2024-12-31"),
            question="¿me conviene un plan mensual?",
        )
    )

    # Byte-identical between questions, which is what lets a gateway cache it.
    assert chat.system == SYSTEM
    assert "RESUMEN:" in chat.messages[-1].content
    assert chat.messages[-1].content.endswith("Pregunta: ¿me conviene un plan mensual?")


def test_system_prompt_carries_the_products_posture():
    """The one component with no posture of its own gets told, explicitly."""
    assert "NUNCA inventes una cifra" in SYSTEM
    assert "no puedo saberlo" in SYSTEM


def test_history_is_passed_through_before_the_new_question(app, seeded, workstation):
    chat = RecordingChat()
    list(
        _answerer(app, chat).stream(
            user_id=DEV_USER,
            workstation=workstation,
            period=Period(),
            question="¿y al año?",
            history=[
                ChatMessage(role="user", content="¿cuánto gasto?"),
                ChatMessage(role="assistant", content="180 pesos."),
            ],
        )
    )
    assert [m.role for m in chat.messages] == ["user", "assistant", "user"]


# --- the tools see every row; the brief prints up to its cap -----------------
def test_the_model_is_handed_tools_over_the_same_rows(app, seeded, workstation):
    chat = RecordingChat()
    list(
        _answerer(app, chat).stream(
            user_id=DEV_USER, workstation=workstation, period=Period(), question="¿cuánto en enero?"
        )
    )
    assert [t.name for t in chat.options.tools] == [
        "buscar_movimientos",
        "agrupar_movimientos",
        "resumen_de_periodo",
    ]
    # The handler computes over the lens: twelve top-ups of 15, no Uber.
    summary = json.loads(chat.options.tool_handler("resumen_de_periodo", {}))
    assert (summary["movimientos"], summary["total"]) == (12, "180.00")
    january = json.loads(
        chat.options.tool_handler("agrupar_movimientos", {"por": "mes", "hasta": "2024-01-31"})
    )
    assert january["grupos"] == [
        {"grupo": "2024-01", "movimientos": 5, "total": "75.00", "promedio": "15.00"}
    ]


def test_brief_truncates_at_the_cap_and_points_at_the_tools(
    app, seeded, workstation, monkeypatch
):
    monkeypatch.setattr(workstation_chat, "MAX_ROWS", 5)
    brief = _answerer(app, RecordingChat()).build_brief(
        user_id=DEV_USER, workstation=workstation, period=Period()
    )
    header = next(line for line in brief.splitlines() if line.startswith("MOVIMIENTOS"))
    assert header.startswith("MOVIMIENTOS (12 — se muestran 5; usa buscar_movimientos")
    assert sum(1 for line in brief.splitlines() if "TELCEL RECARGA" in line) == 5


def test_brief_under_the_cap_is_not_marked_truncated(app, seeded, workstation):
    brief = _answerer(app, RecordingChat()).build_brief(
        user_id=DEV_USER, workstation=workstation, period=Period()
    )
    assert "MOVIMIENTOS (12):" in brief
