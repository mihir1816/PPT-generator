from functools import lru_cache

from qdrant_client import AsyncQdrantClient, QdrantClient

from app.config import get_settings


@lru_cache
def get_qdrant() -> AsyncQdrantClient:
    settings = get_settings()
    return AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


@lru_cache
def get_sync_qdrant() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
