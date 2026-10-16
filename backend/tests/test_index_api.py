import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.main import app
from app.models import Passage
from app.services.embeddings import EmbeddingError, EmbeddingModelUnavailableError
from tests.factories import make_paper
from tests.fake_embedder import FakeEmbedder
from tests.pdf_fakes import FakePdfServer, make_pdf, numbered_words


def test_process_then_index(
    client: TestClient, db_session: Session, fake_pdf_server: FakePdfServer
) -> None:
    paper = make_paper(db_session)
    fake_pdf_server.files[paper.pdf_url] = make_pdf([numbered_words(400)])
    passage_count = client.post(f"/papers/{paper.id}/process").json()["passage_count"]

    response = client.post(f"/papers/{paper.id}/index")

    assert response.status_code == 200
    assert response.json() == {
        "paper_id": paper.id,
        "ingestion_status": "indexed",
        "indexed_passages": passage_count,
        "embedding_dimension": 384,
        "embedding_model": "fake-bag-of-words",
    }
    assert client.get(f"/papers/{paper.id}").json()["ingestion_status"] == "indexed"


def test_index_before_processing_returns_409(client: TestClient, db_session: Session) -> None:
    paper = make_paper(db_session)

    response = client.post(f"/papers/{paper.id}/index")

    assert response.status_code == 409
    assert "Process it first" in response.json()["detail"]


def test_index_unknown_paper_returns_404(client: TestClient) -> None:
    assert client.post("/papers/999999/index").status_code == 404


def test_model_failure_returns_500_with_safe_message(
    client: TestClient, db_session: Session, fake_embedder: FakeEmbedder
) -> None:
    paper = make_paper(db_session)
    db_session.add(Passage(paper_id=paper.id, position=0, text="some text"))
    db_session.commit()
    fake_embedder.fail_with = EmbeddingError("The embedding model failed to process the text.")

    response = client.post(f"/papers/{paper.id}/index")

    assert response.status_code == 500
    assert response.json() == {"detail": "The embedding model failed to process the text."}


def test_missing_model_returns_503(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_model(*args: object) -> None:
        raise EmbeddingModelUnavailableError("Embedding model files not found in /nowhere.")

    del app.dependency_overrides[deps.get_embedder]  # use the real dependency
    monkeypatch.setattr(deps, "_load_embedder", missing_model)
    paper = make_paper(db_session)

    response = client.post(f"/papers/{paper.id}/index")

    assert response.status_code == 503
    assert "not found" in response.json()["detail"]
