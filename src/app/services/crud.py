import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.deck import Deck
from app.models.deck_document import DeckDocument
from app.models.document import Document
from app.models.feedback import FeedbackRound
from app.models.slide import Slide
from app.models.upload import Upload

# --- Upload ---


async def create_upload(
    db: AsyncSession,
    *,
    filename: str,
    source_type: str,
    minio_key: str,
    mime_type: str | None = None,
    file_size: int | None = None,
) -> Upload:
    upload = Upload(
        filename=filename,
        source_type=source_type,
        minio_key=minio_key,
        mime_type=mime_type,
        file_size=file_size,
        status="pending",
    )
    db.add(upload)
    await db.flush()
    return upload


async def get_upload(db: AsyncSession, upload_id: uuid.UUID) -> Upload | None:
    return await db.get(Upload, upload_id)


async def update_upload_status(
    db: AsyncSession,
    upload_id: uuid.UUID,
    status: str,
    error_message: str | None = None,
) -> Upload | None:
    upload = await db.get(Upload, upload_id)
    if upload is None:
        return None
    upload.status = status
    if error_message is not None:
        upload.error_message = error_message
    await db.flush()
    return upload


# --- Document ---


async def create_document(
    db: AsyncSession,
    *,
    upload_id: uuid.UUID,
    title: str | None,
    source_type: str,
    raw_text: str,
    content_blocks: list,
    markdown_content: str,
) -> Document:
    document = Document(
        upload_id=upload_id,
        title=title,
        source_type=source_type,
        raw_text=raw_text,
        content_blocks=content_blocks,
        markdown_content=markdown_content,
    )
    db.add(document)
    await db.flush()
    return document


async def get_document(db: AsyncSession, document_id: uuid.UUID) -> Document | None:
    return await db.get(Document, document_id)


async def get_documents_by_upload(
    db: AsyncSession, upload_id: uuid.UUID
) -> list[Document]:
    result = await db.execute(select(Document).where(Document.upload_id == upload_id))
    return list(result.scalars().all())


async def get_all_documents(db: AsyncSession) -> list[Document]:
    result = await db.execute(select(Document))
    return list(result.scalars().all())


async def delete_document(db: AsyncSession, document_id: uuid.UUID) -> None:
    document = await db.get(Document, document_id)
    if document is not None:
        await db.delete(document)
        await db.flush()


# --- Chunk ---


async def create_chunks_bulk(
    db: AsyncSession, document_id: uuid.UUID, chunks: list[dict]
) -> list[Chunk]:
    objs = [
        Chunk(
            document_id=document_id,
            chunk_index=c["chunk_index"],
            content=c["content"],
            parent_content=c.get("parent_content"),
            metadata_json=c.get("metadata_json"),
            embedding_id=c.get("embedding_id"),
            token_count=c.get("token_count", 0),
        )
        for c in chunks
    ]
    db.add_all(objs)
    await db.flush()
    return objs


async def get_chunks_by_document(db: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
    result = await db.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
    )
    return list(result.scalars().all())


async def get_chunks_by_ids(db: AsyncSession, chunk_ids: list[uuid.UUID]) -> list[Chunk]:
    if not chunk_ids:
        return []
    result = await db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    return list(result.scalars().all())


async def get_chunks_by_documents(
    db: AsyncSession, document_ids: list[uuid.UUID]
) -> list[Chunk]:
    if not document_ids:
        return []
    result = await db.execute(
        select(Chunk).where(Chunk.document_id.in_(document_ids))
    )
    return list(result.scalars().all())


# --- Deck ---


async def create_deck(
    db: AsyncSession,
    *,
    title: str = "Presentation",
    teacher_query: str,
    preferences_json: dict,
) -> Deck:
    deck = Deck(title=title, teacher_query=teacher_query, preferences_json=preferences_json)
    db.add(deck)
    await db.flush()
    return deck


async def get_deck(db: AsyncSession, deck_id: uuid.UUID) -> Deck | None:
    return await db.get(Deck, deck_id)


async def get_all_decks(db: AsyncSession) -> list[Deck]:
    result = await db.execute(select(Deck))
    return list(result.scalars().all())


async def update_deck_status(db: AsyncSession, deck_id: uuid.UUID, status: str) -> Deck | None:
    deck = await db.get(Deck, deck_id)
    if deck is None:
        return None
    deck.status = status
    await db.flush()
    return deck


