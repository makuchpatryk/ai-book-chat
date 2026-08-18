"""Domain layer — pure business logic and entities."""

from app.domain.entities import Chunk, Conversation, Document, Message, RetryVerdict, Section
from app.domain.events import AnswerCompleted, AnswerEvent, AnswerFailed, SourcesFound, TokenProduced
from app.domain.values import (
    ChatPolicy,
    Citation,
    DocumentStatus,
    MessageRole,
    RetrievalPolicy,
    RetrievedChunk,
    ScoredChunk,
    Turn,
)

__all__ = [
    "AnswerCompleted",
    "AnswerEvent",
    "AnswerFailed",
    "ChatPolicy",
    "Chunk",
    "Citation",
    "Conversation",
    "Document",
    "DocumentStatus",
    "Message",
    "MessageRole",
    "RetrievalPolicy",
    "RetrievedChunk",
    "RetryVerdict",
    "ScoredChunk",
    "Section",
    "SourcesFound",
    "TokenProduced",
    "Turn",
]
