"""Mappers between ORM models and domain entities."""

from datetime import UTC, datetime

from app.domain.entities import Chunk, Conversation, Document, Message, Section
from app.domain.values.messages import Turn
from app.domain.values.overview import OverviewStatus
from app.domain.values.retrieval import Citation
from app.domain.values.status import DocumentStatus, MessageRole
from app.infrastructure.db.models import (
    Chunk as ChunkORM,
)
from app.infrastructure.db.models import (
    Conversation as ConversationORM,
)
from app.infrastructure.db.models import (
    Document as DocumentORM,
)
from app.infrastructure.db.models import (
    Message as MessageORM,
)
from app.infrastructure.db.models import (
    MessageSource as MessageSourceORM,
)
from app.infrastructure.db.models import (
    Section as SectionORM,
)


def _as_utc(value: datetime) -> datetime:
    """Domain timestamps are naive UTC; asyncpg would read a naive value as local time."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def orm_document_to_entity(row: DocumentORM) -> Document:
    """Map ORM Document row to domain Document entity."""
    return Document(
        id=row.id,
        filename=row.filename,
        title=row.title,
        status=DocumentStatus(row.status),
        file_path=row.file_path,
        content_hash=row.content_hash,
        page_count=row.page_count,
        error_message=row.error_message,
        chunking_strategy=row.chunking_strategy,
        created_at=row.created_at,
        updated_at=row.updated_at,
        author=row.author,
        summary=row.summary,
        language=row.language,
        doc_type=row.doc_type,
        topics=row.topics or [],
        description_sections=row.description_sections or [],
        overview_status=OverviewStatus(row.overview_status) if row.overview_status else None,
        cover_mime=row.cover_mime,
    )


def entity_document_to_orm(entity: Document, orm_row: DocumentORM | None = None) -> DocumentORM:
    """Map domain Document entity to ORM Document row."""
    if orm_row:
        orm_row.filename = entity.filename
        orm_row.title = entity.title
        orm_row.status = entity.status
        orm_row.file_path = entity.file_path
        orm_row.content_hash = entity.content_hash
        orm_row.page_count = entity.page_count
        orm_row.error_message = entity.error_message
        orm_row.chunking_strategy = entity.chunking_strategy
        orm_row.author = entity.author
        orm_row.summary = entity.summary
        orm_row.language = entity.language
        orm_row.doc_type = entity.doc_type
        orm_row.topics = entity.topics or None
        orm_row.description_sections = entity.description_sections or None
        orm_row.overview_status = entity.overview_status.value if entity.overview_status else None
        orm_row.cover_mime = entity.cover_mime
        orm_row.updated_at = _as_utc(entity.updated_at)
        return orm_row
    else:
        return DocumentORM(
            id=entity.id,
            filename=entity.filename,
            title=entity.title,
            status=entity.status,
            file_path=entity.file_path,
            content_hash=entity.content_hash,
            page_count=entity.page_count,
            error_message=entity.error_message,
            chunking_strategy=entity.chunking_strategy,
            author=entity.author,
            summary=entity.summary,
            language=entity.language,
            doc_type=entity.doc_type,
            topics=entity.topics or None,
            description_sections=entity.description_sections or None,
            overview_status=entity.overview_status.value if entity.overview_status else None,
            cover_mime=entity.cover_mime,
            created_at=_as_utc(entity.created_at),
            updated_at=_as_utc(entity.updated_at),
        )


def orm_section_to_entity(row: SectionORM) -> Section:
    """Map ORM Section row to domain Section entity."""
    return Section(
        id=row.id,
        document_id=row.document_id,
        title=row.title,
        order_index=row.order_index,
        start_page=row.start_page,
        end_page=row.end_page,
    )


def orm_chunk_to_entity(row: ChunkORM) -> Chunk:
    """Map ORM Chunk row to domain Chunk entity."""
    return Chunk(
        id=row.id,
        document_id=row.document_id,
        section_id=row.section_id,
        content=row.content,
        page_start=row.page_start,
        page_end=row.page_end,
        token_count=row.token_count,
        order_index=row.order_index,
    )


def orm_conversation_to_entity(row: ConversationORM) -> Conversation:
    """Map ORM Conversation row to domain Conversation entity."""
    return Conversation(
        id=row.id,
        document_id=row.document_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def entity_conversation_to_orm(
    entity: Conversation, orm_row: ConversationORM | None = None
) -> ConversationORM:
    """Map domain Conversation entity to ORM Conversation row."""
    if orm_row:
        orm_row.title = entity.title
        orm_row.updated_at = entity.updated_at
        return orm_row
    else:
        return ConversationORM(
            id=entity.id,
            document_id=entity.document_id,
            title=entity.title,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


def orm_message_to_entity(row: MessageORM, sources: list[Citation] | None = None) -> Message:
    """Map ORM Message row to domain Message entity."""
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        content=row.content,
        order_index=row.order_index,
        grounded=row.grounded,
        truncated=row.truncated,
        created_at=row.created_at,
        sources=sources or [],
    )


def orm_source_to_citation(row: MessageSourceORM) -> Citation:
    """Map ORM MessageSource row (with chunk and section loaded) to a Citation."""
    chunk = row.chunk
    return Citation(
        chunk_id=chunk.id,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        score=row.score,
        section_title=chunk.section.title if chunk.section else None,
        snippet=chunk.content[:240],
    )


def entity_message_to_orm(entity: Message, orm_row: MessageORM | None = None) -> MessageORM:
    """Map domain Message entity to ORM Message row."""
    if orm_row:
        orm_row.role = entity.role
        orm_row.content = entity.content
        orm_row.grounded = entity.grounded
        orm_row.truncated = entity.truncated
        return orm_row
    else:
        return MessageORM(
            id=entity.id,
            conversation_id=entity.conversation_id,
            role=entity.role,
            content=entity.content,
            order_index=entity.order_index,
            grounded=entity.grounded,
            truncated=entity.truncated,
            created_at=entity.created_at,
            sources=[
                MessageSourceORM(chunk_id=c.chunk_id, score=c.score, rank=rank)
                for rank, c in enumerate(entity.sources)
            ],
        )


def orm_turn_to_entity(role: str, content: str) -> Turn:
    """Map ORM message row pair to domain Turn entity."""
    return Turn(role=MessageRole(role), content=content)