async def update_deck_syllabus(
    db: AsyncSession,
    deck_id: uuid.UUID,
    syllabus_json: dict,
    syllabus_status: str | None = None,
) -> Deck | None:
    deck = await db.get(Deck, deck_id)
    if deck is None:
        return None
    deck.syllabus_json = syllabus_json
    if syllabus_status is not None:
        deck.syllabus_status = syllabus_status
    await db.flush()
    return deck


async def update_deck_outline(
    db: AsyncSession, deck_id: uuid.UUID, outline_json: list
) -> Deck | None:
    deck = await db.get(Deck, deck_id)
    if deck is None:
        return None
    deck.outline_json = outline_json
    await db.flush()
    return deck


async def update_deck_retrieval(
    db: AsyncSession, deck_id: uuid.UUID, retrieval_json: dict
) -> Deck | None:
    deck = await db.get(Deck, deck_id)
    if deck is None:
        return None
    deck.retrieval_json = retrieval_json
    await db.flush()
    return deck


async def get_deck_retrieval(db: AsyncSession, deck_id: uuid.UUID) -> dict | None:
    deck = await db.get(Deck, deck_id)
    return deck.retrieval_json if deck else None


async def delete_deck(db: AsyncSession, deck_id: uuid.UUID) -> None:
    deck = await db.get(Deck, deck_id)
    if deck is not None:
        await db.delete(deck)
        await db.flush()


# --- DeckDocument ---


async def link_deck_document(
    db: AsyncSession, deck_id: uuid.UUID, document_id: uuid.UUID
) -> DeckDocument:
    link = DeckDocument(deck_id=deck_id, document_id=document_id)
    db.add(link)
    await db.flush()
    return link


async def get_deck_documents(db: AsyncSession, deck_id: uuid.UUID) -> list[DeckDocument]:
    result = await db.execute(
        select(DeckDocument).where(DeckDocument.deck_id == deck_id)
    )
    return list(result.scalars().all())


async def get_deck_document_ids(db: AsyncSession, deck_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(DeckDocument.document_id).where(DeckDocument.deck_id == deck_id)
    )
    return list(result.scalars().all())


async def get_documents_by_ids(
    db: AsyncSession, document_ids: list[uuid.UUID]
) -> list[Document]:
    if not document_ids:
        return []
    result = await db.execute(select(Document).where(Document.id.in_(document_ids)))
    return list(result.scalars().all())


# --- Wait Gate (atomic deck transition) ---

_TRANSITION_SQL = text("""
    UPDATE decks SET status = 'ready_for_retrieval',
                     updated_at = NOW()
    WHERE id = :deck_id
      AND syllabus_status = 'approved'
      AND status IN ('syllabus_review', 'waiting_for_indexing')
      AND NOT EXISTS (
          SELECT 1 FROM deck_documents dd
          JOIN documents d ON d.id = dd.document_id
          WHERE dd.deck_id = :deck_id AND d.is_indexed = FALSE
      )
    RETURNING id
""")


async def try_transition_to_ready(db: AsyncSession, deck_id: uuid.UUID) -> bool:
    result = await db.execute(_TRANSITION_SQL, {"deck_id": str(deck_id)})
    await db.commit()
    return result.fetchone() is not None


def try_transition_to_ready_sync(db: Session, deck_id: uuid.UUID) -> bool:
    result = db.execute(_TRANSITION_SQL, {"deck_id": str(deck_id)})
    db.commit()
    return result.fetchone() is not None


_WAITING_SQL = text("""
    UPDATE decks SET status = 'waiting_for_indexing',
                     updated_at = NOW()
    WHERE id = :deck_id
      AND status = 'syllabus_review'
      AND syllabus_status = 'approved'
    RETURNING id
""")


async def try_set_waiting_for_indexing(db: AsyncSession, deck_id: uuid.UUID) -> bool:
    """Atomically set deck to waiting_for_indexing only if still in syllabus_review.

    If the Celery worker already transitioned it to ready_for_retrieval
    between the try_transition_to_ready call and now, this update won't
    match and returns False — avoiding an overwrite of the ready state.
    """
    result = await db.execute(_WAITING_SQL, {"deck_id": str(deck_id)})
    await db.commit()
    return result.fetchone() is not None


