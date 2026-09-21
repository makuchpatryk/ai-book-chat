"""Worker-side composition (async UoW factory + use cases)."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.usecases.documents.generate_overview import GenerateDocumentOverview
from app.application.usecases.ingestion.ingest_document import IngestDocument
from app.infrastructure.config.settings import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWorkFactory
from app.infrastructure.embeddings.adapters import build_embedder
from app.infrastructure.llm.adapters import build_describer
from app.infrastructure.pdf.pymupdf_extractor import PyMuPdfExtractor
from app.infrastructure.tokenizer import TiktokenCounter


def get_ingest_document() -> IngestDocument:
    """Factory for IngestDocument use case (worker-scoped)."""
    from app.infrastructure.queue.celery_queue import CeleryIngestionQueue

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
    queue = CeleryIngestionQueue()

    return IngestDocument(
        uow_factory,
        pdf_extractor,
        token_counter,
        build_embedder(settings),
        settings.embedding_batch_size,
        settings.chunk_target_tokens,
        settings.chunk_overlap_ratio,
        queue=queue,
    )


def get_generate_overview() -> GenerateDocumentOverview:
    """Factory for GenerateDocumentOverview use case (worker-scoped)."""
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        poolclass=__import__("sqlalchemy.pool").NullPool,
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    uow_factory = SqlAlchemyUnitOfWorkFactory(sessionmaker)

    pdf_extractor = PyMuPdfExtractor()
    describer = build_describer(settings)

    return GenerateDocumentOverview(
        uow_factory,
        describer,
        pdf_extractor,
        settings.describe_max_input_tokens,
    )
