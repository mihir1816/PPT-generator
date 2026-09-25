import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk


class FeedbackRound(Base, TimestampMixin):
    __tablename__ = "feedback_rounds"

    id: Mapped[uuid.UUID] = uuid_pk()
    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_type: Mapped[str] = mapped_column(String, nullable=False)
    raw_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_actions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    affected_slide_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    outline_snapshot_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    slides_snapshot_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    syllabus_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    deck: Mapped["Deck"] = relationship(back_populates="feedback_rounds")  # noqa: F821
