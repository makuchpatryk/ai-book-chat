"""SQLAlchemy implementations of repository ports."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.domain.entities import Chunk, Conversation, Document, Message, Section
from app.domain.ports.repositories import (
    ChunkRepository,
    ConversationRepository,
    DocumentRepository,
    MessageRepository,
    SectionRepository,
)
from app.domain.values.messages import Turn
from app.domain.values.retrieval import RetrievedChunk
from app.infrastructure.db.mappers import (
    orm_chunk_to_entity,
    orm_conversation_to_entity,
    orm_document_to_entity,
    orm_message_to_entity,
    orm_section_to_entity,
    orm_turn_to_entity,
)
from app.infrastructure.db.models import (
    Chunk as ChunkORM,
    Conversation as ConversationORM,
    Document as DocumentORM,
    Message as MessageORM,
    Section as SectionORM,
)


class SqlDocumentRepository(DocumentRepository):
    """SQLAlchemy implementation of DocumentRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, document_id: UUID) -> Document | None:
        result = await self.session.execute(
            select(DocumentORM).where(DocumentORM.id == document_id)
        )
        row = result.scalar_one_or_none()
        return orm_document_to_entity(row) if row else None

    async def get_with_sections(self, document_id: UUID) -> tuple[Document, list[Section]] | None:
        result = await self.session.execute(
            select(DocumentORM)
            .where(DocumentORM.id == document_id)
            .options(joinedload(DocumentORM.sections))
        )
        row = result.unique().scalar_one_or_none()
        if not row:
            return None
        doc = orm_document_to_entity(row)
        sections = [orm_section_to_entity(s) for s in row.sections]
        return doc, sections

    async def find_by_hash(self, content_hash: str) -> Document | None:
        result = await self.session.execute(
            select(DocumentORM).where(DocumentORM.content_hash == content_hash)
        )
        row = result.scalar_one_or_none()
        return orm_document_to_entity(row) if row else None

    async def list_newest_first(self) -> list[Document]:
        result = await self.session.execute(
            select(DocumentORM).order_by(DocumentORM.created_at.desc())
        )
        rows = result.scalars().all()
        return [orm_document_to_entity(row) for row in rows]

    async def add(self, document: Document) -> None:
        from app.infrastructure.db.mappers import entity_document_to_orm
        orm_row = entity_document_to_orm(document)
        self.session.add(orm_row)
        await self.session.flush()

    async def save(self, document: Document) -> None:
        from app.infrastructure.db.mappers import entity_document_to_orm
        result = await self.session.execute(
            select(DocumentORM).where(DocumentORM.id == document.id)
        )
        orm_row = result.scalar_one_or_none()
        if orm_row:
            entity_document_to_orm(document, orm_row)
            await self.session.flush()

    async def delete(self, document_id: UUID) -> bool:
        result = await self.session.execute(
            select(DocumentORM).where(DocumentORM.id == document_id)
        )
        row = result.scalar_one_or_none()
        if row:
            await self.session.delete(row)
            await self.session.flush()
            return True
        return False

    async def clear_derived(self, document_id: UUID) -> None:
        await self.session.execute(
            delete(SectionORM).where(SectionORM.document_id == document_id)
        )
        await self.session.flush()


