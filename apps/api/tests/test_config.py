from app.config import Settings


def test_sync_url_derivation_from_asyncpg() -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/db")

    assert settings.sync_database_url == "postgresql+psycopg://u:p@localhost:5432/db"


def test_sync_url_derivation_from_bare_scheme() -> None:
    settings = Settings(database_url="postgresql://u:p@localhost:5432/db")

    assert settings.sync_database_url == "postgresql+psycopg://u:p@localhost:5432/db"


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins="http://localhost:5173, http://127.0.0.1:5173 ,")

    assert settings.cors_origin_list == ["http://localhost:5173", "http://127.0.0.1:5173"]
