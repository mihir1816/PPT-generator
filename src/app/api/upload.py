import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.database import get_db
from app.deps import get_storage_service, get_vector_store
from app.schemas.common import TaskStatus, UploadResponse
from app.schemas.document import SourceType
from app.services import crud
from app.services.parsers.router import detect_source_type
from app.services.storage import StorageService
from app.services.vector_store import VectorStoreService
from app.tasks.process_upload import process_upload_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


class UploadURLRequest(BaseModel):
    url: str


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    if file.size and file.size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    file_bytes = await file.read()
    actual_size = len(file_bytes)
    if actual_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({actual_size} bytes). Max {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    filename = file.filename or "upload"
    source_type = detect_source_type(filename, file.content_type)

    upload = await crud.create_upload(
        db,
        filename=filename,
        source_type=source_type.value,
        minio_key="",
        mime_type=file.content_type,
        file_size=actual_size,
    )
    key = StorageService.generate_key(str(upload.id), filename)
    await storage.upload_bytes(file_bytes, key, file.content_type or "application/octet-stream")
    upload.minio_key = key
    await db.commit()

    process_upload_task.delay(str(upload.id))

    return UploadResponse(file_id=upload.id, filename=upload.filename, status=TaskStatus.PENDING)


@router.post("/upload-url", response_model=UploadResponse, status_code=202)
async def upload_url(
    payload: UploadURLRequest, db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    if not payload.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="Only http:// and https:// URLs are accepted",
        )

    upload = await crud.create_upload(
        db,
        filename=payload.url,
        source_type=SourceType.WEB_URL.value,
        minio_key=payload.url,  # web uploads have no MinIO object; the URL is fetched live
    )
    await db.commit()

    process_upload_task.delay(str(upload.id))

    return UploadResponse(file_id=upload.id, filename=upload.filename, status=TaskStatus.PENDING)


@router.get("/upload/{upload_id}")
async def get_upload_status(upload_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    upload = await crud.get_upload(db, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")

    document_id = None
    if upload.status == "completed":
        docs = await crud.get_documents_by_upload(db, upload_id)
        if docs:
            document_id = docs[0].id

    return {
        "file_id": upload.id,
        "filename": upload.filename,
        "status": upload.status,
        "document_id": document_id,
        "error_message": upload.error_message,
    }


class DocumentItem(BaseModel):
    id: uuid.UUID
    title: str | None = None
    source_type: str
    is_indexed: bool
    chunk_count: int
    block_count: int = 0
    text_preview: str = ""


class DocumentListResponse(BaseModel):
    documents: list[DocumentItem] = Field(default_factory=list)


class DocumentDetailResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    source_type: str
    block_count: int = 0
    text_preview: str = ""
    is_indexed: bool
    chunk_count: int


class DeleteResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# GET /api/documents — list all documents
# ---------------------------------------------------------------------------


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    docs = await crud.get_all_documents(db)
    return DocumentListResponse(
        documents=[
            DocumentItem(
                id=d.id,
                title=d.title,
                source_type=d.source_type,
                is_indexed=d.is_indexed,
                chunk_count=d.chunk_count,
                block_count=len(d.content_blocks or []),
                text_preview=(d.raw_text or "")[:200],
            )
            for d in docs
        ]
    )


# ---------------------------------------------------------------------------
# GET /api/documents/{document_id} — document detail
# ---------------------------------------------------------------------------


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DocumentDetailResponse:
    document = await crud.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetailResponse(
        id=document.id,
        title=document.title,
        source_type=document.source_type,
        block_count=len(document.content_blocks or []),
        text_preview=(document.raw_text or "")[:500],
        is_indexed=document.is_indexed,
        chunk_count=document.chunk_count,
    )


# ---------------------------------------------------------------------------
# DELETE /api/documents/{document_id} — full cleanup
# ---------------------------------------------------------------------------


@router.delete("/documents/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    vector_store: VectorStoreService = Depends(get_vector_store),
    storage: StorageService = Depends(get_storage_service),
) -> DeleteResponse:
    document = await crud.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Delete vectors from Qdrant
    try:
        await vector_store.delete_by_document(str(document_id))
    except Exception:
        logger.exception("Failed to delete Qdrant vectors for document %s", document_id)

    # 2. Delete source file from MinIO (via the upload record)
    upload = await crud.get_upload(db, document.upload_id)
    if upload and upload.minio_key and not upload.minio_key.startswith("http"):
        try:
            await storage.delete_file(upload.minio_key)
        except Exception:
            logger.exception("Failed to delete MinIO file for document %s", document_id)

    # 3. DB CASCADE handles chunks and deck_document rows
    await crud.delete_document(db, document_id)
    await db.commit()

    return DeleteResponse(success=True, message=f"Document {document_id} deleted")
