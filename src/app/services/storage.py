import asyncio
import io
from datetime import timedelta

from fastapi import UploadFile
from minio import Minio


class StorageService:
    def __init__(self, client: Minio, bucket: str):
        self.client = client
        self.bucket = bucket

    async def upload_file(self, file: UploadFile, key: str) -> str:
        data = await file.read()
        content_type = file.content_type or "application/octet-stream"
        return await self.upload_bytes(data, key, content_type)

    async def upload_bytes(self, data: bytes, key: str, content_type: str) -> str:
        def _put() -> None:
            self.client.put_object(
                self.bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return key

    async def download_file(self, key: str) -> bytes:
        def _get() -> bytes:
            response = self.client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(_get)

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        def _presign() -> str:
            return self.client.presigned_get_object(
                self.bucket, key, expires=timedelta(seconds=expires)
            )

        return await asyncio.to_thread(_presign)

    async def delete_file(self, key: str) -> None:
        def _delete() -> None:
            self.client.remove_object(self.bucket, key)

        await asyncio.to_thread(_delete)

    @staticmethod
    def generate_key(upload_id: str, filename: str) -> str:
        return f"uploads/{upload_id}/{filename}"
