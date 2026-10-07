from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

#: A title longer than this stops being a title. Derived from the first
#: question when the conversation starts; the cut is a display decision made
#: once, at write time, so every reader shows the same words.
MAX_TITLE_LENGTH = 80

#: An inferred list-title is a name, not a caption. Five words is the most
#: that still scans in a rail; the character cap catches a single long token.
MAX_INFERRED_WORDS = 5
MAX_INFERRED_LENGTH = 48


def title_from_question(question: str) -> str:
    """The first question, trimmed to a title.

    One line, no ellipsis games: a hard cut at a word boundary where possible.
    The full question still exists as the conversation's first message.
    """
    text = " ".join(question.split())
    if len(text) <= MAX_TITLE_LENGTH:
        return text
    cut = text[:MAX_TITLE_LENGTH]
    head, _, _ = cut.rpartition(" ")
    return (head or cut) + "…"


def sanitize_inferred_title(raw: str) -> str:
    """Turn a model's title attempt into a list name, or empty if unusable.

    The first question is already stored as a fallback; an empty return means
    keep that. Stripping quotes and punctuation is what makes "Nómina en
    Soriana" rather than "«Nómina en Soriana.»" land in the rail.
    """
    text = " ".join((raw or "").split())
    text = text.strip(" «»\"'`.,;:¡!¿?-—")
    if not text:
        return ""
    words = text.split()[:MAX_INFERRED_WORDS]
    text = " ".join(words)
    if len(text) > MAX_INFERRED_LENGTH:
        cut = text[:MAX_INFERRED_LENGTH]
        head, _, _ = cut.rpartition(" ")
        text = head or cut
    return text


@dataclass(slots=True)
class Conversation:
    """One thread of questions about one workstation.

    A workstation invites several *analyses* — "why was May high?" and "when
    should I withdraw?" are different investigations over the same set — so
    conversations are a collection under the lens, not a single running log.
    """

    workstation_id: UUID
    user_id: UUID
    title: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.title = " ".join(self.title.split())
        if not self.title:
            raise ValueError("A conversation needs a title.")


@dataclass(slots=True)
class ConversationTurn:
    """One stored message. Only the two roles the chat protocol knows."""

    conversation_id: UUID
    role: str
    content: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise ValueError(f"Unknown role {self.role!r}")
        if not self.content:
            raise ValueError("A turn needs content.")
