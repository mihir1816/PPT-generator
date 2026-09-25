import uuid

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk


class Slide(Base, TimestampMixin):
    __tablename__ = "slides"
    __table_args__ = (
        Index("ix_slides_deck_position", "deck_id", "position"),
        UniqueConstraint("deck_id", "slide_id", name="uq_slide_deck_slide_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    bullet_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    table_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    speaker_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    layout_hint: Mapped[str] = mapped_column(String, nullable=False, default="bullet")
    outline_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    deck: Mapped["Deck"] = relationship(back_populates="slides")  # noqa: F821

    def to_dict(self) -> dict:
        return {
            "slide_id": self.slide_id,
            "position": self.position,
            "title": self.title,
            "body": self.body,
            "bullet_points": self.bullet_points or [],
            "table_data": self.table_data,
            "speaker_notes": self.speaker_notes,
            "layout_hint": self.layout_hint,
        }
