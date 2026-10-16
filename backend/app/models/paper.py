from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.author import Author, PaperAuthor
    from app.models.passage import Passage


class PaperStatus(StrEnum):
    """Where a paper is in the pipeline."""

    IMPORTED = "imported"  # metadata stored (Stage 2)
    PROCESSED = "processed"  # PDF text extracted and chunked into passages (Stage 3)
    INDEXED = "indexed"  # passages have embeddings (Stage 4)
    FAILED = "failed"  # the last processing attempt failed


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    arxiv_id: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text)
    published_date: Mapped[date]
    source_url: Mapped[str] = mapped_column(String(500))
    pdf_url: Mapped[str] = mapped_column(String(500))
    ingestion_status: Mapped[PaperStatus] = mapped_column(
        # Stored as plain text with a CHECK constraint (not a native Postgres enum),
        # which keeps adding a new status a simple migration.
        Enum(
            PaperStatus,
            name="ingestion_status",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda statuses: [s.value for s in statuses],
        ),
        default=PaperStatus.IMPORTED,
        server_default=PaperStatus.IMPORTED.value,
    )
    # Why the last processing attempt failed (None if it succeeded or never ran).
    processing_error: Mapped[str | None] = mapped_column(Text)

    author_links: Mapped[list[PaperAuthor]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperAuthor.position",
    )
    passages: Mapped[list[Passage]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Passage.position",
    )

    @property
    def authors(self) -> list[Author]:
        """Authors in the order they appear on the paper."""
        return [link.author for link in self.author_links]
