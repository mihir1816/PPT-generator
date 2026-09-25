import asyncio
from functools import lru_cache

from minio import Minio

from app.config import Settings, get_settings


def _build_client(settings: Settings) -> Minio:
    return Minio(
        f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )


@lru_cache
def _cached_client() -> Minio:
    return _build_client(get_settings())


def get_minio_client(settings: Settings | None = None) -> Minio:
    if settings is not None:
        return _build_client(settings)
    return _cached_client()


async def ensure_bucket(client: Minio, bucket: str) -> None:
    def _ensure() -> None:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

    await asyncio.to_thread(_ensure)
