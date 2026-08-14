"""Migrations must round-trip on a scratch database, not the dev one."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.config import get_settings

API_ROOT = Path(__file__).resolve().parents[1]
SCRATCH_DB = "bookchat_migrations_test"


def _admin_engine() -> sa.Engine:
    url = sa.make_url(get_settings().sync_database_url).set(database="postgres")
    return sa.create_engine(url, isolation_level="AUTOCOMMIT")


@pytest.fixture
def scratch_db_url() -> Iterator[str]:
    try:
        admin = _admin_engine()
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
            conn.execute(sa.text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    except sa.exc.OperationalError:
        pytest.skip("postgres unreachable")

    url = sa.make_url(get_settings().sync_database_url).set(database=SCRATCH_DB)
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def test_upgrade_downgrade_upgrade(scratch_db_url: str) -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", scratch_db_url)

    command.upgrade(config, "head")
    engine = sa.create_engine(scratch_db_url)
    with engine.connect() as conn:
        extension = conn.execute(
            sa.text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
        hnsw_index = conn.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'chunks' AND indexname = 'ix_chunks_embedding_hnsw'"
            )
        ).scalar_one_or_none()
    assert extension == "vector"
    assert hnsw_index is not None
    assert "USING hnsw" in hnsw_index
    assert "vector_cosine_ops" in hnsw_index

    command.downgrade(config, "base")
    with engine.connect() as conn:
        extension = conn.execute(
            sa.text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    assert extension is None

    command.upgrade(config, "head")
    engine.dispose()
