"""quiz table

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        # Plain string, not a native enum — see Quiz ORM model for why.
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("questions", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_quizzes_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quizzes")),
    )
    op.create_index(
        op.f("ix_quizzes_document_id"), "quizzes", ["document_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_quizzes_document_id"), table_name="quizzes")
    op.drop_table("quizzes")
