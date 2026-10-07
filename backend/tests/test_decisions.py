"""The typed-decision seam: what goes on the wire, and what comes back as a type.

The chat port is tested for what it refuses to say. This one is tested for what
it refuses to *return*: a value outside the option set, a frame it could not
read, a provider that was busy. Every one of those must leave the caller with
nothing rather than with something that looks like an answer -- because every
caller here has a path for nothing, and none has a path for a wrong type.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from carguito.adapters.outbound.decisions import TypeSafeDecisions
from carguito.application.ports.outbound.decisions import (
    Choice,
    ChoiceAnswer,
    DecisionsUnavailable,
    Noul,
    NoulAnswer,
    NullDecisions,
    Score,
    ScoreAnswer,
)


def _body(answers: dict) -> io.BytesIO:
    return io.BytesIO(
        json.dumps(
            {"model": "jev-latest", "answers": answers,
             "usage": {"input_tokens": 312, "output_tokens": 48}}
        ).encode()
    )


class _Wire:
    """Answers each POST with the next scripted response, keeping the payloads.

    A scripted entry may be an exception, which is raised instead of returned:
    that is how a 429 followed by a 200 is spelled.
    """

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.payloads: list[dict] = []

    def __call__(self, request, timeout=None):
        self.payloads.append(json.loads(request.data))
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _http_error(code: int, message: str = "nope") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.typesafe.ai/v1/systemone", code, message, {},
        io.BytesIO(json.dumps({"error": {"message": message}}).encode()),
    )


@pytest.fixture
def decisions():
    return TypeSafeDecisions(api_key="k", model="jev-latest", base_url="https://api.typesafe.ai/v1")


def test_the_three_question_types_reach_the_wire_in_the_documented_shape(monkeypatch, decisions):
    wire = _Wire(_body({
        "department": {"type": "choice", "choice": "technical",
                       "probabilities": {"billing": 0.08, "technical": 0.85, "sales": 0.07},
                       "confidence": 0.82},
        "frustration": {"type": "score", "score": 1.6,
                        "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
                        "probabilities": {"0": 0.05, "1": 0.3, "2": 0.65}, "confidence": 0.78},
        "is_urgent": {"type": "noul", "noul": 0.92},
    }))
    monkeypatch.setattr(urllib.request, "urlopen", wire)

    answers = decisions.evaluate(
        state="Help! My payouts have been failing for 3 days.",
        questions={
            "department": Choice(
                instructions="Which team should handle this?",
                criteria={"billing": "Payments", "technical": "Bugs", "sales": None},
            ),
            "frustration": Score(
                instructions="How frustrated is the customer?",
                criteria=["Calm", "Frustrated", "Very angry"],
            ),
            "is_urgent": Noul(instructions="Does this convey urgency?"),
        },
    )

    # One round trip for three questions: they share the state, which is the
    # whole reason the port takes a map rather than one question.
    payload = wire.payloads[0]
    assert len(wire.payloads) == 1
    assert payload["model"] == "jev-latest"
    assert payload["state"].startswith("Help!")
    assert payload["questions"]["department"] == {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {"billing": "Payments", "technical": "Bugs", "sales": None},
    }
    assert payload["questions"]["frustration"]["criteria"] == ["Calm", "Frustrated", "Very angry"]
    # An optional criteria the caller did not give is absent, not null.
    assert payload["questions"]["is_urgent"] == {
        "type": "noul", "instructions": "Does this convey urgency?"
    }

    assert answers["department"] == ChoiceAnswer(
        choice="technical",
        probabilities={"billing": 0.08, "technical": 0.85, "sales": 0.07},
        confidence=0.82,
    )
    assert isinstance(answers["frustration"], ScoreAnswer)
    assert answers["frustration"].score == 1.6
    assert answers["frustration"].legend["2"] == "Very angry"
    assert answers["is_urgent"] == NoulAnswer(noul=0.92)


def test_a_noul_criteria_travels_when_the_caller_gave_one(monkeypatch, decisions):
    wire = _Wire(_body({"q": {"type": "noul", "noul": 0.1}}))
    monkeypatch.setattr(urllib.request, "urlopen", wire)

    decisions.evaluate(
        state="x",
        questions={"q": Noul(instructions="¿Es urgente?",
                             criteria={"true": "Sí", "false": "No"})},
    )

    assert wire.payloads[0]["questions"]["q"]["criteria"] == {"true": "Sí", "false": "No"}


def test_a_choice_outside_the_options_is_not_an_answer(monkeypatch, decisions):
    """The option set is the contract. A caller switching on the value would
    otherwise take a branch that does not exist."""
    wire = _Wire(_body({"q": {"type": "choice", "choice": "marketing",
                              "probabilities": {"marketing": 0.9}, "confidence": 0.9}}))
    monkeypatch.setattr(urllib.request, "urlopen", wire)

    answers = decisions.evaluate(
        state="x", questions={"q": Choice(instructions="?", criteria={"billing": None})}
    )

    assert answers == {}


def test_a_frame_that_cannot_be_read_costs_the_answer_not_the_request(monkeypatch, decisions):
    """A renamed field should cost the caller its fallback, which it has, and
    not a 500 on a page whose other half is deterministic."""
    wire = _Wire(_body({
        "bad": {"type": "choice", "choice": "a"},  # no probabilities, no confidence
        "good": {"type": "noul", "noul": 0.4},
    }))
    monkeypatch.setattr(urllib.request, "urlopen", wire)

    answers = decisions.evaluate(
        state="x",
        questions={"bad": Choice(instructions="?", criteria={"a": None}),
                   "good": Noul(instructions="?")},
    )

    assert "bad" not in answers
    assert answers["good"] == NoulAnswer(noul=0.4)


def test_busy_is_retried_and_broken_is_not(monkeypatch, decisions):
    monkeypatch.setattr("carguito.adapters.outbound.decisions.typesafe._RETRY_DELAYS", (0.0, 0.0))

    wire = _Wire(_http_error(429), _http_error(529), _body({"q": {"type": "noul", "noul": 1.0}}))
    monkeypatch.setattr(urllib.request, "urlopen", wire)
    assert decisions.evaluate(state="x", questions={"q": Noul(instructions="?")}) == {
        "q": NoulAnswer(noul=1.0)
    }
    assert len(wire.payloads) == 3

    # 401 and 422 are the request or the configuration being wrong. Retrying
    # them is the same wrong answer, later.
    for code in (401, 422):
        wire = _Wire(_http_error(code, "mal"))
        monkeypatch.setattr(urllib.request, "urlopen", wire)
        with pytest.raises(DecisionsUnavailable, match=str(code)):
            decisions.evaluate(state="x", questions={"q": Noul(instructions="?")})
        assert len(wire.payloads) == 1


def test_a_provider_that_stays_busy_gives_up(monkeypatch, decisions):
    monkeypatch.setattr("carguito.adapters.outbound.decisions.typesafe._RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(urllib.request, "urlopen", _Wire(*[_http_error(429)] * 3))

    with pytest.raises(DecisionsUnavailable):
        decisions.evaluate(state="x", questions={"q": Noul(instructions="?")})


def test_no_questions_is_no_request(monkeypatch, decisions):
    monkeypatch.setattr(urllib.request, "urlopen", _Wire())
    assert decisions.evaluate(state="x", questions={}) == {}


def test_an_unset_key_is_a_state_not_an_error():
    """A fresh clone has no key. Callers branch on `available` rather than
    catching, the same contract as the chat port."""
    assert TypeSafeDecisions(api_key="", model="jev-latest").available is False
    assert NullDecisions().available is False
    with pytest.raises(DecisionsUnavailable, match="TYPESAFE_API_KEY"):
        NullDecisions().evaluate(state="x", questions={"q": Noul(instructions="?")})
