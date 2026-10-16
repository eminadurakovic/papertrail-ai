"""Import arXiv metadata into the database.

Idempotent: an existing paper is returned as-is, and unique constraints catch concurrent
duplicate imports."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Author, IngestionRun, IngestionRunStatus, Paper, PaperAuthor
from app.services.arxiv import ArxivClient, ArxivError, ArxivMetadata, normalize_arxiv_id

logger = logging.getLogger(__name__)


class IngestionDatabaseError(Exception):
    """The database failed while importing. The message is safe to show to users."""


@dataclass(frozen=True)
class ImportResult:
    paper: Paper
    created: bool  # False when the paper was already stored


def import_paper(db: Session, requested_id: str, arxiv: ArxivClient) -> ImportResult:
    """Import one paper by arXiv ID. Raises ArxivError or IngestionDatabaseError on failure."""
    try:
        run = _start_run(db, requested_id)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not create ingestion run for %r", requested_id)
        raise IngestionDatabaseError("The database is unavailable. Try again later.") from exc

    try:
        result = _fetch_and_store(db, requested_id, arxiv)
        _finish_run(db, run, IngestionRunStatus.SUCCEEDED)  # commits paper + run together
        return result
    except ArxivError as exc:
        db.rollback()
        _record_failure(db, run, str(exc))
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while importing %r", requested_id)
        _record_failure(db, run, "Database error while saving the paper.")
        raise IngestionDatabaseError("Could not save the paper. Try again later.") from exc


def _fetch_and_store(db: Session, requested_id: str, arxiv: ArxivClient) -> ImportResult:
    arxiv_id = normalize_arxiv_id(requested_id)

    existing = _find_paper(db, arxiv_id)
    if existing is not None:
        return ImportResult(paper=existing, created=False)

    metadata = arxiv.fetch_metadata(arxiv_id)
    try:
        # Savepoint, so a concurrent insert of the same paper only rolls back this block.
        with db.begin_nested():
            paper = _store_paper(db, metadata)
    except IntegrityError:
        existing = _find_paper(db, arxiv_id)
        if existing is None:
            raise
        return ImportResult(paper=existing, created=False)
    return ImportResult(paper=paper, created=True)


def _find_paper(db: Session, arxiv_id: str) -> Paper | None:
    return db.scalars(select(Paper).where(Paper.arxiv_id == arxiv_id)).one_or_none()


def _store_paper(db: Session, metadata: ArxivMetadata) -> Paper:
    author_ids = _get_or_create_author_ids(db, metadata.authors)
    paper = Paper(
        arxiv_id=metadata.arxiv_id,
        title=metadata.title,
        abstract=metadata.abstract,
        published_date=metadata.published_date,
        source_url=metadata.source_url,
        pdf_url=metadata.pdf_url,
        author_links=[
            PaperAuthor(author_id=author_id, position=position)
            for position, author_id in enumerate(author_ids)
        ],
    )
    db.add(paper)
    db.flush()
    return paper


def _get_or_create_author_ids(db: Session, names: list[str]) -> list[int]:
    """Author IDs in the order of `names`; inserts missing ones (ON CONFLICT DO NOTHING)."""
    db.execute(
        pg_insert(Author)
        .values([{"name": name} for name in names])
        .on_conflict_do_nothing(index_elements=[Author.name])
    )
    rows = db.execute(select(Author.id, Author.name).where(Author.name.in_(names))).all()
    id_by_name = {name: author_id for author_id, name in rows}
    return [id_by_name[name] for name in names]


def _start_run(db: Session, requested_id: str) -> IngestionRun:
    # Commit now so the attempt is recorded even if the import fails.
    run = IngestionRun(requested_arxiv_id=requested_id.strip()[:100])
    db.add(run)
    db.commit()
    return run


def _finish_run(
    db: Session, run: IngestionRun, status: IngestionRunStatus, error: str | None = None
) -> None:
    run.status = status
    run.error_message = error
    run.completed_at = datetime.now(UTC)
    db.commit()


def _record_failure(db: Session, run: IngestionRun, message: str) -> None:
    """Best effort: if the database itself is broken, recording the failure can fail too."""
    try:
        _finish_run(db, run, IngestionRunStatus.FAILED, message)
    except SQLAlchemyError:
        db.rollback()
        # Don't read run attributes here; after a rollback that would query the broken DB.
        logger.exception("Could not record failed ingestion run (%s)", message)
