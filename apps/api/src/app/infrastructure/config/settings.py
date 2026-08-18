"""Application settings.

Values come from environment variables, falling back to the repo-root `.env`.
Environment variables win over the dotenv file, which is what lets
docker-compose point `api`/`worker` at the in-network `postgres`/`redis`
hostnames while host tooling keeps using `localhost` from `.env`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path | None:
    """Walk up from this file looking for a `.env` (repo root on the host).

    Returns None inside the container, where the app lives at /app and config
    arrives purely through environment variables.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


ENV_FILE = _find_env_file()
PROJECT_ROOT = ENV_FILE.parent if ENV_FILE else Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://bookchat:bookchat@localhost:5432/bookchat"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # App
    upload_dir: Path = PROJECT_ROOT / "uploads"
    max_upload_mb: int = 50
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    # LLM — chat, rewrite and re-rank, over any OpenAI-compatible endpoint.
    # Default points at Groq's free tier; swap the base URL for another gateway
    # (the HF router, OpenAI itself, a local vLLM) without touching code.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_token: str | None = None  # unset ⇒ the deterministic Fake* adapters

    # Embeddings — local Ollama, or the deterministic fake when it is unreachable
    embedding_dimensions: int = 768  # width of chunks.embedding; see EMBEDDING_DIMENSIONS
    embedding_batch_size: int = 100
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"  # 768d, matches the column

    # Ingestion — chunking
    chunk_target_tokens: int = 600
    chunk_overlap_ratio: float = 0.15

    # Retrieval — re-ranking
    rerank_model: str = "openai/gpt-oss-120b"
    retrieval_top_k: int = 30
    rerank_top_n: int = 8
    rerank_min_score: int = 5
    rerank_max_tokens: int = 2048

    # Chat — generation and query rewriting
    chat_model: str = "openai/gpt-oss-120b"
    chat_rewrite_model: str = "openai/gpt-oss-20b"
    chat_max_tokens: int = 2048
    chat_history_turns: int = 6
    chat_heartbeat_seconds: float = 15.0

    # Retry and recovery
    stuck_after_minutes: int = 30
    retrieval_max_distance: float = 0.75

    @property
    def sync_database_url(self) -> str:
        """Same database, psycopg driver — used by Celery tasks and Alembic."""
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "+psycopg")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
