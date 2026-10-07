"""The request options and the tool rounds. **No test here touches the network.**

What is worth proving: that the options a caller sets actually reach the wire,
that a tool round is assembled the way the protocol expects (assistant turn with
the calls, one ``tool`` message per call, same ids), that a model which keeps
calling is eventually made to answer, and that every figure the lens tools
return is the arithmetic over the rows and nothing else.
"""

from __future__ import annotations

import io
import json
import urllib.request

import pytest

from carguito.adapters.outbound.chat import OpenAiCompatibleChat
from carguito.adapters.outbound.references.web_listings import parse_listings
from carguito.application.ports.outbound.chat import (
    ChatMessage,
    ChatOptions,
    ChatTool,
    json_schema_format,
)
from carguito.application.use_cases.workstation_tools import LensTools


# --- a fake wire -------------------------------------------------------------
def _sse(*frames: dict) -> io.BytesIO:
    body = b"".join(f"data: {json.dumps(f)}\n\n".encode() for f in frames) + b"data: [DONE]\n\n"
    return io.BytesIO(body)


def _delta(**delta) -> dict:
    return {"choices": [{"delta": delta}]}


class _Wire:
    """Answers each POST with the next scripted response and keeps the payloads."""

    def __init__(self, *responses: io.BytesIO) -> None:
        self.responses = list(responses)
        self.payloads: list[dict] = []

    def __call__(self, request, timeout=None):
        self.payloads.append(json.loads(request.data))
        return self.responses.pop(0)


@pytest.fixture
def chat():
    return OpenAiCompatibleChat(base_url="https://x.test/v1", api_key="k", model="m")


def test_options_reach_the_wire(monkeypatch, chat):
    wire = _Wire(_sse(_delta(content="{}")))
    monkeypatch.setattr(urllib.request, "urlopen", wire)
    fmt = json_schema_format("thing", {"type": "object"})

    out = "".join(
        chat.stream(
            system="s",
            messages=[ChatMessage(role="user", content="u")],
            options=ChatOptions(temperature=0, max_tokens=50, response_format=fmt),
        )
    )

    assert out == "{}"
    payload = wire.payloads[0]
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 50
    assert payload["response_format"] == fmt
    assert "tools" not in payload


def test_no_options_means_the_same_request_as_before(monkeypatch, chat):
    wire = _Wire(_sse(_delta(content="hola")))
    monkeypatch.setattr(urllib.request, "urlopen", wire)
    list(chat.stream(system="s", messages=[]))
    # ...plus an output cap: gateways reserve the whole window against the
    # balance otherwise, and refuse accounts that cannot pay for 131k tokens.
    assert set(wire.payloads[0]) == {"model", "stream", "messages", "max_tokens"}
    assert wire.payloads[0]["max_tokens"] == 4096


