import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import Settings
from app.main import app
from app.models import Paper, Passage
from app.services.llm import LLMError, LLMUnavailableError
from app.services.ollama import OllamaClient
from tests.factories import make_paper
from tests.fake_embedder import FakeEmbedder
from tests.fake_llm import FakeLLM

TEXT = "positional encodings use sine and cosine waves"


@pytest.fixture
def paper(db_session: Session, fake_embedder: FakeEmbedder) -> Paper:
    paper = make_paper(db_session, "1706.03762", title="Transformer")
    for position, text in enumerate([TEXT, "attention relates every token to every other"]):
        db_session.add(
            Passage(
                paper_id=paper.id,
                position=position,
                text=text,
                page=6,
                embedding=fake_embedder.vector(text).tolist(),
            )
        )
    db_session.commit()
    return paper


def test_answer_with_citations(
    client: TestClient, db_session: Session, paper: Paper, fake_llm: FakeLLM
) -> None:
    fake_llm.reply = "They use sine and cosine functions [1]."

    response = client.post("/ask", json={"question": TEXT})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "They use sine and cosine functions [1]."
    assert body["abstained"] is False
    assert body["abstention_reason"] is None
    assert body["best_score"] == pytest.approx(1.0)
    (citation,) = body["citations"]
    assert citation["number"] == 1
    assert citation["paper_id"] == paper.id
    assert citation["paper_title"] == "Transformer"
    assert citation["page"] == 6
    stored = db_session.get(Passage, citation["passage_id"])
    assert stored is not None
    assert stored.text == citation["passage_text"] == TEXT


def test_unrelated_question_abstains(client: TestClient, paper: Paper, fake_llm: FakeLLM) -> None:
    body = client.post("/ask", json={"question": "best sourdough bread recipe"}).json()

    assert body["abstained"] is True
    assert body["abstention_reason"] == "no_relevant_passages"
    assert body["answer"].startswith("I could not find enough evidence")
    assert body["citations"] == []
    assert fake_llm.prompts == []


def test_no_indexed_papers_abstains(client: TestClient) -> None:
    body = client.post("/ask", json={"question": "anything"}).json()

    assert body["abstained"] is True
    assert body["best_score"] is None


def test_paper_filter_is_applied(
    client: TestClient, db_session: Session, paper: Paper, fake_llm: FakeLLM
) -> None:
    other = make_paper(db_session, "1810.04805", title="BERT")

    body = client.post("/ask", json={"question": TEXT, "paper_ids": [other.id]}).json()

    assert body["abstained"] is True  # the matching passage belongs to another paper
    assert fake_llm.prompts == []


def test_unknown_paper_returns_404(client: TestClient, paper: Paper) -> None:
    response = client.post("/ask", json={"question": TEXT, "paper_ids": [999999]})

    assert response.status_code == 404


def test_llm_error_returns_502(client: TestClient, paper: Paper, fake_llm: FakeLLM) -> None:
    fake_llm.error = LLMError("The language model did not respond in time.")

    response = client.post("/ask", json={"question": TEXT})

    assert response.status_code == 502
    assert response.json() == {"detail": "The language model did not respond in time."}


def test_missing_llm_returns_503_only_when_needed(client: TestClient, paper: Paper) -> None:
    app.dependency_overrides[deps.get_llm] = lambda: None

    answerable = client.post("/ask", json={"question": TEXT})
    unanswerable = client.post("/ask", json={"question": "best sourdough bread recipe"})

    assert answerable.status_code == 503
    assert "No language model is configured" in answerable.json()["detail"]
    assert unanswerable.status_code == 200
    assert unanswerable.json()["abstained"] is True


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": "   "},
        {"question": "x" * 1001},
        {"question": "ok", "top_k": 0},
        {"question": "ok", "top_k": 11},
        {"question": "ok", "paper_ids": ["abc"]},
    ],
)
def test_invalid_requests_return_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/ask", json=body).status_code == 422


def test_unreachable_llm_returns_503(client: TestClient, paper: Paper, fake_llm: FakeLLM) -> None:
    fake_llm.error = LLMUnavailableError("Could not reach Ollama at http://localhost:11434.")

    response = client.post("/ask", json={"question": TEXT})

    assert response.status_code == 503
    assert "Could not reach Ollama" in response.json()["detail"]


def test_llm_disabled_by_default_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None))

    assert next(deps.get_llm()) is None  # llm_provider defaults to "none"


def test_ollama_provider_builds_ollama_client(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, llm_provider="ollama", ollama_model="some-model")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

    llm = next(deps.get_llm())

    assert isinstance(llm, OllamaClient)
    assert llm.model_name == "some-model"
