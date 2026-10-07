"""Persisted chat threads under a workstation.

The chat itself (grounding, streaming, the model) lives in
:mod:`workstation_chat`; this is only the memory. Kept apart on purpose: the
model integration is optional — a fresh clone has no key — but a conversation
the user already had is their data and must survive whether or not a model is
currently configured to continue it.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from ...domain.entities import Conversation, ConversationTurn, title_from_question
from ..ports.outbound import ChatMessage, ConversationRepository


class ConversationNotFound(LookupError):
    """No conversation with that id belongs to this user.

    Same non-disclosure as ``WorkstationNotFound``: a missing row and someone
    else's row are one answer.
    """


class ManageConversations:
    """List, read, start, extend and delete a user's chat threads."""

    def __init__(self, conversations: ConversationRepository) -> None:
        self._conversations = conversations

    def list(self, *, user_id: UUID, workstation_id: UUID) -> list[Conversation]:
        return self._conversations.list_for_workstation(user_id, workstation_id)

    def get(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = self._conversations.get(user_id, conversation_id)
        if conversation is None:
            raise ConversationNotFound(str(conversation_id))
        return conversation

    def start(
        self, *, user_id: UUID, workstation_id: UUID, first_question: str
    ) -> Conversation:
        """A new thread, titled after what opened it."""
        conversation = Conversation(
            user_id=user_id,
            workstation_id=workstation_id,
            title=title_from_question(first_question),
        )
        self._conversations.add(conversation)
        return conversation

    def turns(self, *, user_id: UUID, conversation_id: UUID) -> list[ConversationTurn]:
        # Existence first, so an unknown id is a 404 and not an empty thread.
        self.get(user_id=user_id, conversation_id=conversation_id)
        return self._conversations.turns(user_id, conversation_id)

    def history(self, *, user_id: UUID, conversation_id: UUID) -> list[ChatMessage]:
        """The thread as the chat port speaks it — what the model gets to see.

        Server-side rather than trusting the client to echo the transcript
        back: the stored thread is the one source of what was actually said.
        """
        return [
            ChatMessage(role=t.role, content=t.content)
            for t in self.turns(user_id=user_id, conversation_id=conversation_id)
        ]

    def append(
        self, *, user_id: UUID, conversation_id: UUID, role: str, content: str
    ) -> None:
        if not content:
            # A stream that died before its first token leaves nothing worth
            # remembering; storing an empty assistant turn would replay as a
            # blank bubble forever.
            return
        self._conversations.append(
            user_id,
            ConversationTurn(
                conversation_id=conversation_id, role=role, content=content
            ),
        )

    def rename(
        self, *, user_id: UUID, conversation_id: UUID, title: str
    ) -> Conversation:
        """Replace the list name. Empty is refused: a thread without a title
        cannot be found again in the rail."""
        conversation = self.get(user_id=user_id, conversation_id=conversation_id)
        conversation.title = " ".join(title.split())
        if not conversation.title:
            raise ValueError("A conversation needs a title.")
        renamed = self._conversations.rename(user_id, conversation)
        if renamed is None:
            raise ConversationNotFound(str(conversation_id))
        return renamed

    def delete(self, *, user_id: UUID, conversation_id: UUID) -> None:
        if not self._conversations.delete(user_id, conversation_id):
            raise ConversationNotFound(str(conversation_id))

    def delete_for_workstation(self, *, user_id: UUID, workstation_id: UUID) -> None:
        self._conversations.delete_for_workstation(user_id, workstation_id)


__all__: Sequence[str] = ["ConversationNotFound", "ManageConversations"]
