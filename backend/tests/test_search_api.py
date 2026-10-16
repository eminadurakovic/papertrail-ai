import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Paper, Passage
from tests.factories import make_paper
from tests.fake_embedder import FakeEmbedder

TEXTS = [
    "attention mechanisms relate positions in a sequence",
    "the encoder maps input tokens to representations",
    "training used eight gpus for three days",
    "label smoothing improved bleu scores",
    "positional encodings use sine and cosine functions",
    "the decoder generates one token at a time",
    "dropout is applied to each sub layer",
]


@pytest.fixture
def indexed_paper(db_session: Session, fake_embedder: FakeEmbedder) -> Paper:
    paper = make_paper(db_session, "2401.00001", title="Indexed Paper")
    for position, text in enumerate(TEXTS):
        db_session.add(
            Passage(
                paper_id=paper.id,
                position=position,
                text=text,
                page=1,
                embedding=fake_embedder.vector(text).tolist(),
            )
        )
    db_session.commit()
    return paper


def search(client: TestClient, **body: object) -> tuple[int, dict[str, object]]:
    response = client.post("/search", json=body)
    return response.status_code, response.json()


def test_search_returns_ranked_results(client: TestClient, indexed_paper: Paper) -> None:
    status_code, body = search(client, query="how do positional encodings use sine", limit=3)

    assert status_code == 200
    assert body["query"] == "how do positional encodings use sine"
    results = body["results"]
    assert isinstance(results, list) and len(results) == 3
    assert results[0]["text"] == TEXTS[4]
    assert set(results[0]) == {
        "paper_id",
        "title",
        "arxiv_id",
        "passage_id",
        "position",
        "page",
        "text",
        "score",
    }
    assert results[0]["title"] == "Indexed Paper"
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_default_limit_is_five(client: TestClient, indexed_paper: Paper) -> None:
    _, body = search(client, query="tokens")

    assert len(body["results"]) == 5  # type: ignore[arg-type]


def test_paper_filter(client: TestClient, db_session: Session, indexed_paper: Paper) -> None:
    other = make_paper(db_session, "2401.00002")

    _, only_other = search(client, query="attention", paper_ids=[other.id])
    _, only_indexed = search(client, query="attention", paper_ids=[indexed_paper.id])

    assert only_other["results"] == []  # exists, but has no indexed passages
    assert len(only_indexed["results"]) == 5  # type: ignore[arg-type]


def test_no_indexed_passages_returns_empty_results(client: TestClient) -> None:
    status_code, body = search(client, query="anything at all")

    assert status_code == 200
    assert body["results"] == []


def test_unknown_paper_returns_404(client: TestClient, indexed_paper: Paper) -> None:
    status_code, body = search(client, query="attention", paper_ids=[999999])

    assert status_code == 404
    assert body["detail"] == "Unknown paper IDs: 999999"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"query": ""},
        {"query": "    "},
        {"query": "x" * 1001},
        {"query": "ok", "limit": 0},
        {"query": "ok", "limit": 51},
        {"query": "ok", "paper_ids": "1"},
        {"query": 42},
    ],
)
def test_invalid_requests_return_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/search", json=body).status_code == 422


def test_query_is_stripped(client: TestClient, indexed_paper: Paper) -> None:
    _, body = search(client, query="   dropout   ")

    assert body["query"] == "dropout"
