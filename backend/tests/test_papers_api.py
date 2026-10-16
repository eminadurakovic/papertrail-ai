from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Passage
from tests.factories import make_paper


def test_list_papers_is_empty_initially(client: TestClient) -> None:
    response = client.get("/papers")

    assert response.status_code == 200
    assert response.json() == []


def test_list_papers_returns_newest_first_with_authors(
    client: TestClient, db_session: Session
) -> None:
    make_paper(db_session, "2401.00001", title="Older", authors=["Ada Lovelace"])
    make_paper(db_session, "2401.00002", title="Newer", authors=["Alan Turing", "Ada Lovelace"])

    body = client.get("/papers").json()

    assert [paper["title"] for paper in body] == ["Newer", "Older"]
    newest = body[0]
    assert newest["arxiv_id"] == "2401.00002"
    assert newest["published_date"] == "2024-01-15"
    assert newest["ingestion_status"] == "imported"
    assert [author["name"] for author in newest["authors"]] == ["Alan Turing", "Ada Lovelace"]
    assert "abstract" not in newest  # summaries stay small


def test_list_papers_supports_limit_and_offset(client: TestClient, db_session: Session) -> None:
    for number in range(1, 6):
        make_paper(db_session, f"2401.0000{number}")

    body = client.get("/papers", params={"limit": 2, "offset": 1}).json()

    assert [paper["arxiv_id"] for paper in body] == ["2401.00004", "2401.00003"]


def test_list_papers_rejects_invalid_limit(client: TestClient) -> None:
    assert client.get("/papers", params={"limit": 0}).status_code == 422
    assert client.get("/papers", params={"limit": 1000}).status_code == 422
    assert client.get("/papers", params={"offset": -1}).status_code == 422


def test_get_paper_returns_details(client: TestClient, db_session: Session) -> None:
    paper = make_paper(db_session, title="Detailed", authors=["Grace Hopper"])

    response = client.get(f"/papers/{paper.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == paper.id
    assert body["abstract"] == "Abstract of Detailed."
    assert body["source_url"] == "https://arxiv.org/abs/2401.00001"
    assert body["pdf_url"] == "https://arxiv.org/pdf/2401.00001"
    assert body["authors"][0]["name"] == "Grace Hopper"
    assert "created_at" in body and "updated_at" in body


def test_get_missing_paper_returns_404(client: TestClient) -> None:
    response = client.get("/papers/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Paper not found"}


def test_get_paper_with_non_numeric_id_returns_422(client: TestClient) -> None:
    assert client.get("/papers/abc").status_code == 422


def test_passage_counts_are_included(client: TestClient, db_session: Session) -> None:
    with_passages = make_paper(db_session, "2401.00001")
    make_paper(db_session, "2401.00002")
    db_session.add_all(
        [Passage(paper_id=with_passages.id, position=i, text=f"p{i}") for i in range(3)]
    )
    db_session.commit()

    counts = {p["arxiv_id"]: p["passage_count"] for p in client.get("/papers").json()}

    assert counts == {"2401.00001": 3, "2401.00002": 0}
    assert client.get(f"/papers/{with_passages.id}").json()["passage_count"] == 3


def test_info_exposes_configuration_without_secrets(client: TestClient) -> None:
    body = client.get("/info").json()

    assert body["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert body["embedding_dimension"] == 384
    assert body["llm_provider"] in {"none", "ollama"}
    assert 0 < body["rag_min_score"] <= 1
    assert "password" not in str(body).lower()
