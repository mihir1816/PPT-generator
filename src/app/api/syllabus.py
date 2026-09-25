import asyncio
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_storage_service, get_syllabus_service
from app.schemas.common import DeckStatus
from app.schemas.deck import TeacherPreferences
from app.schemas.syllabus import TopicSyllabus
from app.services import crud
from app.services.llm_client import LLMServiceError
from app.services.storage import StorageService
from app.services.syllabus import SyllabusService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["syllabus"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateDeckRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1)
    description: str = Field(min_length=1, max_length=5000)
    outline: str | None = None
    preferences: TeacherPreferences = Field(default_factory=TeacherPreferences)


class DeckResponse(BaseModel):
    deck_id: UUID
    status: str
    syllabus: TopicSyllabus | None = None
    syllabus_status: str = "pending"
    version: int = 0
    document_ids: list[UUID] = Field(default_factory=list)
    message: str | None = None


class SyllabusFeedbackRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=10000)


# ---------------------------------------------------------------------------
# POST /api/decks — create deck + generate syllabus
# ---------------------------------------------------------------------------


@router.post("/decks", response_model=DeckResponse, status_code=201)
async def create_deck(
    body: CreateDeckRequest,
    db: AsyncSession = Depends(get_db),
    syllabus_svc: SyllabusService = Depends(get_syllabus_service),
) -> DeckResponse:
    unique_doc_ids = list(dict.fromkeys(body.document_ids))

    docs = await crud.get_documents_by_ids(db, unique_doc_ids)
    found_ids = {d.id for d in docs}
    missing = [did for did in unique_doc_ids if did not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Documents not found: {[str(m) for m in missing]}",
        )

    deck = await crud.create_deck(
        db,
        teacher_query=body.description,
        preferences_json=body.preferences.model_dump(mode="json"),
    )
    for doc_id in unique_doc_ids:
        await crud.link_deck_document(db, deck.id, doc_id)

    deck.status = DeckStatus.GENERATING_SYLLABUS
    await db.flush()

    try:
        syllabus = await syllabus_svc.generate_syllabus(
            body.description, body.outline, body.preferences,
        )
    except LLMServiceError as exc:
        deck.status = DeckStatus.FAILED
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    deck.syllabus_json = syllabus.model_dump(mode="json")
    deck.syllabus_status = "draft"
    deck.status = DeckStatus.SYLLABUS_REVIEW
    await db.commit()

    return DeckResponse(
        deck_id=deck.id,
        status=deck.status,
        syllabus=syllabus,
        syllabus_status=deck.syllabus_status,
        version=deck.version,
        document_ids=unique_doc_ids,
    )


# ---------------------------------------------------------------------------
# GET /api/decks/{deck_id}
# ---------------------------------------------------------------------------


