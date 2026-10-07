"""Typed decisions: the second model seam, and the narrow one.

:mod:`chat` exists because an *answer in words* cannot be computed from the
data. This port exists for the opposite reason: a handful of places in Tomin
need a **decision**, not prose -- which of these words names this product,
is this question asking about a store we do not have, are these two lines the
same thing. Today those are asked of a text model at ``temperature=0`` and the
caller validates the string afterwards, which is a chat model doing a job it
was not built for and a regex cleaning up after it.

A System One model answers those directly: a state goes in, a typed value comes
out, with the probability distribution it came from and a confidence derived
from that distribution. There is no free text to parse, so there is no parse to
get wrong.

Three shapes, and they are the provider's, not an abstraction over it:

* :class:`Choice` -- one option out of a set the caller defines. The set is the
  contract: an answer outside it is not possible, which is the whole point.
* :class:`Score` -- a position along ordered levels, which may land between two.
* :class:`Noul` -- the probability that a statement is true, 0 to 1.

Deliberately vendor-neutral above this line, same as the chat port: nothing here
names TypeSafe, and the adapter below is one file. But the shapes are honest
about what they are -- pretending a typed decision is a chat completion is what
this port exists to stop.

**Confidence is the reason to use this.** Every caller is written as three
paths, not one: act, ask, or do nothing. A decision taken below its threshold
must fall back to whatever the code did before the model existed -- which in
this repo is usually "show nothing and let the user type it".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


# --- questions ---------------------------------------------------------------
@dataclass(frozen=True)
class Choice:
    """One option out of ``criteria``. Values describe an option, or are None."""

    instructions: str
    criteria: Mapping[str, str | None]


@dataclass(frozen=True)
class Score:
    """A position along ``criteria``, an ordered list of at least two levels."""

    instructions: str
    criteria: Sequence[str]


@dataclass(frozen=True)
class Noul:
    """Is this true? ``criteria`` optionally says what a yes and a no mean."""

    instructions: str
    criteria: Mapping[str, str] | None = None


Question = Choice | Score | Noul


# --- answers -----------------------------------------------------------------
@dataclass(frozen=True)
class ChoiceAnswer:
    """``choice`` is always a key the caller put in ``criteria``.

    ``confidence`` collapses ``probabilities`` into one number so callers can
    threshold without doing the statistics; the distribution rides along for
    the caller that wants a different measure.
    """

    choice: str
    probabilities: Mapping[str, float]
    confidence: float


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    legend: Mapping[str, str]
    probabilities: Mapping[str, float]
    confidence: float


@dataclass(frozen=True)
class NoulAnswer:
    """0 is no, 1 is yes, and near 0.5 is the model saying it cannot tell.

    No ``confidence``: the value *is* the uncertainty, and a second number over
    it would invite reading one when the other was meant.
    """

    noul: float


Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer


class DecisionPort(Protocol):
    """Evaluates several questions against one state, in one round trip.

    Batching is the provider's own shape and worth keeping: the questions share
    the state, are evaluated independently, and cost one request. A caller with
    two questions about the same receipt should ask them together.
    """

    @property
    def available(self) -> bool:
        """False when no key is configured -- a normal state, not a failure."""
        ...

    @property
    def model_label(self) -> str:
        """What to name in the UI's disclosure, same contract as the chat port."""
        ...

    def evaluate(
        self,
        *,
        state: Any,
        questions: Mapping[str, Question],
    ) -> dict[str, Answer]:
        """Answers keyed by the caller's own ids. Raises :class:`DecisionsUnavailable`.

        ``state`` is text, or any JSON-shaped object or list when the thing
        being judged has structure worth keeping.
        """
        ...


class DecisionsUnavailable(RuntimeError):
    """Configured and did not work -- distinct from "not configured"."""


class NullDecisions:
    """What the container injects when no key is set.

    Every caller already branches on ``available`` and has a path for the
    answer it cannot get, because that path is what the product did before any
    of this existed.
    """

    available = False
    model_label = ""

    def evaluate(self, *, state: Any, questions: Mapping[str, Question]) -> dict[str, Answer]:
        raise DecisionsUnavailable(
            "No hay un modelo de decisiones configurado. Define TYPESAFE_API_KEY."
        )


__all__ = [
    "Answer",
    "Choice",
    "ChoiceAnswer",
    "DecisionPort",
    "DecisionsUnavailable",
    "Noul",
    "NoulAnswer",
    "NullDecisions",
    "Question",
    "Score",
    "ScoreAnswer",
]
