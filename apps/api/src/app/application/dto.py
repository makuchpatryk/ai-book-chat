"""Application-level commands and results (dataclasses, not pydantic)."""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class CreateConversationCommand:
    """Create a new conversation for a document."""

    document_id: UUID


@dataclass
class ConversationResult:
    """Conversation read result."""

    id: UUID
    title: str | None
    created_at: str


@dataclass
class ListConversationsCommand:
    """List conversations for a document."""

    document_id: UUID


@dataclass
class AskQuestionCommand:
    """Ask a question in a conversation."""

    conversation_id: UUID
    question: str


@dataclass
class GetMessagesCommand:
    """Get all messages in a conversation."""

    conversation_id: UUID


@dataclass
class DeleteConversationCommand:
    """Delete a conversation."""

    conversation_id: UUID