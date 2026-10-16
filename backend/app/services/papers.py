"""Read queries for papers."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from app.models import Paper, PaperAuthor, Passage


def _with_authors() -> LoaderOption:
    # Load author links and authors in two extra queries instead of one per paper (N+1).
    return selectinload(Paper.author_links).selectinload(PaperAuthor.author)


def list_papers(db: Session, *, limit: int, offset: int) -> list[Paper]:
    """Newest papers first."""
    statement = (
        select(Paper).options(_with_authors()).order_by(Paper.id.desc()).limit(limit).offset(offset)
    )
    return list(db.scalars(statement))


def get_paper(db: Session, paper_id: int) -> Paper | None:
    return db.get(Paper, paper_id, options=[_with_authors()])


def passage_counts(db: Session, paper_ids: list[int]) -> dict[int, int]:
    """Number of passages per paper, in one grouped query (papers without passages are absent)."""
    if not paper_ids:
        return {}
    rows = db.execute(
        select(Passage.paper_id, func.count())
        .where(Passage.paper_id.in_(paper_ids))
        .group_by(Passage.paper_id)
    )
    return {paper_id: count for paper_id, count in rows}


def list_passages(db: Session, paper_id: int) -> list[Passage]:
    statement = select(Passage).where(Passage.paper_id == paper_id).order_by(Passage.position)
    return list(db.scalars(statement))
