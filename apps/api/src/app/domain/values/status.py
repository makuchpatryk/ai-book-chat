"""Document and message statuses."""

import enum


class DocumentStatus(enum.StrEnum):
    """Lifecycle of a document, driven by the ingestion pipeline."""

    PENDING = "PENDING"
    PARSING = "PARSING"
    EMBEDDING = "EMBEDDING"
    READY = "READY"
    FAILED = "FAILED"


class MessageRole(enum.StrEnum):
    """Role of a message in a conversation."""

    USER = "user"
    ASSISTANT = "assistant"
