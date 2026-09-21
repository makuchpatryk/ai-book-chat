"""Add embedding progress counters to documents.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("embedded_chunks", sa.Integer, nullable=True))
    op.add_column("documents", sa.Column("total_chunks", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "total_chunks")
    op.drop_column("documents", "embedded_chunks")
