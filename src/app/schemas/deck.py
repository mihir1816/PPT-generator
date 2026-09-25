from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DeckStatus
from app.schemas.syllabus import TopicSyllabus


class SlideType(StrEnum):
    TITLE = "title"
    CONTENT = "content"
    SECTION_HEADER = "section_header"
    TABLE = "table"
    TABLE_CONTINUATION = "table_continuation"
    SUMMARY = "summary"
    CLOSING = "closing"


class SlideStatus(StrEnum):
    PENDING = "pending"
    NEEDS_REGENERATION = "needs_regeneration"
    GENERATED = "generated"


class LayoutHint(StrEnum):
    TITLE = "title"
    BULLET = "bullet"
    TWO_COLUMN = "two_column"
    TABLE = "table"
    SECTION_HEADER = "section_header"
    IMAGE_PLACEHOLDER = "image_placeholder"


class TeacherPreferences(BaseModel):
    audience_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    tone: Literal["formal", "creative"] = "formal"
    content_mode: Literal["grounded", "mixed"] = "grounded"
    slide_count_hint: int | None = None
    additional_instructions: str | None = None


class TableData(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class SlideOutline(BaseModel):
    id: str
    position: int
    type: SlideType
    title: str
    key_points: list[str] = Field(default_factory=list)
    layout_hint: LayoutHint = LayoutHint.BULLET
    source_chunk_ids: list[str] = Field(default_factory=list)
    spans_slides: bool = False
    table_continuation: bool = False
    status: SlideStatus = SlideStatus.PENDING


class SlideContent(BaseModel):
    slide_id: str
    title: str
    body: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    table_data: TableData | None = None
    speaker_notes: str = ""
    layout_hint: LayoutHint = LayoutHint.BULLET


class DeckState(BaseModel):
    id: UUID
    teacher_query: str
    preferences: TeacherPreferences
    syllabus: TopicSyllabus | None = None
    syllabus_status: str = "pending"
    status: DeckStatus = DeckStatus.PENDING
    outline: list[SlideOutline] = Field(default_factory=list)
    version: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
