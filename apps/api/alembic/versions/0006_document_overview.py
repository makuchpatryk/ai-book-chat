"""Add document overview fields.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("author", sa.String(512), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("summary", sa.Text, nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("language", sa.String(16), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("doc_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("topics", sa.ARRAY(sa.String(64)), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("description_sections", sa.JSON, nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("overview_status", sa.String(16), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("cover_image", sa.LargeBinary, nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("cover_mime", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "cover_mime")
    op.drop_column("documents", "cover_image")
    op.drop_column("documents", "overview_status")
    op.drop_column("documents", "description_sections")
    op.drop_column("documents", "topics")
    op.drop_column("documents", "doc_type")
    op.drop_column("documents", "language")
    op.drop_column("documents", "summary")
    op.drop_column("documents", "author")