def test_tool_round_runs_the_handler_and_feeds_the_result_back(monkeypatch, chat):
    # The call arrives in pieces: id and name first, then the arguments split
    # across two frames, which is how every provider actually streams them.
    first = _sse(
        _delta(content="Déjame ver. "),
        _delta(tool_calls=[{"index": 0, "id": "call_1", "function": {"name": "sumar", "arguments": '{"a": 1'}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": ', "b": 2}'}}]),
    )
    second = _sse(_delta(content="Son "), _delta(content="3."))
    wire = _Wire(first, second)
    monkeypatch.setattr(urllib.request, "urlopen", wire)

    seen = []

    def handler(name, args):
        seen.append((name, args))
        return json.dumps({"suma": args["a"] + args["b"]})

    tool = ChatTool(name="sumar", description="suma", parameters={"type": "object"})
    out = "".join(
        chat.stream(
            system="s",
            messages=[ChatMessage(role="user", content="1+2?")],
            options=ChatOptions(tools=[tool], tool_handler=handler),
        )
    )

    assert out == "Déjame ver. Son 3."
    assert seen == [("sumar", {"a": 1, "b": 2})]

    first_payload, second_payload = wire.payloads
    assert first_payload["tools"][0]["function"]["name"] == "sumar"
    assert first_payload["tool_choice"] == "auto"
    # The second request carries the whole exchange so far.
    tail = second_payload["messages"][-2:]
    assert tail[0]["role"] == "assistant"
    assert tail[0]["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "sumar", "arguments": '{"a": 1, "b": 2}'},
    }
    assert tail[1] == {"role": "tool", "tool_call_id": "call_1", "content": '{"suma": 3}'}


def test_a_failing_tool_is_reported_to_the_model_not_raised(monkeypatch, chat):
    first = _sse(_delta(tool_calls=[{"index": 0, "id": "c", "function": {"name": "x", "arguments": "not json"}}]))
    second = _sse(_delta(content="ok"))
    wire = _Wire(first, second)
    monkeypatch.setattr(urllib.request, "urlopen", wire)

    def handler(name, args):
        raise AssertionError("never reached: the arguments did not parse")

    tool = ChatTool(name="x", description="", parameters={"type": "object"})
    out = "".join(chat.stream(system="s", messages=[], options=ChatOptions(tools=[tool], tool_handler=handler)))

    assert out == "ok"
    reply = json.loads(wire.payloads[1]["messages"][-1]["content"])
    assert "argumentos inválidos" in reply["error"]


def test_a_model_that_keeps_calling_is_made_to_answer(monkeypatch, chat):
    def call():
        return _sse(_delta(tool_calls=[{"index": 0, "id": "c", "function": {"name": "x", "arguments": "{}"}}]))

    wire = _Wire(call(), call(), _sse(_delta(content="fin")))
    monkeypatch.setattr(urllib.request, "urlopen", wire)

    tool = ChatTool(name="x", description="", parameters={"type": "object"})
    out = "".join(
        chat.stream(
            system="s",
            messages=[],
            options=ChatOptions(tools=[tool], tool_handler=lambda n, a: "{}", max_tool_rounds=2),
        )
    )

    assert out == "fin"
    assert [p["tool_choice"] for p in wire.payloads] == ["auto", "auto", "none"]


def test_tools_without_a_handler_are_not_sent(monkeypatch, chat):
    wire = _Wire(_sse(_delta(content="hola")))
    monkeypatch.setattr(urllib.request, "urlopen", wire)
    tool = ChatTool(name="x", description="", parameters={"type": "object"})
    list(chat.stream(system="s", messages=[], options=ChatOptions(tools=[tool])))
    assert "tools" not in wire.payloads[0]


# --- the lens tools ----------------------------------------------------------
ROWS = [
    ("2026-06-01", "OXXO", "50.00"),  # lunes
    ("2026-06-03", "Oxxo Gas", "700.00"),  # miércoles
    ("2026-06-08", "OXXO", "70.00"),  # lunes
    ("2026-07-15", "Soriana", "1200.50"),  # miércoles
]


def test_group_by_description_folds_case_and_orders_by_weight():
    result = LensTools(ROWS).group({"por": "descripcion"})
    assert result["movimientos"] == 4
    assert result["total"] == "2020.50"
    labels = [g["grupo"] for g in result["grupos"]]
    assert labels == ["Soriana", "Oxxo Gas", "OXXO"]
    oxxo = result["grupos"][2]
    assert (oxxo["movimientos"], oxxo["total"], oxxo["promedio"]) == (2, "120.00", "60.00")


def test_group_by_month_and_weekday_read_in_order():
    by_month = LensTools(ROWS).group({"por": "mes"})
    assert [(g["grupo"], g["total"]) for g in by_month["grupos"]] == [
        ("2026-06", "820.00"),
        ("2026-07", "1200.50"),
    ]
    by_weekday = LensTools(ROWS).group({"por": "dia_semana"})
    assert [(g["grupo"], g["movimientos"]) for g in by_weekday["grupos"]] == [
        ("lunes", 2),
        ("miércoles", 2),
    ]


def test_search_filters_and_caps():
    tools = LensTools(ROWS)
    hit = tools.search({"contiene": "oxxo", "monto_max": 100, "orden": "monto_desc", "limite": 1})
    assert hit["coinciden"] == 2
    assert hit["total"] == "120.00"
    assert hit["mostrados"] == 1
    assert hit["movimientos"] == [{"fecha": "2026-06-08", "descripcion": "OXXO", "monto": "70.00"}]

    by_date = tools.search({"desde": "2026-07-01"})
    assert [m["descripcion"] for m in by_date["movimientos"]] == ["Soriana"]


def test_summary_is_the_arithmetic_over_the_rows():
    out = LensTools(ROWS).summary({"hasta": "2026-06-30"})
    assert out["movimientos"] == 3
    assert out["total"] == "820.00"
    assert out["mediana"] == "70.00"
    assert (out["minimo"], out["maximo"]) == ("50.00", "700.00")
    assert (out["primer_movimiento"], out["ultimo_movimiento"]) == ("2026-06-01", "2026-06-08")
    assert out["dias_cubiertos"] == 8


def test_summary_of_nothing_says_so():
    assert LensTools(ROWS).summary({"contiene": "walmart"})["movimientos"] == 0


def test_call_rejects_what_it_does_not_know():
    tools = LensTools(ROWS)
    with pytest.raises(ValueError):
        tools.call("borrar_todo", {})
    with pytest.raises(ValueError):
        tools.call("buscar_movimientos", {"desde": "ayer"})
    assert json.loads(tools.call("resumen_de_periodo", {}))["total"] == "2020.50"


def test_every_tool_spec_is_a_function_the_handler_answers():
    tools = LensTools(ROWS)
    for spec in tools.specs:
        args = {"por": "mes"} if spec.name == "agrupar_movimientos" else {}
        json.loads(tools.call(spec.name, args))


def test_parse_listings_accepts_both_shapes():
    row = {"url": "https://a", "price": 1}
    assert parse_listings(json.dumps([row])) == [row]
    assert parse_listings(json.dumps({"listings": [row]})) == [row]
    assert parse_listings('```json\n{"listings": []}\n```') == []
    assert parse_listings("no") == []
