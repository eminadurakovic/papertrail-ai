import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Paper
from app.services import ingestion
from app.services.arxiv import ArxivMetadata
from tests.arxiv_fakes import FakeArxiv


def test_import_creates_paper(client: TestClient) -> None:
    response = client.post("/papers/import", json={"arxiv_id": "1706.03762"})

    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["paper"]["arxiv_id"] == "1706.03762"
    assert body["paper"]["title"] == "Attention Is All You Need"
    assert body["paper"]["ingestion_status"] == "imported"
    assert body["paper"]["authors"][0]["name"] == "Ashish Vaswani"


def test_second_import_returns_existing_paper_with_200(client: TestClient) -> None:
    first = client.post("/papers/import", json={"arxiv_id": "1706.03762"}).json()

    response = client.post("/papers/import", json={"arxiv_id": "1706.03762v7"})

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert response.json()["paper"]["id"] == first["paper"]["id"]
    assert len(client.get("/papers").json()) == 1


def test_imported_paper_is_visible_in_paper_endpoints(client: TestClient) -> None:
    paper_id = client.post("/papers/import", json={"arxiv_id": "1706.03762"}).json()["paper"]["id"]

    assert client.get("/papers").json()[0]["id"] == paper_id
    assert client.get(f"/papers/{paper_id}").json()["abstract"].startswith("The dominant")


@pytest.mark.parametrize(
    ("arxiv_id", "expected_status"),
    [
        ("not-an-id", 422),
        ("2501.99999", 404),
    ],
)
def test_import_errors_from_input(client: TestClient, arxiv_id: str, expected_status: int) -> None:
    response = client.post("/papers/import", json={"arxiv_id": arxiv_id})

    assert response.status_code == expected_status
    assert isinstance(response.json()["detail"], str)


def test_network_error_returns_503(client: TestClient, fake_arxiv: FakeArxiv) -> None:
    fake_arxiv.error = httpx.ConnectError("connection refused")

    response = client.post("/papers/import", json={"arxiv_id": "1706.03762"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Could not reach arXiv. Check your connection."}


def test_malformed_arxiv_response_returns_502(client: TestClient, fake_arxiv: FakeArxiv) -> None:
    fake_arxiv.feeds["1706.03762"] = b"<html>maintenance</html"

    response = client.post("/papers/import", json={"arxiv_id": "1706.03762"})

    assert response.status_code == 502


def test_database_failure_returns_500_without_internals(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_store(db: Session, metadata: ArxivMetadata) -> Paper:
        raise OperationalError("INSERT INTO papers ...", {}, Exception("secret internals"))

    monkeypatch.setattr(ingestion, "_store_paper", broken_store)

    response = client.post("/papers/import", json={"arxiv_id": "1706.03762"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Could not save the paper. Try again later."}
    assert "Traceback" not in response.text
    assert "secret internals" not in response.text


@pytest.mark.parametrize(
    "payload",
    [{}, {"arxiv_id": ""}, {"arxiv_id": 1706.03762}, {"arxiv_id": "x" * 101}],
)
def test_invalid_request_body_returns_422(client: TestClient, payload: object) -> None:
    assert client.post("/papers/import", json=payload).status_code == 422
