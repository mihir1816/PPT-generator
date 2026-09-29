import uuid

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk
from app.schemas.common import DeckStatus


class Deck(Base, TimestampMixin):
    __tablename__ = "decks"

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="Presentation")
    teacher_query: Mapped[str] = mapped_column(Text, nullable=False)
    preferences_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    syllabus_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    syllabus_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=DeckStatus.PENDING.value
    )
    outline_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    retrieval_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    document_map: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    slides: Mapped[list["Slide"]] = relationship(  # noqa: F821
        back_populates="deck", cascade="all, delete-orphan"
    )
    feedback_rounds: Mapped[list["FeedbackRound"]] = relationship(  # noqa: F821
        back_populates="deck", cascade="all, delete-orphan"
    )
    deck_documents: Mapped[list["DeckDocument"]] = relationship(  # noqa: F821
        back_populates="deck", cascade="all, delete-orphan"
    )