class SqlSectionRepository(SectionRepository):
    """SQLAlchemy implementation of SectionRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, section: Section) -> None:
        from app.infrastructure.db.mappers import orm_section_to_entity
        orm_row = SectionORM(
            id=section.id,
            document_id=section.document_id,
            title=section.title,
            order_index=section.order_index,
            start_page=section.start_page,
            end_page=section.end_page,
        )
        self.session.add(orm_row)
        await self.session.flush()

    async def add_many(self, sections: list[Section]) -> None:
        orm_rows = [
            SectionORM(
                id=s.id,
                document_id=s.document_id,
                title=s.title,
                order_index=s.order_index,
                start_page=s.start_page,
                end_page=s.end_page,
            )
            for s in sections
        ]
        self.session.add_all(orm_rows)
        await self.session.flush()


class SqlChunkRepository(ChunkRepository):
    """SQLAlchemy implementation of ChunkRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_similar(
        self, document_id: UUID, vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        from pgvector.sqlalchemy import Vector
        result = await self.session.execute(
            select(
                ChunkORM.id,
                ChunkORM.content,
                ChunkORM.page_start,
                ChunkORM.page_end,
                SectionORM.title,
                ChunkORM.embedding.cosine_distance(vector).label("distance"),
            )
            .select_from(ChunkORM)
            .join(SectionORM, ChunkORM.section_id == SectionORM.id)
            .where(ChunkORM.document_id == document_id)
            .order_by("distance")
            .limit(limit)
        )
        chunks = []
        for row in result:
            chunks.append(
                RetrievedChunk(
                    chunk_id=row.id,
                    distance=row.distance,
                    content=row.content,
                    page_start=row.page_start,
                    page_end=row.page_end,
                    section_title=row.title,
                )
            )
        return chunks

    async def replace_for_document(
        self, document_id: UUID, sections: list[Section], chunks: list[Chunk]
    ) -> None:
        await self.session.execute(
            delete(SectionORM).where(SectionORM.document_id == document_id)
        )
        orm_sections = [
            SectionORM(
                id=s.id,
                document_id=s.document_id,
                title=s.title,
                order_index=s.order_index,
                start_page=s.start_page,
                end_page=s.end_page,
            )
            for s in sections
        ]
        self.session.add_all(orm_sections)
        await self.session.flush()

        orm_chunks = [
            ChunkORM(
                id=c.id,
                document_id=c.document_id,
                section_id=c.section_id,
                content=c.content,
                page_start=c.page_start,
                page_end=c.page_end,
                token_count=c.token_count,
                order_index=c.order_index,
            )
            for c in chunks
        ]
        self.session.add_all(orm_chunks)
        await self.session.flush()

    async def add_many(self, chunks: list[Chunk]) -> None:
        orm_rows = [
            ChunkORM(
                id=c.id,
                document_id=c.document_id,
                section_id=c.section_id,
                content=c.content,
                page_start=c.page_start,
                page_end=c.page_end,
                token_count=c.token_count,
                order_index=c.order_index,
            )
            for c in chunks
        ]
        self.session.add_all(orm_rows)
        await self.session.flush()


class SqlConversationRepository(ConversationRepository):
    """SQLAlchemy implementation of ConversationRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, conversation_id: UUID) -> Conversation | None:
        result = await self.session.execute(
            select(ConversationORM).where(ConversationORM.id == conversation_id)
        )
        row = result.scalar_one_or_none()
        return orm_conversation_to_entity(row) if row else None

    async def list_for_document(self, document_id: UUID) -> list[Conversation]:
        result = await self.session.execute(
            select(ConversationORM)
            .where(ConversationORM.document_id == document_id)
            .order_by(ConversationORM.created_at.desc())
        )
        rows = result.scalars().all()
        return [orm_conversation_to_entity(row) for row in rows]

    async def add(self, conversation: Conversation) -> None:
        from app.infrastructure.db.mappers import entity_conversation_to_orm
        orm_row = entity_conversation_to_orm(conversation)
        self.session.add(orm_row)
        await self.session.flush()

    async def delete(self, conversation_id: UUID) -> bool:
        result = await self.session.execute(
            select(ConversationORM).where(ConversationORM.id == conversation_id)
        )
        row = result.scalar_one_or_none()
        if row:
            await self.session.delete(row)
            await self.session.flush()
            return True
        return False


class SqlMessageRepository(MessageRepository):
    """SQLAlchemy implementation of MessageRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def recent_turns(self, conversation_id: UUID, limit: int) -> list[Turn]:
        result = await self.session.execute(
            select(MessageORM.role, MessageORM.content)
            .where(MessageORM.conversation_id == conversation_id)
            .order_by(MessageORM.order_index.desc())
            .limit(limit * 2)
        )
        messages = result.all()
        return [orm_turn_to_entity(role, content) for role, content in reversed(messages)]

    async def next_order_index(self, conversation_id: UUID) -> int:
        result = await self.session.execute(
            select(MessageORM)
            .where(MessageORM.conversation_id == conversation_id)
            .order_by(MessageORM.order_index.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()
        return (last.order_index + 1) if last else 0

    async def list_with_citations(self, conversation_id: UUID) -> list[Message]:
        result = await self.session.execute(
            select(MessageORM)
            .where(MessageORM.conversation_id == conversation_id)
            .order_by(MessageORM.order_index)
        )
        rows = result.scalars().all()
        return [orm_message_to_entity(row) for row in rows]

    async def add(self, message: Message) -> None:
        from app.infrastructure.db.mappers import entity_message_to_orm
        orm_row = entity_message_to_orm(message)
        self.session.add(orm_row)
        await self.session.flush()

    async def save(self, message: Message) -> None:
        from app.infrastructure.db.mappers import entity_message_to_orm
        result = await self.session.execute(
            select(MessageORM).where(MessageORM.id == message.id)
        )
        orm_row = result.scalar_one_or_none()
        if orm_row:
            entity_message_to_orm(message, orm_row)
            await self.session.flush()
