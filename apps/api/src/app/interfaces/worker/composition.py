"""Worker-side composition (async UoW factory + use cases)."""

from app.application.usecases.ingestion.ingest_document import IngestDocument
from app.infrastructure.config.settings import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWorkFactory
from app.infrastructure.pdf.pymupdf_extractor import PyMuPdfExtractor
from app.infrastructure.tokenizer import TiktokenCounter
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


def get_ingest_document() -> IngestDocument:
    """Factory for IngestDocument use case (worker-scoped)."""
    settings = get_settings()

    # Per-task async engine with NullPool to avoid event-loop issues
    engine = create_async_engine(
        settings.database_url,
        poolclass=__import__("sqlalchemy.pool").NullPool,
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    uow_factory = SqlAlchemyUnitOfWorkFactory(sessionmaker)

    pdf_extractor = PyMuPdfExtractor()
    token_counter = TiktokenCounter()

    return IngestDocument(
        uow_factory,
        pdf_extractor,
        token_counter,
        settings.chunk_target_tokens,
        settings.chunk_overlap_ratio,
    )
