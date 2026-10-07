"""Chat over the OpenAI-shaped Completions protocol, against any base URL.

One adapter covers OpenRouter, Groq, Together, DeepSeek, LM Studio and a local
Ollama, because they all speak the same request and the same SSE frames. That is
the entire reason this is the protocol rather than a vendor SDK: switching
providers is three environment variables, and no vendor name appears above the
adapter line.

Written against ``urllib`` rather than a client library on purpose. The protocol
is a POST and a stream of ``data:`` lines; pulling in an HTTP stack (or a vendor
SDK, which would defeat the point) to spell that is a dependency this repo does
not need -- the same judgement that kept it to Flask, SQLAlchemy and DuckDB.

Tool calls are handled here, not above. A caller hands over the tool specs and
one function that runs them; this adapter loops -- request, run what the model
asked for, append the results, request again -- until the model answers in
text, and only that text is yielded. The protocol details (the ``tool_calls``
deltas arrive in pieces, split across frames, keyed by index) belong to the
protocol, so they live with it.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from typing import Any

from ....application.ports.outbound.chat import (
    ChatMessage,
    ChatOptions,
    ChatPort,
    ChatUnavailable,
)

logger = logging.getLogger(__name__)

#: Long enough for a slow free-tier queue, short enough that a wedged provider
#: does not hold a worker forever.
_CONNECT_TIMEOUT = 30.0

#: Sent whenever the caller did not choose one. Gateways reserve the model's
#: whole output window against the account balance before answering, and a
#: model that can emit 131k tokens is refused with a 402 on any account that
#: cannot pay for 131k tokens -- for a question whose answer is a paragraph.
#: Four thousand is a long answer and a hundred-line ticket, and still a few
#: cents at most.
_DEFAULT_MAX_TOKENS = 4096

#: A tool's answer beyond this is not an answer, it is a dump. Cut so a rogue
#: query cannot turn one round into a context-sized request.
_MAX_TOOL_RESULT_CHARS = 60_000


class OpenAiCompatibleChat:
    """Implements :class:`ChatPort` against an OpenAI-shaped endpoint."""

    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    @property
    def available(self) -> bool:
        return bool(self._base_url and self._api_key and self._model)

    @property
    def model_label(self) -> str:
        return self._model

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        options: ChatOptions | None = None,
    ) -> Iterator[str]:
        options = options or ChatOptions()
        # System first and unchanging, so a gateway that caches prefixes can.
        # Nothing here depends on it working -- caching is a bonus, not a
        # behaviour this code relies on.
        conversation: list[dict[str, Any]] = [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content} for m in messages
        ]
        # Tools travel only when someone is there to run them; a spec without a
        # handler would invite calls nobody answers.
        tools_on = bool(options.tools) and options.tool_handler is not None

        rounds = 0
        while True:
            # On the last permitted round the model keeps the specs (so its
            # earlier calls still make sense to it) but may not call again.
            payload = self._payload(
                conversation, options, tools_on, allow_calls=rounds < options.max_tool_rounds
            )
            response = self._post(payload)

            text: list[str] = []
            calls: dict[int, dict[str, str]] = {}
            with response:
                for delta in _parse_sse(response):
                    piece = delta.get("content")
                    if piece:
                        text.append(piece)
                        yield piece
                    for call in delta.get("tool_calls") or []:
                        _accumulate(calls, call)

            if not calls or not tools_on or rounds >= options.max_tool_rounds:
                return
            rounds += 1
            conversation.append(_assistant_turn("".join(text), calls))
            for index in sorted(calls):
                conversation.append(_run(calls[index], index, options))

    # --- request -----------------------------------------------------------
    def _payload(
        self,
        conversation: list[dict[str, Any]],
        options: ChatOptions,
        tools_on: bool,
        *,
        allow_calls: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": True,
            "messages": conversation,
        }
        if options.temperature is not None:
            payload["temperature"] = options.temperature
        payload["max_tokens"] = options.max_tokens or _DEFAULT_MAX_TOKENS
        if options.response_format is not None:
            payload["response_format"] = options.response_format
        if tools_on:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in options.tools
            ]
            payload["tool_choice"] = "auto" if allow_calls else "none"
        return payload

    def _post(self, payload: dict[str, Any]):
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            return urllib.request.urlopen(request, timeout=_CONNECT_TIMEOUT)
        except urllib.error.HTTPError as exc:
            # The provider's own message is the useful half ("model not found",
            # "rate limited"); the status alone sends the user hunting.
            detail = _safe_read(exc)
            logger.warning("chat provider returned %s: %s", exc.code, detail)
            raise ChatUnavailable(f"El proveedor respondió {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ChatUnavailable(f"No se pudo contactar al proveedor: {exc}") from exc


class FallbackChat:
    """Primary model, then the configured fallback if that one refuses.

    The HTTP error happens before any token is yielded, so a 429 or an
    outage on the first model can still produce a full answer from the
    second. A mid-stream failure is left as-is — half an answer plus an
    error is better than restarting the question on a different model.
    """

    def __init__(self, primary: ChatPort, fallback: ChatPort) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def available(self) -> bool:
        return self._primary.available

    @property
    def model_label(self) -> str:
        return f"{self._primary.model_label} · {self._fallback.model_label}"

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        options: ChatOptions | None = None,
    ) -> Iterator[str]:
        try:
            iterator = self._primary.stream(system=system, messages=messages, options=options)
            first = next(iterator)
        except ChatUnavailable:
            yield from self._fallback.stream(system=system, messages=messages, options=options)
            return
        except StopIteration:
            return
        yield first
        yield from iterator


# --- tool rounds -------------------------------------------------------------
def _accumulate(calls: dict[int, dict[str, str]], call: dict[str, Any]) -> None:
    """Fold one ``tool_calls`` delta into the call it belongs to.

    Providers stream the id and name once and the arguments in fragments, all
    keyed by ``index``. A few omit the index on a single call; that one is 0.
    """
    index = call.get("index")
    slot = calls.setdefault(index if isinstance(index, int) else 0, {"id": "", "name": "", "arguments": ""})
    if call.get("id"):
        slot["id"] = str(call["id"])
    function = call.get("function") or {}
    if function.get("name"):
        slot["name"] = str(function["name"])
    if function.get("arguments"):
        slot["arguments"] += str(function["arguments"])


def _assistant_turn(text: str, calls: dict[int, dict[str, str]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": _call_id(calls[i], i),
                "type": "function",
                "function": {"name": calls[i]["name"], "arguments": calls[i]["arguments"] or "{}"},
            }
            for i in sorted(calls)
        ],
    }


def _run(call: dict[str, str], index: int, options: ChatOptions) -> dict[str, Any]:
    """One tool call, answered. Failures are told to the model, not raised.

    A model that asked for something malformed gets the parse error back and a
    chance to ask again; a handler that raised gets its message reported the
    same way. Neither is the user's problem -- the stream keeps going.
    """
    name = call["name"]
    try:
        arguments = json.loads(call["arguments"] or "{}")
        if not isinstance(arguments, dict):
            raise TypeError("los argumentos deben ser un objeto JSON")
    except (ValueError, TypeError) as exc:
        result = json.dumps({"error": f"argumentos inválidos: {exc}"}, ensure_ascii=False)
    else:
        assert options.tool_handler is not None
        # Whatever the handler raises is the model's problem to work around,
        # never the user's: it goes back as an error message, not up the stack.
        try:
            result = options.tool_handler(name, arguments)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool %s failed: %s", name, exc)
            result = json.dumps({"error": str(exc)}, ensure_ascii=False)
    if len(result) > _MAX_TOOL_RESULT_CHARS:
        result = result[:_MAX_TOOL_RESULT_CHARS] + "\n… (truncado)"
    logger.info("tool %s(%s) -> %d chars", name, call["arguments"][:200], len(result))
    return {"role": "tool", "tool_call_id": _call_id(call, index), "content": result}


def _call_id(call: dict[str, str], index: int) -> str:
    return call["id"] or f"call_{index}"


# --- the wire ----------------------------------------------------------------
def _parse_sse(response) -> Iterator[dict[str, Any]]:
    """Yield the ``delta`` objects out of an SSE stream.

    Frames that are not JSON, or that carry no delta, are skipped rather than
    raised on: providers interleave keep-alive comments and usage frames, and a
    strict parser here would turn a working stream into an error on the first
    one it had not seen before.
    """
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return
        try:
            frame = json.loads(data)
        except json.JSONDecodeError:
            continue
        for choice in frame.get("choices") or []:
            delta = choice.get("delta")
            if isinstance(delta, dict):
                yield delta


def _safe_read(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - the error path of an error path
        return exc.reason or "sin detalle"
    # Providers wrap the message differently; try the common shape, fall back to
    # the raw body truncated, never to an empty string.
    try:
        parsed = json.loads(body)
        message = parsed.get("error", {}).get("message") or parsed.get("message")
        if message:
            return str(message)
    except json.JSONDecodeError:
        pass
    return body[:200] or (exc.reason or "sin detalle")


class NullChat:
    """What the container injects when no model is configured.

    A fresh clone has no key, and that is a normal state rather than a broken
    one: the Workspace view still reads, and only the chat band renders disabled
    with its reason. Raising from here instead would make the absence of an
    optional integration look like a bug in the product.
    """

    available = False
    model_label = ""

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        options: ChatOptions | None = None,
    ) -> Iterator[str]:
        raise ChatUnavailable(
            "No hay un modelo configurado. Define LLM_BASE_URL, LLM_API_KEY y LLM_MODEL."
        )
