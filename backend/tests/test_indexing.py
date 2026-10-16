import numpy as np
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.models import Paper, PaperStatus, Passage
from app.models.passage import EMBEDDING_DIMENSION
from app.services import indexing, processing
from app.services.embeddings import EmbeddingError
from tests.factories import make_paper
from tests.fake_embedder import FakeEmbedder
from tests.pdf_fakes import FakePdfServer, make_pdf


@pytest.fixture
def paper(db_session: Session) -> Paper:
    paper = make_paper(db_session)
    db_session.add_all(
        [
            Passage(paper_id=paper.id, position=0, text="transformers use attention"),
            Passage(paper_id=paper.id, position=1, text="recurrent networks are slow"),
            Passage(paper_id=paper.id, position=2, text="we evaluate on translation"),
        ]
    )
    paper.ingestion_status = PaperStatus.PROCESSED
    db_session.commit()
    return paper


def stored_embeddings(db: Session, paper: Paper) -> list[tuple[str, list[float] | None]]:
    db.expire_all()  # read what is really in the database
    rows = db.execute(
        select(Passage.text, Passage.embedding)
        .where(Passage.paper_id == paper.id)
        .order_by(Passage.position)
    )
    return [(row.text, row.embedding) for row in rows]


def test_indexing_stores_one_vector_per_passage(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder
) -> None:
    result = indexing.index_paper(db_session, paper.id, fake_embedder)

    assert result.indexed_passages == 3
    assert result.dimension == EMBEDDING_DIMENSION
    assert result.model_name == "fake-bag-of-words"
    assert paper.ingestion_status == PaperStatus.INDEXED
    for passage_text, embedding in stored_embeddings(db_session, paper):
        assert embedding is not None
        assert len(embedding) == EMBEDDING_DIMENSION
        # Each passage keeps the vector of its own text (no mix-ups between rows).
        assert np.allclose(embedding, fake_embedder.vector(passage_text))
        assert np.isclose(np.linalg.norm(embedding), 1.0, atol=1e-5)


def test_reindexing_overwrites_embeddings(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder
) -> None:
    indexing.index_paper(db_session, paper.id, fake_embedder)
    before = [vector for _, vector in stored_embeddings(db_session, paper)]

    fake_embedder.salt = "new-model"  # every vector changes, like switching models
    indexing.index_paper(db_session, paper.id, fake_embedder)
    after = stored_embeddings(db_session, paper)

    assert len(after) == 3  # no duplicate passages
    for (passage_text, new), old in zip(after, before, strict=True):
        assert new is not None and old is not None
        assert not np.allclose(new, old)
        assert np.allclose(new, fake_embedder.vector(passage_text))


def test_reindexing_with_same_model_is_stable(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder
) -> None:
    indexing.index_paper(db_session, paper.id, fake_embedder)
    first = [v for _, v in stored_embeddings(db_session, paper)]
    indexing.index_paper(db_session, paper.id, fake_embedder)
    second = [v for _, v in stored_embeddings(db_session, paper)]

    assert first == second


@pytest.mark.parametrize("wrong_dimension", [128, 768])
def test_wrong_vector_dimension_is_rejected(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder, wrong_dimension: int
) -> None:
    fake_embedder.output_dimension = wrong_dimension

    with pytest.raises(EmbeddingError, match="shape"):
        indexing.index_paper(db_session, paper.id, fake_embedder)

    assert all(vector is None for _, vector in stored_embeddings(db_session, paper))
    assert paper.ingestion_status == PaperStatus.FAILED
    assert paper.processing_error is not None and "shape" in paper.processing_error


def test_database_also_rejects_wrong_dimension(db_session: Session, paper: Paper) -> None:
    """The vector(384) column is a second safety net, independent of application code."""
    with pytest.raises(DataError, match="expected 384 dimensions"):
        db_session.execute(
            text("UPDATE passages SET embedding = :v WHERE paper_id = :id"),
            {"v": str([0.1] * 10), "id": paper.id},
        )


def test_model_failure_marks_paper_failed_and_keeps_old_embeddings(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder
) -> None:
    indexing.index_paper(db_session, paper.id, fake_embedder)
    fake_embedder.fail_with = EmbeddingError("The embedding model failed to process the text.")

    with pytest.raises(EmbeddingError):
        indexing.index_paper(db_session, paper.id, fake_embedder)

    assert paper.ingestion_status == PaperStatus.FAILED
    assert all(vector is not None for _, vector in stored_embeddings(db_session, paper))


def test_paper_without_passages_cannot_be_indexed(
    db_session: Session, fake_embedder: FakeEmbedder
) -> None:
    paper = make_paper(db_session, "2401.00002")

    with pytest.raises(indexing.NotProcessedError):
        indexing.index_paper(db_session, paper.id, fake_embedder)

    assert fake_embedder.calls == 0
    assert paper.ingestion_status == PaperStatus.IMPORTED  # nothing changed


def test_unknown_paper_raises_not_found(db_session: Session, fake_embedder: FakeEmbedder) -> None:
    with pytest.raises(processing.PaperNotFoundError):
        indexing.index_paper(db_session, 999_999, fake_embedder)


def test_database_failure_rolls_back_and_marks_failed(
    db_session: Session,
    paper: Paper,
    fake_embedder: FakeEmbedder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pgvector refuses NaN values, so the UPDATE fails inside Postgres itself.
    def nan_vectors(texts: list[str]) -> np.ndarray:
        return np.full((len(texts), EMBEDDING_DIMENSION), np.nan, dtype=np.float32)

    monkeypatch.setattr(fake_embedder, "embed_documents", nan_vectors)

    with pytest.raises(indexing.IndexingDatabaseError) as raised:
        indexing.index_paper(db_session, paper.id, fake_embedder)

    assert "NaN" not in str(raised.value)  # database details are not leaked
    db_session.refresh(paper)
    assert paper.ingestion_status == PaperStatus.FAILED
    assert paper.processing_error == "Database error while saving embeddings."
    assert all(vector is None for _, vector in stored_embeddings(db_session, paper))


def test_reprocessing_clears_embeddings_and_returns_to_processed(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder
) -> None:
    indexing.index_paper(db_session, paper.id, fake_embedder)
    server = FakePdfServer()
    server.files[paper.pdf_url] = make_pdf([["fresh text from the pdf"]])

    processing.process_paper(
        db_session, paper.id, server.downloader(), chunk_size=10, chunk_overlap=2
    )

    assert paper.ingestion_status == PaperStatus.PROCESSED
    assert stored_embeddings(db_session, paper) == [("fresh text from the pdf", None)]
