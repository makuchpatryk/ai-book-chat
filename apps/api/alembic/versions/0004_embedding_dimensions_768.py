"""narrow chunks.embedding to 768 dimensions

Local `nomic-embed-text` answers 768-wide where OpenAI's `text-embedding-3-small`
default was 1536, and pgvector columns are fixed width.

This migration DISCARDS every existing embedding: there is no cast from a
1536-dimensional vector to a 768-dimensional one, and re-embedding is the only
way to refill the column. Chunks and sections go with it, since a chunk without
its vector is unusable — documents and their uploaded files survive, so the fix
is to re-run ingestion. The HNSW index is dropped and rebuilt because it is
built against the column's width.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HNSW_INDEX = "ix_chunks_embedding_hnsw"


def _resize(dimensions: int) -> None:
    op.drop_index(HNSW_INDEX, table_name="chunks", postgresql_using="hnsw")
    # Cascades to message_sources; documents keep their rows and their files.
    op.execute(sa.text("DELETE FROM chunks"))
    op.alter_column(
        "chunks",
        "embedding",
        type_=pgvector.sqlalchemy.Vector(dim=dimensions),
        existing_nullable=False,
    )
    op.create_index(
        HNSW_INDEX,
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def upgrade() -> None:
    _resize(768)


def downgrade() -> None:
    _resize(1536)
