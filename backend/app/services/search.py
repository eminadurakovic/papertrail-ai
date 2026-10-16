"""Exact cosine-similarity search over passage embeddings (score = 1 - cosine distance)."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, Passage
from app.services.embeddings import Embedder


class UnknownPapersError(Exception):
    def __init__(self, paper_ids: list[int]) -> None:
        super().__init__(f"Unknown paper IDs: {', '.join(map(str, paper_ids))}")
        self.paper_ids = paper_ids


@dataclass(frozen=True)
class SearchHit:
    passage_id: int
    paper_id: int
    paper_title: str
    arxiv_id: str
    position: int
    page: int | None
    text: str
    score: float


def semantic_search(
    db: Session, embedder: Embedder, query: str, *, limit: int, paper_ids: Sequence[int] = ()
) -> list[SearchHit]:
    """Embed the query and return the `limit` most similar passages."""
    _check_papers_exist(db, paper_ids)
    query_vector = embedder.embed_query(query)
    return search_by_vector(db, query_vector.tolist(), limit=limit, paper_ids=paper_ids)


def search_by_vector(
    db: Session, query_vector: list[float], *, limit: int, paper_ids: Sequence[int] = ()
) -> list[SearchHit]:
    """Nearest passages to a given vector. Passages without an embedding are skipped."""
    distance = Passage.embedding.cosine_distance(query_vector)
    statement = (
        select(
            Passage.id,
            Passage.paper_id,
            Paper.title,
            Paper.arxiv_id,
            Passage.position,
            Passage.page,
            Passage.text,
            (1 - distance).label("score"),
        )
        .join(Paper, Paper.id == Passage.paper_id)
        .where(Passage.embedding.is_not(None))
        .order_by(distance, Passage.id)
        .limit(limit)
    )
    if paper_ids:
        statement = statement.where(Passage.paper_id.in_(paper_ids))

    return [
        SearchHit(
            passage_id=row.id,
            paper_id=row.paper_id,
            paper_title=row.title,
            arxiv_id=row.arxiv_id,
            position=row.position,
            page=row.page,
            text=row.text,
            score=float(row.score),
        )
        for row in db.execute(statement)
    ]


def _check_papers_exist(db: Session, paper_ids: Sequence[int]) -> None:
    if not paper_ids:
        return
    found = set(db.scalars(select(Paper.id).where(Paper.id.in_(paper_ids))))
    missing = sorted(set(paper_ids) - found)
    if missing:
        raise UnknownPapersError(missing)
