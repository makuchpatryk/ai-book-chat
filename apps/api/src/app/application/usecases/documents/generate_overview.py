"""Use case: generate document overview from sampled text."""

import logging
from uuid import UUID

from app.domain.entities import Chunk
from app.domain.ports.llm import DocumentDescriber
from app.domain.ports.storage import PdfExtractor
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.overview import DocumentOverview, OverviewStatus
from app.domain.values.status import DocumentStatus

logger = logging.getLogger(__name__)

COVER_WIDTH_PX = 400
DESCRIBE_ATTEMPTS = 2  # one retry when the model returns unusable JSON
CHUNK_SEPARATOR = "\n\n---\n\n"


def sample_chunks(chunks: list[Chunk], max_tokens: int) -> str:
    """Join evenly-spaced chunks, staying within `max_tokens` (at least one chunk)."""
    if not chunks:
        return ""

    total = sum(c.token_count for c in chunks)
    if total <= max_tokens:
        picked = chunks
    else:
        average = total / len(chunks)
        count = max(1, min(len(chunks), int(max_tokens // average)))
        picked = [chunks[i * len(chunks) // count] for i in range(count)]

    kept: list[str] = []
    used = 0
    for chunk in picked:
        if kept and used + chunk.token_count > max_tokens:
            break
        kept.append(chunk.content)
        used += chunk.token_count
    return CHUNK_SEPARATOR.join(kept)


class GenerateDocumentOverview:
    """Use case: generate document overview from sampled content. Never raises."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        describer: DocumentDescriber,
        pdf_extractor: PdfExtractor,
        max_input_tokens: int,
    ):
        self.uow_factory = uow_factory
        self.describer = describer
        self.pdf_extractor = pdf_extractor
        self.max_input_tokens = max_input_tokens

    async def execute(self, document_id: UUID) -> bool:
        """Generate overview for a document. Returns True if it was applied."""
        async with self.uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                logger.warning(f"document {document_id} not found")
                return False

            if document.status != DocumentStatus.READY:
                logger.warning(f"document {document_id} not READY: {document.status}")
                return False

            if not document.has_cover:
                try:
                    cover = self.pdf_extractor.render_cover(
                        document.file_path, width_px=COVER_WIDTH_PX
                    )
                except Exception as e:
                    logger.warning(f"failed to render cover for {document_id}: {e}")
                    cover = None
                if cover:
                    await uow.documents.set_cover(document_id, cover.data, cover.mime_type)
                    document.cover_mime = cover.mime_type

            chunks = await uow.chunks.list_for_document(document_id)
            if not chunks:
                logger.warning(f"no chunks for {document_id}")
                document.mark_overview_failed()
                await uow.documents.save(document)
                await uow.commit()
                return False

            detail = await uow.documents.get_with_sections(document_id)
            section_titles = [s.title for s in detail[1]] if detail else []

            overview = await self._describe(
                document.title,
                document.author,
                section_titles,
                sample_chunks(chunks, self.max_input_tokens),
            )
            if overview is None:
                document.mark_overview_failed()
            else:
                document.apply_overview(overview)

            await uow.documents.save(document)
            await uow.commit()
            return document.overview_status == OverviewStatus.READY

    async def _describe(
        self,
        title: str,
        author: str | None,
        section_titles: list[str],
        sample_text: str,
    ) -> DocumentOverview | None:
        for attempt in range(1, DESCRIBE_ATTEMPTS + 1):
            try:
                return await self.describer.describe(title, author, section_titles, sample_text)
            except ValueError as e:
                logger.warning(f"describer returned invalid output (attempt {attempt}): {e}")
            except Exception as e:
                logger.exception(f"describer failed: {e}")
                return None
        return None
