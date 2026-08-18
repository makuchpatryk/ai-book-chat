"""SQLAlchemy implementation of the unit of work pattern."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ports.repositories import (
    ChunkRepository,
    ConversationRepository,
    DocumentRepository,
    MessageRepository,
    SectionRepository,
)
from app.domain.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.infrastructure.db.repositories import (
    SqlChunkRepository,
    SqlConversationRepository,
    SqlDocumentRepository,
    SqlMessageRepository,
    SqlSectionRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """SQLAlchemy implementation of UnitOfWork."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.documents = SqlDocumentRepository(session)
        self.sections = SqlSectionRepository(session)
        self.chunks = SqlChunkRepository(session)
        self.conversations = SqlConversationRepository(session)
        self.messages = SqlMessageRepository(session)

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            await self.rollback()
        else:
            await self.commit()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


class SqlAlchemyUnitOfWorkFactory(UnitOfWorkFactory):
    """Factory for creating SqlAlchemyUnitOfWork instances."""

    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    def __call__(self) -> SqlAlchemyUnitOfWork:
        session = self.sessionmaker()
        return SqlAlchemyUnitOfWork(session)
