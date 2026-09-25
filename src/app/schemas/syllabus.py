from enum import StrEnum

from pydantic import BaseModel, Field


class SyllabusTopic(BaseModel):
    title: str
    subtopics: list[str] = Field(default_factory=list)
    depth_hint: str | None = None  # e.g. "brief", "detailed"
    notes: str | None = None


class TopicSyllabus(BaseModel):
    title: str
    topics: list[SyllabusTopic] = Field(default_factory=list)
    audience_level: str = "intermediate"
    estimated_slides: int | None = None


class SyllabusFeedbackAction(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    EXPAND = "expand"
    REORDER = "reorder"
    MODIFY = "modify"


class SyllabusFeedback(BaseModel):
    action: SyllabusFeedbackAction
    target_topic: str | None = None
    instruction: str
