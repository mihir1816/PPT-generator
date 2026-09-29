import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_exporter, get_storage_service
from app.schemas.common import DeckStatus
from app.schemas.deck import TeacherPreferences
from app.services import crud
from app.services.exporter import PPTXExporter
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["export"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ExportResponse(BaseModel):
    deck_id: UUID
    download_url: str
    filename: str
    file_size: int


# ---------------------------------------------------------------------------
# POST /api/decks/{deck_id}/export — generate and upload PPTX
# ---------------------------------------------------------------------------


@router.post("/decks/{deck_id}/export", response_model=ExportResponse)
async def export_deck(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    exporter: PPTXExporter = Depends(get_exporter),
    storage: StorageService = Depends(get_storage_service),
) -> ExportResponse:
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    if deck.status not in (DeckStatus.COMPLETED, DeckStatus.OUTLINE_READY):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot export deck in state '{deck.status}'. "
            f"Deck must have generated slides.",
        )

    slides = await crud.get_slides_by_deck(db, deck_id)
    if not slides:
        raise HTTPException(status_code=409, detail="No slides to export")

    prefs = TeacherPreferences.model_validate(deck.preferences_json)
    deck_title = deck.title or "Presentation"

    try:
        pptx_bytes = exporter.export_deck(slides, preferences=prefs.model_dump(), title=deck_title)
    except Exception as exc:
        logger.exception("PPTX export failed for deck %s", deck_id)
        raise HTTPException(status_code=502, detail=f"Export failed: {exc}") from exc

    filename = PPTXExporter.make_filename(deck_title)
    minio_key = f"exports/{deck_id}/{filename}"

    try:
        await storage.upload_bytes(
            pptx_bytes,
            minio_key,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception as exc:
        logger.exception("Failed to upload PPTX to MinIO for deck %s", deck_id)
        raise HTTPException(status_code=502, detail=f"Upload failed: {exc}") from exc

    download_url = await storage.get_presigned_url(minio_key, expires=3600)

    return ExportResponse(
        deck_id=deck_id,
        download_url=download_url,
        filename=filename,
        file_size=len(pptx_bytes),
    )


# ---------------------------------------------------------------------------
# GET /api/decks/{deck_id}/export/download — direct download
# ---------------------------------------------------------------------------


@router.get("/decks/{deck_id}/export/download")
async def download_deck(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    exporter: PPTXExporter = Depends(get_exporter),
):
    deck = await crud.get_deck(db, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    slides = await crud.get_slides_by_deck(db, deck_id)
    if not slides:
        raise HTTPException(status_code=409, detail="No slides to export")

    prefs = TeacherPreferences.model_validate(deck.preferences_json)
    deck_title = deck.title or "Presentation"

    try:
        pptx_bytes = exporter.export_deck(slides, preferences=prefs.model_dump(), title=deck_title)
    except Exception as exc:
        logger.exception("PPTX export failed for deck %s", deck_id)
        raise HTTPException(status_code=502, detail=f"Export failed: {exc}") from exc

    filename = PPTXExporter.make_filename(deck_title)

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
