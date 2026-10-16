"""Application settings, loaded from environment variables and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# app/core/config.py -> repository root (papertrail-ai/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env lives in the repository root, whatever directory the backend is started from.
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PaperTrail AI"
    log_level: str = "INFO"

    postgres_user: str = "papertrail"
    postgres_password: str = "papertrail"
    postgres_db: str = "papertrail"
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    arxiv_api_url: str = "https://export.arxiv.org/api/query"
    arxiv_timeout_seconds: float = 15.0

    pdf_timeout_seconds: float = 60.0
    pdf_max_bytes: int = 30_000_000

    # ~150 words is roughly 200 tokens: small enough for typical embedding models,
    # big enough to hold a complete thought. The overlap keeps sentences that straddle
    # a boundary findable from both sides.
    chunk_size_words: int = Field(default=150, gt=0)
    chunk_overlap_words: int = Field(default=30, ge=0)

    # Local ONNX export of BAAI/bge-small-en-v1.5 (MIT). See README "Embedding model".
    embedding_model_dir: Path = PROJECT_ROOT / "models" / "bge-small-en-v1.5"
    embedding_batch_size: int = Field(default=32, gt=0)

    # Passages scoring below this cosine similarity are not used as evidence; if none
    # remain, /ask abstains. Calibrated by hand on a few queries (see README, "Abstention").
    rag_min_score: float = Field(default=0.70, ge=-1.0, le=1.0)

    # Which language model generates answers. "none" = answer generation disabled.
    llm_provider: Literal["none", "ollama"] = "none"
    llm_timeout_seconds: float = 120.0
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> "Settings":
        if self.chunk_overlap_words >= self.chunk_size_words:
            raise ValueError("chunk_overlap_words must be smaller than chunk_size_words")
        return self

    @property
    def database_url(self) -> URL:
        """SQLAlchemy URL for PostgreSQL using the psycopg (v3) driver.

        Built with URL.create so special characters in the password are escaped safely.
        """
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
