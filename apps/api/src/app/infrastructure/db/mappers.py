"""Mappers between ORM models and domain entities."""

from app.domain.entities import Chunk, Conversation, Document, Message, Section
from app.domain.values.messages import Turn
from app.domain.values.status import DocumentStatus, MessageRole
from app.infrastructure.db.models import (
    Chunk as ChunkORM,
    Conversation as ConversationORM,
    Document as DocumentORM,
    Message as MessageORM,
    Section as SectionORM,
)


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
        orm_row.updated_at = entity.updated_at
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
            created_at=entity.created_at,
            updated_at=entity.updated_at,
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


def orm_message_to_entity(row: MessageORM) -> Message:
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
        )


def orm_turn_to_entity(role: str, content: str) -> Turn:
    """Map ORM message row pair to domain Turn entity."""
    return Turn(role=MessageRole(role), content=content)
