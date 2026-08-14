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


def test_retrieval_defaults() -> None:
    settings = Settings()

    assert settings.rerank_provider == "anthropic"
    assert settings.rerank_model == "claude-haiku-4-5"
    assert settings.retrieval_top_k == 30
    assert settings.rerank_top_n == 8
    assert settings.rerank_min_score == 5
    assert settings.rerank_max_tokens == 2048
    assert settings.ollama_base_url == "http://localhost:11434"


def test_chat_defaults() -> None:
    settings = Settings()

    assert settings.chat_provider == "anthropic"
    assert settings.chat_model == "claude-sonnet-5"
    assert settings.chat_rewrite_model == "claude-haiku-4-5"
    assert settings.chat_max_tokens == 2048
    assert settings.chat_history_turns == 6
    assert settings.chat_heartbeat_seconds == 15.0
