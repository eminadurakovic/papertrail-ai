"""Turning a stored paper into retrieval-ready passages.

Pipeline: download PDF -> extract + clean text per page -> chunk -> replace passages.

Re-processing is safe: old passages are deleted and new ones inserted in one
transaction, and chunking is deterministic, so the same PDF and settings give the
same passages. If processing fails, the paper is marked FAILED with the reason and
any passages from an earlier successful run are left untouched.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Paper, PaperStatus, Passage
from app.services.chunking import Chunk, chunk_pages
from app.services.pdf import PdfDownloader, ProcessingError, extract_pages

logger = logging.getLogger(__name__)


class PaperNotFoundError(Exception):
    pass


class ProcessingDatabaseError(Exception):
    """The database failed while saving passages. The message is safe to show to users."""


@dataclass(frozen=True)
class ProcessResult:
    paper: Paper
    page_count: int
    extracted_characters: int
    passage_count: int


def process_paper(
    db: Session,
    paper_id: int,
    downloader: PdfDownloader,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> ProcessResult:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise PaperNotFoundError(f"Paper {paper_id} not found")

    try:
        pdf_bytes = downloader.download(paper.pdf_url)
        pages = extract_pages(pdf_bytes)
    except ProcessingError as exc:
        mark_failed(db, paper, str(exc))
        raise

    chunks = chunk_pages(pages, size=chunk_size, overlap=chunk_overlap)
    try:
        _replace_passages(db, paper, chunks)
        paper.ingestion_status = PaperStatus.PROCESSED
        paper.processing_error = None
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while saving passages for paper %s", paper_id)
        mark_failed(db, paper, "Database error while saving passages.")
        raise ProcessingDatabaseError("Could not save the passages. Try again later.") from exc

    return ProcessResult(
        paper=paper,
        page_count=len(pages),
        # Pages are joined by a single space when chunking, so count those too.
        extracted_characters=len(" ".join(pages)),
        passage_count=len(chunks),
    )


def _replace_passages(db: Session, paper: Paper, chunks: list[Chunk]) -> None:
    # Lock the paper row so two simultaneous "process" requests run one after the other
    # instead of both inserting passages with the same positions.
    db.refresh(paper, with_for_update=True)

    # Delete first and flush, so the new rows never clash with the old ones on the
    # UNIQUE (paper_id, position) constraint.
    db.execute(delete(Passage).where(Passage.paper_id == paper.id))
    db.expire(paper, ["passages"])
    db.add_all(
        Passage(paper_id=paper.id, position=chunk.position, text=chunk.text, page=chunk.page)
        for chunk in chunks
    )
    db.flush()


def mark_failed(db: Session, paper: Paper, message: str) -> None:
    """Record why the last step failed. Best effort: if the database itself is broken,
    recording the failure can fail too. Shared by processing and indexing."""
    try:
        paper.ingestion_status = PaperStatus.FAILED
        paper.processing_error = message
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not record processing failure (%s)", message)
