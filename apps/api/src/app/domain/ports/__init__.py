"""Domain ports — interfaces for external systems."""

from app.domain.ports.llm import AnswerGenerator, Embedder, QueryRewriter, Reranker
from app.domain.ports.repositories import (
    ChunkRepository,
    ConversationRepository,
    DocumentRepository,
    MessageRepository,
    SectionRepository,
)
from app.domain.ports.storage import (
    Clock,
    FileStorage,
    IngestionQueue,
    PdfExtractor,
    StoredFile,
    TokenCounter,
)
from app.domain.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

__all__ = [
    "AnswerGenerator",
    "ChunkRepository",
    "Clock",
    "ConversationRepository",
    "DocumentRepository",
    "Embedder",
    "FileStorage",
    "IngestionQueue",
    "MessageRepository",
    "PdfExtractor",
    "QueryRewriter",
    "Reranker",
    "SectionRepository",
    "StoredFile",
    "TokenCounter",
    "UnitOfWork",
    "UnitOfWorkFactory",
]
