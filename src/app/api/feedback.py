import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.database import async_session, get_db
from app.deps import get_feedback_service
from app.schemas.common import DeckStatus
from app.schemas.deck import TeacherPreferences
from app.services import crud
from app.services.feedback import FeedbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["feedback"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class SlideFeedbackRequest(BaseModel):
    feedback: str = Field(..., min_length=1, max_length=5000)


class UndoResponse(BaseModel):
    success: bool
    message: str
    outline: list[dict] = Field(default_factory=list)
    slides: list[dict] = Field(default_factory=list)
    version: int = 0


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/slide-feedback — SSE stream
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/slide-feedback")
async def slide_feedback(
    deck_id: UUID,
    body: SlideFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    feedback_svc: FeedbackService = Depends(get_feedback_service),
):
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    if deck.status not in (DeckStatus.COMPLETED, DeckStatus.OUTLINE_READY):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot apply feedback in state '{deck.status}'. "
            f"Deck must be '{DeckStatus.COMPLETED}'.",
        )

    if not deck.outline_json:
        raise HTTPException(status_code=409, detail="No outline found on deck")
    if not deck.retrieval_json:
        raise HTTPException(status_code=409, detail="No retrieval data found on deck")

    prefs = TeacherPreferences.model_validate(deck.preferences_json)
    retrieval_data = deck.retrieval_json

    async def event_stream():
        async with async_session() as stream_db:
            try:
                stream_deck = await crud.get_deck(stream_db, deck_id)
                async for event in feedback_svc.process_feedback(
                    stream_deck, body.feedback, retrieval_data, prefs, stream_db,
                ):
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event["data"]),
                    }
            except Exception as exc:
                logger.exception("Feedback stream failed for deck %s", deck_id)
                try:
                    stream_deck = await crud.get_deck(stream_db, deck_id)
                    if stream_deck:
                        stream_deck.status = DeckStatus.COMPLETED
                        await stream_db.commit()
                except Exception:
                    logger.exception("Failed to restore deck %s status after feedback error", deck_id)
                yield {
                    "event": "generation_error",
                    "data": json.dumps({"slide_id": "", "error": f"Feedback failed: {exc}"}),
                }

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/undo — undo last feedback round
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/undo", response_model=UndoResponse)
async def undo_feedback(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    feedback_svc: FeedbackService = Depends(get_feedback_service),
) -> UndoResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    result = await feedback_svc.undo_last_feedback(deck, db)

    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("message", "Undo failed"))

    return UndoResponse(
        success=True,
        message=result["message"],
        outline=result.get("outline", []),
        slides=result.get("slides", []),
        version=result.get("version", 0),
    )


# ---------------------------------------------------------------------------
# GET /api/decks/{deck_id}/feedback-history — list feedback rounds
# ---------------------------------------------------------------------------


class FeedbackRoundItem(BaseModel):
    id: UUID
    round_number: int
    feedback_type: str
    raw_feedback: str
    affected_slide_ids: list[str] = Field(default_factory=list)
    action_count: int = 0


class FeedbackHistoryResponse(BaseModel):
    deck_id: UUID
    rounds: list[FeedbackRoundItem] = Field(default_factory=list)


@router.get("/decks/{deck_id}/feedback-history", response_model=FeedbackHistoryResponse)
async def feedback_history(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FeedbackHistoryResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    rounds = await crud.get_feedback_rounds_by_deck(db, deck_id)
    return FeedbackHistoryResponse(
        deck_id=deck_id,
        rounds=[
            FeedbackRoundItem(
                id=r.id,
                round_number=r.round_number,
                feedback_type=r.feedback_type,
                raw_feedback=r.raw_feedback,
                affected_slide_ids=r.affected_slide_ids or [],
                action_count=len(r.parsed_actions_json or []),
            )
            for r in rounds
        ],
    )
