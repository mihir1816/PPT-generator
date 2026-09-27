import json
import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.database import async_session, get_db
from app.deps import get_rag_service, get_slide_generator, get_slide_outline_service
from app.schemas.common import DeckStatus
from app.schemas.deck import SlideOutline, TeacherPreferences
from app.schemas.syllabus import TopicSyllabus
from app.services import crud
from app.services.rag import RAGService
from app.services.slide_generator import SlideGenerator
from app.services.slide_outline import SlideOutlineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])

_BRACKET_RE = re.compile(r"\[\[(.+?)\]\]")


def _strip_emphasis(text: str) -> str:
    if not text:
        return text
    prev = None
    while prev != text:
        prev = text
        text = _BRACKET_RE.sub(r"\1", text)
    return text


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TopicCoverageItem(BaseModel):
    topic: str
    coverage: str
    chunk_count: int


class RetrievalResponse(BaseModel):
    deck_id: UUID
    status: str
    total_chunks: int
    queries_generated: int
    coverage: list[TopicCoverageItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    message: str | None = None


class OutlineResponse(BaseModel):
    deck_id: UUID
    status: str
    outline: list[SlideOutline] = Field(default_factory=list)
    slide_count: int = 0
    message: str | None = None


class SlideItem(BaseModel):
    slide_id: str
    position: int
    title: str
    body: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    table_data: dict | None = None
    speaker_notes: str = ""
    layout_hint: str = "bullet"


class SlidesListResponse(BaseModel):
    deck_id: UUID
    slides: list[SlideItem] = Field(default_factory=list)


class GenerationStatusResponse(BaseModel):
    deck_id: UUID
    status: str
    total: int
    generated: int
    pending: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/retrieve — trigger RAG retrieval
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/retrieve", response_model=RetrievalResponse)
async def trigger_retrieval(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    rag_svc: RAGService = Depends(get_rag_service),
) -> RetrievalResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    allowed = (DeckStatus.READY_FOR_RETRIEVAL, DeckStatus.RETRIEVING)
    if deck.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot retrieve in state '{deck.status}'. "
            f"Deck must be in '{DeckStatus.READY_FOR_RETRIEVAL}' state.",
        )

    if not deck.syllabus_json:
        raise HTTPException(status_code=409, detail="No syllabus found on deck")

    doc_ids = await crud.get_deck_document_ids(db, deck_id)
    if not doc_ids:
        raise HTTPException(
            status_code=409, detail="No documents linked to this deck"
        )

    deck.status = DeckStatus.RETRIEVING
    await db.commit()

    syllabus = TopicSyllabus.model_validate(deck.syllabus_json)
    prefs = TeacherPreferences.model_validate(deck.preferences_json)
    doc_id_strs = [str(d) for d in doc_ids]

    try:
        result = await rag_svc.retrieve_for_deck(
            syllabus, doc_id_strs, prefs.content_mode, db,
        )
    except Exception as exc:
        logger.exception("Retrieval failed for deck %s", deck_id)
        deck.status = DeckStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail=f"Retrieval pipeline failed: {exc}",
        ) from exc

    deck.retrieval_json = result.to_dict()
    deck.status = DeckStatus.RETRIEVAL_COMPLETE
    await db.commit()

    coverage = [
        TopicCoverageItem(
            topic=tc.topic_title,
            coverage=tc.coverage,
            chunk_count=len(tc.chunks),
        )
        for tc in result.topic_chunks
    ]

    return RetrievalResponse(
        deck_id=deck_id,
        status=deck.status,
        total_chunks=result.total_chunks,
        queries_generated=result.queries_generated,
        coverage=coverage,
        gaps=result.gaps,
        message=(
            "Retrieval complete — all topics covered."
            if not result.gaps
            else f"Retrieval complete — {len(result.gaps)} topic(s) with gaps."
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/generate-outline — generate slide outline
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/generate-outline", response_model=OutlineResponse)
async def generate_outline(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    outline_svc: SlideOutlineService = Depends(get_slide_outline_service),
) -> OutlineResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    allowed = (DeckStatus.RETRIEVAL_COMPLETE, DeckStatus.GENERATING_OUTLINE)
    if deck.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot generate outline in state '{deck.status}'. "
            f"Deck must be in '{DeckStatus.RETRIEVAL_COMPLETE}' state.",
        )

    if not deck.syllabus_json:
        raise HTTPException(status_code=409, detail="No syllabus found on deck")

    if not deck.retrieval_json:
        raise HTTPException(
            status_code=409, detail="No retrieval data found on deck"
        )

    deck.status = DeckStatus.GENERATING_OUTLINE
    await db.commit()

    syllabus = TopicSyllabus.model_validate(deck.syllabus_json)
    prefs = TeacherPreferences.model_validate(deck.preferences_json)

    try:
        outline = await outline_svc.generate_outline(
            syllabus, deck.retrieval_json, prefs,
        )
    except Exception as exc:
        logger.exception("Outline generation failed for deck %s", deck_id)
        deck.status = DeckStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail=f"Outline generation failed: {exc}",
        ) from exc

    deck.outline_json = [s.model_dump(mode="json") for s in outline]
    deck.status = DeckStatus.OUTLINE_READY
    await db.commit()

    return OutlineResponse(
        deck_id=deck_id,
        status=deck.status,
        outline=outline,
        slide_count=len(outline),
        message=f"Outline generated with {len(outline)} slides.",
    )


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/generate-slides — SSE streaming slide generation
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/generate-slides")
async def generate_slides(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    slide_gen: SlideGenerator = Depends(get_slide_generator),
):
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    allowed = (DeckStatus.OUTLINE_READY, DeckStatus.GENERATING_SLIDES)
    if deck.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot generate slides in state '{deck.status}'. "
            f"Deck must be in '{DeckStatus.OUTLINE_READY}' state.",
        )

    if not deck.outline_json:
        raise HTTPException(status_code=409, detail="No outline found on deck")

    if not deck.retrieval_json:
        raise HTTPException(
            status_code=409, detail="No retrieval data found on deck"
        )

    deck.status = DeckStatus.GENERATING_SLIDES
    await db.commit()

    prefs = TeacherPreferences.model_validate(deck.preferences_json)
    retrieval_data = deck.retrieval_json

    async def event_stream():
        async with async_session() as stream_db:
            try:
                stream_deck = await crud.get_deck(stream_db, deck_id)
                async for event in slide_gen.generate_all_slides(
                    stream_deck, retrieval_data, prefs, stream_db,
                ):
                    data = event["data"]
                    if event["event"] == "slide_content":
                        data = dict(data)
                        if "body" in data:
                            data["body"] = _strip_emphasis(data.get("body", ""))
                        if "bullet_points" in data:
                            data["bullet_points"] = [
                                _strip_emphasis(b)
                                for b in data.get("bullet_points", [])
                            ]
                    yield {
                        "event": event["event"],
                        "data": json.dumps(data),
                    }
            except Exception as exc:
                logger.exception(
                    "Slide generation stream failed for deck %s", deck_id,
                )
                try:
                    stream_deck = await crud.get_deck(stream_db, deck_id)
                    if stream_deck:
                        stream_deck.status = DeckStatus.FAILED
                        await stream_db.commit()
                except Exception:
                    logger.exception(
                        "Failed to update deck %s status after stream error",
                        deck_id,
                    )
                yield {
                    "event": "generation_error",
                    "data": json.dumps(
                        {"slide_id": "", "error": f"Stream failed: {exc}"}
                    ),
                }

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# GET /api/decks/{deck_id}/slides — all generated slides (non-streaming)
# ---------------------------------------------------------------------------