@router.get("/decks/{deck_id}", response_model=DeckResponse)
async def get_deck(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeckResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    doc_ids = await crud.get_deck_document_ids(db, deck_id)

    syllabus = None
    if deck.syllabus_json:
        syllabus = TopicSyllabus.model_validate(deck.syllabus_json)

    return DeckResponse(
        deck_id=deck.id,
        status=deck.status,
        syllabus=syllabus,
        syllabus_status=deck.syllabus_status,
        version=deck.version,
        document_ids=doc_ids,
    )


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/syllabus-feedback
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/syllabus-feedback", response_model=DeckResponse)
async def syllabus_feedback(
    deck_id: UUID,
    body: SyllabusFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    syllabus_svc: SyllabusService = Depends(get_syllabus_service),
) -> DeckResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    if deck.status != DeckStatus.SYLLABUS_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send feedback in state '{deck.status}'. "
            f"Deck must be in '{DeckStatus.SYLLABUS_REVIEW}' state.",
        )

    if not deck.syllabus_json:
        raise HTTPException(status_code=409, detail="No syllabus to update")

    current_syllabus = TopicSyllabus.model_validate(deck.syllabus_json)

    last_round = await crud.get_last_feedback_round(db, deck_id, feedback_type="syllabus")
    next_round_number = (last_round.round_number + 1) if last_round else 1

    await crud.create_feedback_round(
        db,
        deck_id,
        {
            "round_number": next_round_number,
            "feedback_type": "syllabus",
            "raw_feedback": body.feedback,
            "syllabus_snapshot_json": deck.syllabus_json,
        },
    )
    await db.commit()

    try:
        updated_syllabus = await syllabus_svc.apply_feedback(
            current_syllabus, body.feedback,
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    deck.syllabus_json = updated_syllabus.model_dump(mode="json")
    deck.version += 1
    await db.commit()

    doc_ids = await crud.get_deck_document_ids(db, deck_id)

    return DeckResponse(
        deck_id=deck.id,
        status=deck.status,
        syllabus=updated_syllabus,
        syllabus_status=deck.syllabus_status,
        version=deck.version,
        document_ids=doc_ids,
    )


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/syllabus-approve
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/syllabus-approve", response_model=DeckResponse)
async def syllabus_approve(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeckResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    if deck.status != DeckStatus.SYLLABUS_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve in state '{deck.status}'. "
            f"Deck must be in '{DeckStatus.SYLLABUS_REVIEW}' state.",
        )

    if not deck.syllabus_json:
        raise HTTPException(status_code=409, detail="No syllabus to approve")

    deck.syllabus_status = "approved"
    await db.flush()

    transitioned = await crud.try_transition_to_ready(db, deck_id)

    if transitioned:
        await db.refresh(deck)
        status = DeckStatus.READY_FOR_RETRIEVAL
        message = "Syllabus approved. All documents indexed — ready for retrieval."
    else:
        moved = await crud.try_set_waiting_for_indexing(db, deck_id)
        await db.refresh(deck)
        status = deck.status
        if moved:
            message = "Syllabus approved. Waiting for documents to finish indexing."
        else:
            message = "Syllabus approved. Documents indexed — ready for retrieval."

    doc_ids = await crud.get_deck_document_ids(db, deck_id)
    syllabus = TopicSyllabus.model_validate(deck.syllabus_json)

    return DeckResponse(
        deck_id=deck.id,
        status=status,
        syllabus=syllabus,
        syllabus_status=deck.syllabus_status,
        version=deck.version,
        document_ids=doc_ids,
        message=message,
    )


# ---------------------------------------------------------------------------
# GET /api/decks — list all decks
# ---------------------------------------------------------------------------


class DeckListItem(BaseModel):
    deck_id: UUID
    status: str
    syllabus_status: str
    teacher_query: str
    version: int
    slide_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DeckListResponse(BaseModel):
    decks: list[DeckListItem] = Field(default_factory=list)


@router.get("/decks", response_model=DeckListResponse)
async def list_decks(
    db: AsyncSession = Depends(get_db),
) -> DeckListResponse:
    decks = await crud.get_all_decks(db)
    items: list[DeckListItem] = []
    for d in decks:
        slides = await crud.get_slides_by_deck(db, d.id)
        items.append(
            DeckListItem(
                deck_id=d.id,
                status=d.status,
                syllabus_status=d.syllabus_status,
                teacher_query=d.teacher_query[:200],
                version=d.version,
                slide_count=len(slides),
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
        )
    return DeckListResponse(decks=items)


# ---------------------------------------------------------------------------
# DELETE /api/decks/{deck_id} — full cleanup
# ---------------------------------------------------------------------------


class DeleteResponse(BaseModel):
    success: bool
    message: str


@router.delete("/decks/{deck_id}", response_model=DeleteResponse)
async def delete_deck(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DeleteResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    # 1. Delete exported PPTX files from MinIO
    try:
        prefix = f"exports/{deck_id}/"
        objects = await asyncio.to_thread(
            lambda: list(storage.client.list_objects(storage.bucket, prefix=prefix, recursive=True))
        )
        for obj in objects:
            await storage.delete_file(obj.object_name)
    except Exception:
        logger.exception("Failed to clean MinIO exports for deck %s", deck_id)

    # 2. DB CASCADE handles: slides, feedback_rounds, deck_documents
    await crud.delete_deck(db, deck_id)
    await db.commit()

    return DeleteResponse(success=True, message=f"Deck {deck_id} deleted")
