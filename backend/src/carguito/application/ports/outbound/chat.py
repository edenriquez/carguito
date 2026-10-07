"""The one seam an LLM may reach the product through.

Everything else in Tomin is deterministic by design -- a closed metric catalog,
a rule engine that returns a dormant principle rather than a guess. A chat
answer is the first thing here that cannot be reproduced from the data alone,
so it gets a narrow port with a null implementation, and every caller is written
against the possibility that no model is configured at all.

Deliberately provider-agnostic. The adapter speaks OpenAI-shaped Chat
Completions against a configurable base URL, which is the lingua franca of every
gateway worth pointing at -- OpenRouter, Groq, Together, a local Ollama. Nothing
above this line names a vendor, and swapping one is three environment variables.

Three things ride on a request beyond the messages, and all three are optional
so a caller that wants none of them passes nothing:

* **Sampling** (`temperature`, `max_tokens`). Extraction wants a cold model;
  conversation does not care.
* **A response schema.** When the answer has to be parsed, the schema is the
  request, not a plea in the prompt. The caller still validates -- a schema is
  a strong hint to the provider, not a proof.
* **Tools.** Functions the model may call, run by the caller, whose results
  go back to the model before it answers. This is how the model reaches data
  that would not fit in a prompt -- and how every figure it quotes stays a
  figure this code computed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    """One turn. The system prompt is passed separately, never as a message."""

    role: Role
    content: str


@dataclass(frozen=True)
class ChatTool:
    """A function the model may ask for. ``parameters`` is a JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any]


#: Runs one tool call. Gets the tool's name and its parsed arguments, returns
#: the text the model reads back -- JSON, usually. Whatever it raises is
#: reported to the model as an error rather than to the user as a crash.
ToolHandler = Callable[[str, dict[str, Any]], str]


@dataclass(frozen=True)
class ChatOptions:
    """Everything a request may carry besides the messages. All optional."""

    temperature: float | None = None
    max_tokens: int | None = None
    #: OpenAI-shaped ``response_format``. Build it with :func:`json_schema_format`.
    response_format: dict[str, Any] | None = None
    tools: Sequence[ChatTool] = ()
    tool_handler: ToolHandler | None = None
    #: How many times the model may go back to the tools before it must answer
    #: with what it has. A cap, not a target: most questions take one round.
    max_tool_rounds: int = 6


def json_schema_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """A ``response_format`` that pins the answer to one JSON Schema.

    Strict mode is requested; providers that support it refuse to emit a key
    the schema does not name. Ones that do not understand it fall back to plain
    JSON mode or ignore the field, which is why the caller keeps parsing
    defensively either way.
    """
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


class ChatPort(Protocol):
    """Streams an answer, token by token.

    Streaming is not decoration: a grounded answer over six months of movements
    takes seconds, and a request that returns all at once both risks the HTTP
    timeout and shows the user a blank panel while it thinks.
    """

    @property
    def available(self) -> bool:
        """False when no model is configured.

        Callers branch on this rather than catching an exception, because
        "the owner has not set a key" is a normal state of a fresh clone and
        must render as a disabled panel, not an error.
        """
        ...

    @property
    def model_label(self) -> str:
        """What to name in the UI's disclosure. The user is entitled to know
        which third party their movements are about to be described to."""
        ...

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        options: ChatOptions | None = None,
    ) -> Iterator[str]:
        """Yield answer fragments in order. Raises :class:`ChatUnavailable`.

        When ``options.tools`` is set, tool rounds happen inside this call:
        the model's requests are run through ``options.tool_handler`` and only
        the final answer's text is yielded. Callers see one stream either way.
        """
        ...


class ChatUnavailable(RuntimeError):
    """The configured provider could not be reached, or refused the request.

    Distinct from "not configured": this one is worth showing the user as a
    failure, because they did set it up and it did not work.
    """


__all__ = [
    "ChatMessage",
    "ChatOptions",
    "ChatPort",
    "ChatTool",
    "ChatUnavailable",
    "Role",
    "ToolHandler",
    "json_schema_format",
]
