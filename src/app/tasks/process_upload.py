import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.celery_app import celery_app
from app.core.database import get_sync_db
from app.core.minio_client import get_minio_client
from app.models.document import Document
from app.models.upload import Upload
from app.schemas.document import SourceType
from app.services.parsers.base import ParseError
from app.services.parsers.router import parse_upload
from app.tasks.indexing import index_document_task

logger = logging.getLogger(__name__)


def _mark_failed(db: Session, upload_id: str, message: str) -> None:
    db.rollback()
    upload = db.get(Upload, UUID(upload_id))
    if upload is not None:
        upload.status = "failed"
        upload.error_message = message[:2000]
        db.commit()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def process_upload_task(self, upload_id: str) -> None:
    settings = get_settings()
    db = get_sync_db()
    try:
        upload = db.get(Upload, UUID(upload_id))
        if upload is None:
            logger.error("Upload %s not found", upload_id)
            return

        upload.status = "processing"
        db.commit()

        source_type = SourceType(upload.source_type)

        if source_type == SourceType.WEB_URL:
            file_bytes = b""
            filename = upload.minio_key  # holds the raw URL for web uploads
        else:
            client = get_minio_client(settings)
            response = client.get_object(settings.MINIO_BUCKET, upload.minio_key)
            try:
                file_bytes = response.read()
            finally:
                response.close()
                response.release_conn()
            filename = upload.filename

        try:
            processed = parse_upload(file_bytes, filename, source_type)
        except ParseError as exc:
            _mark_failed(db, upload_id, exc.message)
            return

        document = Document(
            upload_id=upload.id,
            title=processed.title,
            source_type=source_type.value,
            raw_text=processed.raw_text,
            content_blocks=[b.model_dump(mode="json") for b in processed.blocks],
            markdown_content=processed.to_markdown(),
        )
        db.add(document)
        upload.status = "completed"
        db.commit()

        index_document_task.delay(str(document.id))

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error processing upload %s", upload_id)
        if self.request.retries >= self.max_retries:
            _mark_failed(db, upload_id, str(exc))
        else:
            raise self.retry(exc=exc)
    finally:
        db.close()
