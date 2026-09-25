from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class TaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DeckStatus(StrEnum):
    """Single source of truth for all deck state transitions.

    Every session that changes deck status MUST use these values.
    """

    PENDING = "pending"
    GENERATING_SYLLABUS = "generating_syllabus"
    SYLLABUS_REVIEW = "syllabus_review"
    WAITING_FOR_INDEXING = "waiting_for_indexing"
    READY_FOR_RETRIEVAL = "ready_for_retrieval"
    RETRIEVING = "retrieving"
    RETRIEVAL_COMPLETE = "retrieval_complete"
    GENERATING_OUTLINE = "generating_outline"
    OUTLINE_READY = "outline_ready"
    GENERATING_SLIDES = "generating_slides"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadResponse(BaseModel):
    file_id: UUID
    filename: str
    status: TaskStatus


class GenerationStatus(BaseModel):
    status: str
    total: int
    generated: int
    pending: list[str]


class ErrorResponse(BaseModel):
    detail: str
    code: str


class HealthResponse(BaseModel):
    status: str
    version: str


class SystemStatusResponse(BaseModel):
    llm_available: bool
    qdrant: str
    valkey: str
    minio: str


class StatusOnlyResponse(BaseModel):
    status: str
    message: str | None = None


class TimestampedModel(BaseModel):
    created_at: datetime
    updated_at: datetime