async def get_decks_waiting_for_document(
    db: AsyncSession, document_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await db.execute(
        select(DeckDocument.deck_id)
        .join(Deck, Deck.id == DeckDocument.deck_id)
        .where(
            DeckDocument.document_id == document_id,
            Deck.status.in_(["waiting_for_indexing", "syllabus_review"]),
        )
    )
    return list(result.scalars().all())


def get_decks_waiting_for_document_sync(
    db: Session, document_id: uuid.UUID
) -> list[uuid.UUID]:
    result = db.execute(
        select(DeckDocument.deck_id)
        .join(Deck, Deck.id == DeckDocument.deck_id)
        .where(
            DeckDocument.document_id == document_id,
            Deck.status.in_(["waiting_for_indexing", "syllabus_review"]),
        )
    )
    return list(result.scalars().all())


def fail_decks_for_document_sync(
    db: Session, document_id: uuid.UUID
) -> list[uuid.UUID]:
    """Mark any decks waiting on this document as failed."""
    deck_ids = get_decks_waiting_for_document_sync(db, document_id)
    if not deck_ids:
        return []
    for did in deck_ids:
        deck = db.get(Deck, did)
        if deck is not None and deck.status in ("waiting_for_indexing", "syllabus_review"):
            deck.status = "failed"
    db.commit()
    return deck_ids


# --- Slide ---


async def create_slide(db: AsyncSession, deck_id: uuid.UUID, data: dict) -> Slide:
    slide = Slide(deck_id=deck_id, **data)
    db.add(slide)
    await db.flush()
    return slide


async def create_slides_bulk(
    db: AsyncSession, deck_id: uuid.UUID, slides: list[dict]
) -> list[Slide]:
    objs = [Slide(deck_id=deck_id, **s) for s in slides]
    db.add_all(objs)
    await db.flush()
    return objs


async def get_slides_by_deck(db: AsyncSession, deck_id: uuid.UUID) -> list[Slide]:
    result = await db.execute(
        select(Slide).where(Slide.deck_id == deck_id).order_by(Slide.position)
    )
    return list(result.scalars().all())


async def get_slide_by_slide_id(
    db: AsyncSession, deck_id: uuid.UUID, slide_id: str
) -> Slide | None:
    result = await db.execute(
        select(Slide).where(Slide.deck_id == deck_id, Slide.slide_id == slide_id)
    )
    return result.scalar_one_or_none()


async def update_slide(db: AsyncSession, slide_pk: uuid.UUID, data: dict) -> Slide | None:
    slide = await db.get(Slide, slide_pk)
    if slide is None:
        return None
    for key, value in data.items():
        setattr(slide, key, value)
    await db.flush()
    return slide


async def delete_slides_by_deck(db: AsyncSession, deck_id: uuid.UUID) -> None:
    slides = await get_slides_by_deck(db, deck_id)
    for slide in slides:
        await db.delete(slide)
    await db.flush()


# --- FeedbackRound ---


async def create_feedback_round(db: AsyncSession, deck_id: uuid.UUID, data: dict) -> FeedbackRound:
    round_ = FeedbackRound(deck_id=deck_id, **data)
    db.add(round_)
    await db.flush()
    return round_


async def get_feedback_rounds_by_deck(
    db: AsyncSession, deck_id: uuid.UUID
) -> list[FeedbackRound]:
    result = await db.execute(
        select(FeedbackRound)
        .where(FeedbackRound.deck_id == deck_id)
        .order_by(FeedbackRound.round_number)
    )
    return list(result.scalars().all())


async def get_last_feedback_round(
    db: AsyncSession,
    deck_id: uuid.UUID,
    feedback_type: str | None = None,
) -> FeedbackRound | None:
    stmt = (
        select(FeedbackRound)
        .where(FeedbackRound.deck_id == deck_id)
    )
    if feedback_type is not None:
        stmt = stmt.where(FeedbackRound.feedback_type == feedback_type)
    stmt = stmt.order_by(FeedbackRound.round_number.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_feedback_round(db: AsyncSession, feedback_round_id: uuid.UUID) -> None:
    round_ = await db.get(FeedbackRound, feedback_round_id)
    if round_ is not None:
        await db.delete(round_)
        await db.flush()
