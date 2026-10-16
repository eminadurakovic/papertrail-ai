import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from tests.factories import make_paper
from tests.pdf_fakes import FakePdfServer, make_pdf, numbered_words


def test_process_returns_summary_and_passages_become_available(
    client: TestClient, db_session: Session, fake_pdf_server: FakePdfServer
) -> None:
    paper = make_paper(db_session)
    fake_pdf_server.files[paper.pdf_url] = make_pdf([numbered_words(400)])

    response = client.post(f"/papers/{paper.id}/process")

    assert response.status_code == 200
    body = response.json()
    assert body["paper_id"] == paper.id
    assert body["ingestion_status"] == "processed"
    assert body["page_count"] == 1
    assert body["extracted_characters"] == len(" ".join(numbered_words(400)))

    passages = client.get(f"/papers/{paper.id}/passages").json()
    assert len(passages) == body["passage_count"]
    assert [p["position"] for p in passages] == list(range(len(passages)))
    assert len(passages[0]["text"].split()) == get_settings().chunk_size_words
    assert passages[0]["page"] == 1
    assert passages[0]["section"] is None


def test_passages_of_unprocessed_paper_are_empty(client: TestClient, db_session: Session) -> None:
    paper = make_paper(db_session)

    assert client.get(f"/papers/{paper.id}/passages").json() == []


def test_unknown_paper_returns_404(client: TestClient) -> None:
    assert client.post("/papers/999999/process").status_code == 404
    assert client.get("/papers/999999/passages").status_code == 404


def test_document_without_text_returns_422_and_records_error(
    client: TestClient, db_session: Session, fake_pdf_server: FakePdfServer
) -> None:
    paper = make_paper(db_session)
    fake_pdf_server.files[paper.pdf_url] = make_pdf([[]])

    response = client.post(f"/papers/{paper.id}/process")

    assert response.status_code == 422
    assert "Scanned" in response.json()["detail"]
    detail = client.get(f"/papers/{paper.id}").json()
    assert detail["ingestion_status"] == "failed"
    assert detail["processing_error"] == response.json()["detail"]


def test_missing_pdf_returns_502(client: TestClient, db_session: Session) -> None:
    paper = make_paper(db_session)  # nothing served at its pdf_url -> HTTP 404 upstream

    assert client.post(f"/papers/{paper.id}/process").status_code == 502


def test_network_error_returns_503(
    client: TestClient, db_session: Session, fake_pdf_server: FakePdfServer
) -> None:
    paper = make_paper(db_session)
    fake_pdf_server.error = httpx.ConnectError("offline")

    response = client.post(f"/papers/{paper.id}/process")

    assert response.status_code == 503
    assert "Traceback" not in response.text
