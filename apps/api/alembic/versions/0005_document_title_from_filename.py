"""name documents after their uploaded file

Ingestion used to take the title from PDF metadata, falling back to the stem of
the stored path — which is `{uuid}.pdf`, so documents without a metadata title
ended up named after a random id. Titles now come from the upload name; this
backfills the rows that got a uuid.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_TITLE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE documents
               SET title = regexp_replace(filename, '\\.pdf$', '', 'i')
             WHERE title ~ :uuid_title
            """
        ).bindparams(uuid_title=UUID_TITLE)
    )


def downgrade() -> None:
    # The discarded titles are not recoverable, and the uuid form carried no
    # information worth restoring.
    pass
