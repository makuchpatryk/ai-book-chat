"""ORM models.

Every model must be imported here: `alembic/env.py` imports this module so
autogenerate sees the full `Base.metadata`.

Phase 2 adds the ingestion schema; Phase 4 adds conversations/messages.
"""

from app.db.models.chunk import Chunk
from app.db.models.conversation import Conversation
from app.db.models.document import Document, DocumentStatus
from app.db.models.message import Message, MessageRole
from app.db.models.message_source import MessageSource
from app.db.models.section import Section

__all__ = [
    "Chunk",
    "Conversation",
    "Document",
    "DocumentStatus",
    "Message",
    "MessageRole",
    "MessageSource",
    "Section",
]
