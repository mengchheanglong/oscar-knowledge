from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KNOWLEDGE_", env_file=".env", env_file_encoding="utf-8-sig", extra="ignore"
    )
    database_url: str = (
        "postgresql+psycopg://knowledge:local_knowledge_only@127.0.0.1:43114/knowledge"
    )
    service_token: SecretStr = SecretStr("")
    allowed_collections: list[str] = ["mba-business"]
    embedding_provider: Literal["disabled", "openai", "ollama"] = "disabled"
    embedding_api_key: SecretStr = SecretStr("")
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_model_revision: str | None = None
    embedding_batch_size: int = Field(default=16, ge=1, le=32)
    embedding_timeout_seconds: float = Field(default=15, ge=0.1, le=60)
    embedding_query_timeout_seconds: float = Field(default=2, ge=0.1, le=30)
    embedding_document_timeout_seconds: float = Field(default=600, ge=1, le=600)
    embedding_max_document_chunks: int = Field(default=256, ge=1, le=256)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_keep_alive: str = "10m"
    ollama_query_instruction: str = (
        "Given a question, retrieve relevant passages that answer the question"
    )
    max_file_bytes: int = Field(default=20 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    max_extract_chars: int = Field(default=2_000_000, gt=0, le=5_000_000)
    max_batch_files: int = Field(default=100, gt=0, le=1000)
    max_pending_jobs: int = Field(default=1000, gt=0, le=10000)
    max_storage_chars: int = Field(default=100_000_000, gt=0)
    max_embedding_rows: int = Field(default=100000, ge=1, le=1000000)
    parser_timeout_seconds: int = Field(default=30, ge=1, le=120)
    job_lease_seconds: int = Field(default=900, ge=300)

    @model_validator(mode="after")
    def validate_embeddings(self):
        if self.embedding_dimensions not in {1024, 1536}:
            raise ValueError("Supported embedding dimensions are 1024 and 1536")
        if self.embedding_provider == "openai":
            if self.embedding_dimensions != 1536 or not self.embedding_api_key.get_secret_value():
                raise ValueError("OpenAI requires a separate embedding key and 1536 dimensions")
        if self.embedding_provider == "ollama":
            if self.embedding_model != "qwen3-embedding:0.6b" or self.embedding_dimensions != 1024:
                raise ValueError("Ollama requires qwen3-embedding:0.6b and 1024 dimensions")
            url = urlsplit(self.ollama_base_url)
            if (
                url.scheme != "http"
                or url.hostname not in {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
            ):
                raise ValueError(
                    "Ollama must use an explicit local HTTP origin, without credentials"
                )
            if self.embedding_model_revision:
                import re

                if not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", self.embedding_model_revision):
                    raise ValueError("Ollama model revision must be the full SHA256 digest")
        if len(self.ollama_query_instruction) > 500 or len(self.ollama_keep_alive) > 20:
            raise ValueError("Ollama instruction or keep_alive exceeds its bound")
        if (
            self.job_lease_seconds
            <= self.embedding_document_timeout_seconds + self.parser_timeout_seconds + 60
        ):
            raise ValueError("Job lease must exceed the bounded embedding and parsing duration")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
