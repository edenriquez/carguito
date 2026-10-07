"""The decisions port over TypeSafe's System One endpoint.

One POST, one JSON body, one JSON answer -- no stream, no frames, no partial
state. Written against ``urllib`` for the same reason the chat adapter is: the
vendor ships an SDK, and taking it would put a vendor name in the dependency
list to spell a request this file spells in forty lines. The same judgement
that kept this repo to Flask, SQLAlchemy and DuckDB.

The provider asks for exponential backoff on 429 and 529 and its SDK does it,
so this file does it too -- but twice and briefly. Every caller in Tomin runs
this inside a request the user is waiting on, and a decision that is never
load-bearing must not be the reason a page takes ten seconds.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from ....application.ports.outbound.decisions import (
    Answer,
    Choice,
    ChoiceAnswer,
    DecisionsUnavailable,
    Noul,
    NoulAnswer,
    Question,
    Score,
    ScoreAnswer,
)

logger = logging.getLogger(__name__)

#: Generous for a model that answers in 70-500ms, short enough that a wedged
#: provider does not hold a worker while the user watches a spinner.
_TIMEOUT = 15.0

#: Statuses the provider tells you to retry. Everything else is a bug in the
#: request (422) or in the configuration (401) and retrying it is just slower.
_RETRY_STATUSES = frozenset({429, 529})

#: Two retries, 0.4s then 1.2s. Past that the answer is late enough that the
#: caller's fallback is the better outcome.
_RETRY_DELAYS = (0.4, 1.2)


class TypeSafeDecisions:
    """Implements :class:`DecisionPort` against ``/v1/systemone``."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "jev-latest",
        base_url: str = "https://api.typesafe.ai/v1",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self._api_key and self._model)

    @property
    def model_label(self) -> str:
        return self._model

    def evaluate(self, *, state: Any, questions: Mapping[str, Question]) -> dict[str, Answer]:
        if not questions:
            return {}
        payload = {
            "state": state,
            "model": self._model,
            "questions": {qid: _encode(q) for qid, q in questions.items()},
        }
        body = self._post(payload)
        answers = body.get("answers")
        if not isinstance(answers, dict):
            raise DecisionsUnavailable("La respuesta del proveedor no traía answers.")
        # Only the ids that were asked, and only the ones that parsed. A caller
        # reading `answers["term"]` on a malformed frame should get a KeyError
        # it can see, not a half-built object that looks like an answer.
        decoded: dict[str, Answer] = {}
        for qid, question in questions.items():
            raw = answers.get(qid)
            if isinstance(raw, dict):
                parsed = _decode(question, raw)
                if parsed is not None:
                    decoded[qid] = parsed
        return decoded

    # --- the wire ----------------------------------------------------------
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        for attempt in range(len(_RETRY_DELAYS) + 1):
            request = urllib.request.Request(
                f"{self._base_url}/systemone",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUSES and attempt < len(_RETRY_DELAYS):
                    time.sleep(_RETRY_DELAYS[attempt])
                    continue
                detail = _safe_read(exc)
                logger.warning("decisions provider returned %s: %s", exc.code, detail)
                raise DecisionsUnavailable(f"El proveedor respondió {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                raise DecisionsUnavailable(f"No se pudo contactar al proveedor: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise DecisionsUnavailable("El proveedor respondió algo que no era JSON.") from exc
        raise DecisionsUnavailable("El proveedor siguió ocupado tras los reintentos.")


# --- encoding ----------------------------------------------------------------
def _encode(question: Question) -> dict[str, Any]:
    if isinstance(question, Choice):
        return {
            "type": "choice",
            "instructions": question.instructions,
            "criteria": dict(question.criteria),
        }
    if isinstance(question, Score):
        return {
            "type": "score",
            "instructions": question.instructions,
            "criteria": list(question.criteria),
        }
    if isinstance(question, Noul):
        encoded: dict[str, Any] = {"type": "noul", "instructions": question.instructions}
        if question.criteria:
            encoded["criteria"] = dict(question.criteria)
        return encoded
    raise TypeError(f"tipo de pregunta desconocido: {type(question).__name__}")


def _decode(question: Question, raw: dict[str, Any]) -> Answer | None:
    """One answer, or nothing.

    Nothing rather than an exception: a provider that adds a field or renames
    one should cost a caller its fallback path, which every caller has, and not
    a 500 on a page whose other half is deterministic.
    """
    try:
        if isinstance(question, Choice):
            choice = raw["choice"]
            probabilities = {str(k): float(v) for k, v in dict(raw["probabilities"]).items()}
            # The contract of this port is that the answer is inside the set.
            # A provider that broke it gets treated as a failed call, because a
            # caller switching on the value would otherwise take a branch that
            # does not exist.
            if choice not in question.criteria:
                logger.warning("choice %r is outside the criteria it was asked over", choice)
                return None
            return ChoiceAnswer(
                choice=str(choice),
                probabilities=probabilities,
                confidence=float(raw["confidence"]),
            )
        if isinstance(question, Score):
            return ScoreAnswer(
                score=float(raw["score"]),
                legend={str(k): str(v) for k, v in dict(raw.get("legend") or {}).items()},
                probabilities={str(k): float(v) for k, v in dict(raw["probabilities"]).items()},
                confidence=float(raw["confidence"]),
            )
        if isinstance(question, Noul):
            return NoulAnswer(noul=float(raw["noul"]))
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("could not read a %s answer: %s", type(question).__name__, exc)
    return None


def _safe_read(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - the error path of an error path
        return exc.reason or "sin detalle"
    try:
        parsed = json.loads(body)
        message = parsed.get("error", {}).get("message") or parsed.get("message")
        if message:
            return str(message)
    except (json.JSONDecodeError, AttributeError):
        pass
    return body[:200] or (exc.reason or "sin detalle")
