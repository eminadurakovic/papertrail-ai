from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.paper import Paper


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Simplification: authors are identified by their exact name, so two different
    # people with the same name share one row. Good enough for a single-source app.
    name: Mapped[str] = mapped_column(String(300), unique=True)

    paper_links: Mapped[list[PaperAuthor]] = relationship(back_populates="author")


class PaperAuthor(Base):
    """Link table for the many-to-many Paper <-> Author relationship, with author order."""

    __tablename__ = "paper_authors"
    __table_args__ = (CheckConstraint("position >= 0", name="position_non_negative"),)

    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int]  # 0 = first author

    paper: Mapped[Paper] = relationship(back_populates="author_links")
    author: Mapped[Author] = relationship(back_populates="paper_links")
