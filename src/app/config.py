from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_NAME: str = "teacher_content_gen"
    DB_USER: str = "tcg_user"
    DB_PASSWORD: str

    REDIS_HOST: str = "valkey"
    REDIS_PORT: int = 6379

    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    MINIO_HOST: str = "minio"
    MINIO_PORT: int = 9000
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "tcg-uploads"

    LLM_BASE_URL: str = "http://vllm:8000/v1"
    LLM_MODEL: str = "Qwen/Qwen2.5-1.5B-Instruct-AWQ"
    LLM_API_KEY: str = "not-needed"
    LLM_FALLBACK_MODEL: str = ""
    LLM_MAX_TOKENS: int = 4096
    LLM_MODEL_CONTEXT: int = 4096
    LLM_TEMPERATURE: float = 0.7
    LLM_TIMEOUT: int = 120
    LLM_JSON_RETRIES: int = 1

    EMBEDDING_MODEL: str = "nomic-ai/nomic-embed-text-v1.5"
    EMBEDDING_DIMENSION: int = 768

    CHUNK_SIZE_CHILD: int = 512
    CHUNK_SIZE_PARENT: int = 2048
    CHUNK_OVERLAP: int = 50

    QDRANT_COLLECTION: str = "tcg_chunks"

    CELERY_BROKER_URL: str = "redis://valkey:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://valkey:6379/1"

    MAX_UPLOAD_SIZE_MB: int = 50
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
