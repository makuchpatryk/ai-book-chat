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

    # Providers
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_api_key: str | None = None  # Shared key for re-ranking and generation
    hf_token: str | None = None  # Hugging Face Inference Providers; falls back to llm_api_key
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_bill_to: str | None = None  # X-HF-Bill-To: charge an org instead of the user

    # Ingestion — embeddings
    embedding_provider: str = "openai"  # openai | huggingface
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100
    hf_embedding_model: str = "intfloat/multilingual-e5-large-instruct"
    hf_embedding_query_prefix: str = "query: "
    hf_embedding_passage_prefix: str = "passage: "

    # Ingestion — chunking
    chunk_target_tokens: int = 600
    chunk_overlap_ratio: float = 0.15

    # Retrieval — LLM provider and configuration
    rerank_provider: str = "huggingface"  # huggingface | anthropic | mistral | ollama
    rerank_model: str = "openai/gpt-oss-120b:cheapest"  # or claude-haiku-4-5, mistral-large, etc.
    retrieval_top_k: int = 30
    rerank_top_n: int = 8
    rerank_min_score: int = 5
    rerank_max_tokens: int = 2048
    ollama_base_url: str = "http://localhost:11434"

    # Chat — LLM provider and configuration
    chat_provider: str = "huggingface"  # huggingface | anthropic | mistral | ollama
    chat_model: str = "openai/gpt-oss-120b:cheapest"
    chat_rewrite_model: str = "openai/gpt-oss-20b:cheapest"
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
