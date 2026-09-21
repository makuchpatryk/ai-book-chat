"""Ingest a document: extract, section, chunk, embed."""

import logging
from datetime import datetime
from uuid import UUID

from app.domain.entities import Chunk, Document, Section
from app.domain.ports.llm import Embedder
from app.domain.ports.storage import IngestionQueue, PdfExtractor, TokenCounter
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.services.chunking import PageText as ChunkingPageText
from app.domain.services.chunking import chunk_document
from app.domain.services.sections import detect_sections
from app.domain.values.status import DocumentStatus

logger = logging.getLogger(__name__)


class IngestDocument:
    """Use case: ingest document through parsing, extraction, embedding."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        pdf_extractor: PdfExtractor,
        token_counter: TokenCounter,
        embedder: Embedder,
        embedding_batch_size: int,
        chunk_target_tokens: int,
        chunk_overlap_ratio: float,
        queue: IngestionQueue | None = None,
    ):
        self.uow_factory = uow_factory
        self.pdf_extractor = pdf_extractor
        self.token_counter = token_counter
        self.embedder = embedder
        self.embedding_batch_size = embedding_batch_size
        self.chunk_target_tokens = chunk_target_tokens
        self.chunk_overlap_ratio = chunk_overlap_ratio
        self.queue = queue

    async def execute(self, document_id: UUID) -> Document:
        """Ingest document through full pipeline with transactional checkpoints."""
        async with self.uow_factory() as uow:
            # Load document
            document = await uow.documents.get(document_id)
            if document is None:
                raise ValueError(f"document {document_id} not found")

            # Step 1: Parse PDF (PENDING → PARSING)
            try:
                document.status = DocumentStatus.PARSING
                await uow.documents.save(document)
                await uow.commit()

                extracted = self.pdf_extractor.extract(document.file_path, document.filename)

                # Render cover (fail silently; cover is optional)
                try:
                    cover = self.pdf_extractor.render_cover(document.file_path, width_px=400)
                    if cover:
                        await uow.documents.set_cover(document.id, cover.data, cover.mime_type)
                        document.cover_mime = cover.mime_type
                        logger.info(f"rendered cover for {document.id}")
                except Exception as e:
                    logger.warning(f"failed to render cover for {document.id}: {e}")
            except Exception as e:
                document.mark_failed(f"parsing failed: {str(e)}")
                await uow.documents.save(document)
                await uow.commit()
                return document

            # Step 2: Detect sections (still PARSING)
            try:
                sections_list, strategy = detect_sections(
                    extracted.outline,
                    extracted.lines,
                    extracted.title,
                    extracted.page_count,
                )

                # Create Section entities
                sections = [
                    Section(
                        id=__import__("uuid").uuid4(),
                        document_id=document_id,
                        title=s.title,
                        order_index=s.order_index,
                        start_page=s.start_page,
                        end_page=s.end_page,
                    )
                    for s in sections_list
                ]
            except Exception as e:
                document.mark_failed(f"section detection failed: {str(e)}")
                await uow.documents.save(document)
                await uow.commit()
                return document

            # Step 3: Chunk document (still PARSING)
            try:
                # Convert ExtractedPdf pages to chunking format
                pages_for_chunking = [
                    ChunkingPageText(page_number=p.page_number, text=p.text)
                    for p in extracted.pages
                ]

                chunk_specs = chunk_document(
                    pages_for_chunking,
                    sections,
                    self.token_counter.encode,
                    self.token_counter.decode,
                    size=self.chunk_target_tokens,
                    overlap_ratio=self.chunk_overlap_ratio,
                )

                # Create Chunk entities
                chunks = [
                    Chunk(
                        id=__import__("uuid").uuid4(),
                        document_id=document_id,
                        section_id=sections[spec.section_order_index].id,
                        content=spec.content,
                        page_start=spec.page_start,
                        page_end=spec.page_end,
                        token_count=spec.token_count,
                        order_index=spec.order_index,
                    )
                    for spec in chunk_specs
                ]
            except Exception as e:
                document.mark_failed(f"chunking failed: {str(e)}")
                await uow.documents.save(document)
                await uow.commit()
                return document

            # Step 4: Embed chunks (PARSING → EMBEDDING)
            try:
                document.status = DocumentStatus.EMBEDDING
                await uow.documents.save(document)
                await uow.commit()

                batch = self.embedding_batch_size
                for start in range(0, len(chunks), batch):
                    group = chunks[start : start + batch]
                    vectors = await self.embedder.embed([c.content for c in group])
                    if len(vectors) != len(group):
                        raise ValueError(
                            f"embedder returned {len(vectors)} vectors for {len(group)} chunks"
                        )
                    for chunk, vector in zip(group, vectors):
                        chunk.embedding = vector
            except Exception as e:
                document.mark_failed(f"embedding failed: {str(e)}")
                await uow.documents.save(document)
                await uow.commit()
                return document

            # Step 5: Mark ready (EMBEDDING → READY)
            try:
                # Clear old overview on re-ingestion
                document.clear_derived()

                document.mark_ready(
                    extracted.page_count,
                    extracted.title,
                    strategy.value,
                    author=extracted.author,
                )
                if self.queue:
                    document.mark_overview_pending(datetime.utcnow())

                # Clear old sections/chunks if any
                await uow.documents.clear_derived(document_id)

                # Persist new sections and chunks in one transaction
                await uow.sections.add_many(sections)
                await uow.chunks.add_many(chunks)
                await uow.documents.save(document)
                await uow.commit()

                # Enqueue overview generation (after commit, safe to fail)
                if self.queue:
                    try:
                        await self.queue.enqueue_overview(document_id)
                        logger.info(f"enqueued overview for {document_id}")
                    except Exception as e:
                        logger.error(f"failed to enqueue overview for {document_id}: {e}")
            except Exception as e:
                document.mark_failed(f"persistence failed: {str(e)}")
                await uow.documents.save(document)
                await uow.commit()
                return document

            return document
