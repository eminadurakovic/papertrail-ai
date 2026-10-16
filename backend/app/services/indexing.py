"""Embedding a paper's passages and storing the vectors in Postgres (pgvector).

Re-indexing is safe: every passage's embedding is simply overwritten, in one
transaction. Re-processing a paper replaces its passages, which removes
their embeddings, so the paper goes back to PROCESSED until it is indexed again.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Paper, PaperStatus, Passage
from app.services.embeddings import Embedder, EmbeddingError
from app.services.processing import PaperNotFoundError, mark_failed

logger = logging.getLogger(__name__)


class NotProcessedError(Exception):
    """The paper has no passages yet, so there is nothing to embed."""


class IndexingDatabaseError(Exception):
    """The database failed while saving embeddings. The message is safe to show to users."""


@dataclass(frozen=True)
class IndexResult:
    paper: Paper
    indexed_passages: int
    dimension: int
    model_name: str


def index_paper(db: Session, paper_id: int, embedder: Embedder) -> IndexResult:
    # Lock the paper so indexing can't interleave with re-processing of the same paper.
    paper = db.get(Paper, paper_id, with_for_update=True)
    if paper is None:
        raise PaperNotFoundError(f"Paper {paper_id} not found")

    passages = list(
        db.scalars(select(Passage).where(Passage.paper_id == paper_id).order_by(Passage.position))
    )
    if not passages:
        db.rollback()  # release the lock
        raise NotProcessedError("This paper has no passages yet. Process it first.")

    try:
        vectors = embedder.embed_documents([passage.text for passage in passages])
        _check_shape(vectors.shape, expected=(len(passages), embedder.dimension))
    except EmbeddingError as exc:
        db.rollback()
        mark_failed(db, paper, str(exc))
        raise

    try:
        for passage, vector in zip(passages, vectors, strict=True):
            passage.embedding = vector.tolist()
        paper.ingestion_status = PaperStatus.INDEXED
        paper.processing_error = None
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while saving embeddings for paper %s", paper_id)
        mark_failed(db, paper, "Database error while saving embeddings.")
        raise IndexingDatabaseError("Could not save the embeddings. Try again later.") from exc

    return IndexResult(
        paper=paper,
        indexed_passages=len(passages),
        dimension=embedder.dimension,
        model_name=embedder.model_name,
    )


def _check_shape(actual: tuple[int, ...], expected: tuple[int, int]) -> None:
    """Guard against a model that returns the wrong number or size of vectors."""
    if actual != expected:
        raise EmbeddingError(
            f"The embedding model returned vectors of shape {actual}, expected {expected}."
        )
