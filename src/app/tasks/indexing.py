import logging
import uuid
from uuid import UUID

from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)
from sqlalchemy import select

from app.config import get_settings
from app.core.celery_app import celery_app
from app.core.database import get_sync_db
from app.core.qdrant_client import get_sync_qdrant
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.chunking import ChunkingService
from app.services.crud import (
    fail_decks_for_document_sync,
    get_decks_waiting_for_document_sync,
    try_transition_to_ready_sync,
)
from app.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)

_embedding_service: EmbeddingService | None = None
_chunking_service: ChunkingService | None = None


def _get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        settings = get_settings()
        _embedding_service = EmbeddingService(
            model_name=settings.EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )
    return _embedding_service


def _get_chunking_service() -> ChunkingService:
    global _chunking_service
    if _chunking_service is None:
        settings = get_settings()
        _chunking_service = ChunkingService(
            child_chunk_size=settings.CHUNK_SIZE_CHILD,
            child_chunk_overlap=settings.CHUNK_OVERLAP,
            parent_chunk_size=settings.CHUNK_SIZE_PARENT,
        )
    return _chunking_service


QDRANT_UPSERT_BATCH = 100


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def index_document_task(self, document_id: str) -> None:
    settings = get_settings()
    db = get_sync_db()
    try:
        doc = db.get(Document, UUID(document_id))
        if doc is None:
            logger.error("Document %s not found", document_id)
            return

        if doc.is_indexed:
            logger.info("Document %s already indexed, skipping", document_id)
            return

        logger.info("Starting indexing for document %s ('%s')", document_id, doc.title)

        # Clean up any partial previous attempt (idempotent retries)
        _cleanup_previous(db, document_id, settings)

        # Step 1: Chunk
        chunking_svc = _get_chunking_service()
        chunk_results = chunking_svc.chunk_document(
            doc.markdown_content or "",
            {"document_id": document_id, "source_type": doc.source_type},
        )

        if not chunk_results:
            logger.warning("No chunks produced for document %s", document_id)
            doc.is_indexed = True
            doc.chunk_count = 0
            db.commit()
            return

        # Step 2: Embed
        embedding_svc = _get_embedding_service()
        texts = [c.content for c in chunk_results]
        vectors = embedding_svc.embed_documents(texts)

        # Step 3: Upsert to Qdrant
        qdrant = get_sync_qdrant()
        collection = settings.QDRANT_COLLECTION
        point_ids: list[str] = []

        for batch_start in range(0, len(chunk_results), QDRANT_UPSERT_BATCH):
            batch_end = batch_start + QDRANT_UPSERT_BATCH
            batch_chunks = chunk_results[batch_start:batch_end]
            batch_vectors = vectors[batch_start:batch_end]

            points = []
            for cr, vec in zip(batch_chunks, batch_vectors):
                pid = str(uuid.uuid4())
                point_ids.append(pid)
                points.append(
                    PointStruct(
                        id=pid,
                        vector=vec,
                        payload={
                            "document_id": document_id,
                            "chunk_index": len(point_ids) - 1,
                            "content": cr.content,
                            "parent_content": cr.parent_content,
                            "metadata": cr.metadata,
                        },
                    )
                )
            qdrant.upsert(collection_name=collection, points=points)

        # Step 4: Save chunks to DB
        db_chunks = []
        for idx, (cr, pid) in enumerate(zip(chunk_results, point_ids)):
            db_chunks.append(
                Chunk(
                    document_id=UUID(document_id),
                    chunk_index=idx,
                    content=cr.content,
                    parent_content=cr.parent_content,
                    metadata_json=cr.metadata,
                    embedding_id=pid,
                    token_count=cr.token_count,
                )
            )
        db.add_all(db_chunks)

        # Step 5: Update document
        doc.is_indexed = True
        doc.chunk_count = len(db_chunks)
        db.commit()

        logger.info(
            "Indexed document %s: %d chunks, %d vectors",
            document_id,
            len(db_chunks),
            len(point_ids),
        )

        deck_ids = get_decks_waiting_for_document_sync(db, UUID(document_id))
        for did in deck_ids:
            if try_transition_to_ready_sync(db, did):
                logger.info("Deck %s transitioned to ready_for_retrieval", did)

    except Exception as exc:
        logger.exception("Error indexing document %s", document_id)
        db.rollback()
        if self.request.retries >= self.max_retries:
            doc = db.get(Document, UUID(document_id))
            if doc is not None:
                doc.is_indexed = False
                doc.chunk_count = 0
                db.commit()
            failed_decks = fail_decks_for_document_sync(db, UUID(document_id))
            for fd in failed_decks:
                logger.warning("Deck %s marked failed due to document %s indexing failure", fd, document_id)
        else:
            raise self.retry(exc=exc)
    finally:
        db.close()


def _cleanup_previous(db, document_id: str, settings) -> None:
    existing = db.execute(
        select(Chunk).where(Chunk.document_id == UUID(document_id))
    ).scalars().all()
    if not existing:
        return

    logger.info(
        "Cleaning up %d existing chunks for document %s (retry)",
        len(existing),
        document_id,
    )

    qdrant = get_sync_qdrant()
    qdrant.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            )
        ),
    )

    for chunk in existing:
        db.delete(chunk)
    db.flush()
