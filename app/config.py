from functools import lru_cache

from pydantic import Field, SecretStr
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
    embedding_api_key: SecretStr = SecretStr("")
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1536, le=1536)
    max_file_bytes: int = Field(default=20 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    max_extract_chars: int = Field(default=2_000_000, gt=0, le=5_000_000)
    max_batch_files: int = Field(default=100, gt=0, le=1000)
    max_pending_jobs: int = Field(default=1000, gt=0, le=10000)
    max_storage_chars: int = Field(default=100_000_000, gt=0)
    parser_timeout_seconds: int = Field(default=30, ge=1, le=120)
    job_lease_seconds: int = Field(default=900, ge=300)


@lru_cache
def get_settings() -> Settings:
    return Settings()
