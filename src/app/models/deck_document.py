import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk


class DeckDocument(Base, TimestampMixin):
    __tablename__ = "deck_documents"
    __table_args__ = (
        UniqueConstraint("deck_id", "document_id", name="uq_deck_document"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    deck: Mapped["Deck"] = relationship(back_populates="deck_documents")  # noqa: F821
    document: Mapped["Document"] = relationship()  # noqa: F821