@router.get("/decks/{deck_id}/slides", response_model=SlidesListResponse)
async def get_slides(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SlidesListResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    slides = await crud.get_slides_by_deck(db, deck_id)
    return SlidesListResponse(
        deck_id=deck_id,
        slides=[
            SlideItem(
                slide_id=s.slide_id,
                position=s.position,
                title=s.title,
                body=_strip_emphasis(s.body),
                bullet_points=[_strip_emphasis(b) for b in (s.bullet_points or [])],
                table_data=s.table_data,
                speaker_notes=s.speaker_notes,
                layout_hint=s.layout_hint,
            )
            for s in slides
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/decks/{deck_id}/generation-status — resume helper
# ---------------------------------------------------------------------------


@router.get(
    "/decks/{deck_id}/generation-status",
    response_model=GenerationStatusResponse,
)
async def generation_status(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> GenerationStatusResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    outline = deck.outline_json or []
    slides = await crud.get_slides_by_deck(db, deck_id)
    generated_ids = {s.slide_id for s in slides}

    return GenerationStatusResponse(
        deck_id=deck_id,
        status=deck.status,
        total=len(outline),
        generated=len(generated_ids),
        pending=[
            s["id"] for s in outline if s.get("id") not in generated_ids
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/decks/{deck_id}/slides/{slide_id} — single slide
# ---------------------------------------------------------------------------


@router.get("/decks/{deck_id}/slides/{slide_id}", response_model=SlideItem)
async def get_single_slide(
    deck_id: UUID,
    slide_id: str,
    db: AsyncSession = Depends(get_db),
) -> SlideItem:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    slide = await crud.get_slide_by_slide_id(db, deck_id, slide_id)
    if slide is None:
        raise HTTPException(status_code=404, detail="Slide not found")

    return SlideItem(
        slide_id=slide.slide_id,
        position=slide.position,
        title=slide.title,
        body=_strip_emphasis(slide.body),
        bullet_points=[_strip_emphasis(b) for b in (slide.bullet_points or [])],
        table_data=slide.table_data,
        speaker_notes=slide.speaker_notes,
        layout_hint=slide.layout_hint,
    )
