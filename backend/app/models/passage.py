from __future__ import annotations

from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.paper import Paper

# Output size of the embedding model (bge-small-en-v1.5). Changing the model to one
# with a different size requires a migration and re-indexing every paper.
EMBEDDING_DIMENSION = 384


class Passage(TimestampMixin, Base):
    """A chunk of a paper's text, plus its embedding once the paper is indexed."""

    __tablename__ = "passages"
    __table_args__ = (
        # Each position appears at most once per paper, giving passages a stable order.
        UniqueConstraint("paper_id", "position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    position: Mapped[int]  # 0-based index of the passage within its paper
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None]
    section: Mapped[str | None] = mapped_column(String(300))
    # NULL until the paper is indexed. Deferred: only loaded when explicitly requested.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), deferred=True
    )

    paper: Mapped[Paper] = relationship(back_populates="passages")
