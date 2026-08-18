"""Re-exports from new interfaces.http.schemas location for backwards compatibility."""

from app.interfaces.http.schemas.chat import (
    ConversationRead,
    DonePayload,
    ErrorPayload,
    MessageRead,
    SendMessageRequest,
    SourceRead,
    SourcesPayload,
    TokenPayload,
)
from app.interfaces.http.schemas.documents import DocumentDetail, DocumentRead
from app.interfaces.http.schemas.search import SearchResponse

__all__ = [
    "ConversationRead",
    "DonePayload",
    "DocumentDetail",
    "DocumentRead",
    "ErrorPayload",
    "MessageRead",
    "SearchResponse",
    "SendMessageRequest",
    "SourceRead",
    "SourcesPayload",
    "TokenPayload",
]
