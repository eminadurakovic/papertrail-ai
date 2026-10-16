import pytest
from sqlalchemy.orm import Session

from app.models import Paper, Passage
from app.services import rag
from app.services.llm import LLMError, LLMNotConfiguredError
from app.services.rag import AbstentionReason, extract_citations
from tests.factories import make_paper
from tests.fake_embedder import FakeEmbedder
from tests.fake_llm import FakeLLM

TRANSFORMER_TEXTS = [
    "attention relates every token to every other token",
    "positional encodings use sine and cosine waves",
    "training ran on eight gpus for twelve hours",
]
BERT_TEXTS = [
    "masked language modeling hides random input words",
    "next sentence prediction classifies sentence pairs",
]


@pytest.fixture
def papers(db_session: Session, fake_embedder: FakeEmbedder) -> tuple[Paper, Paper]:
    transformer = make_paper(db_session, "1706.03762", title="Transformer")
    bert = make_paper(db_session, "1810.04805", title="BERT")
    for paper, texts in [(transformer, TRANSFORMER_TEXTS), (bert, BERT_TEXTS)]:
        for position, text in enumerate(texts):
            db_session.add(
                Passage(
                    paper_id=paper.id,
                    position=position,
                    text=text,
                    page=position + 1,
                    embedding=fake_embedder.vector(text).tolist(),
                )
            )
    db_session.commit()
    return transformer, bert


def ask(
    db: Session,
    embedder: FakeEmbedder,
    llm: FakeLLM | None,
    question: str,
    *,
    min_score: float = 0.7,
    top_k: int = 5,
    paper_ids: tuple[int, ...] = (),
) -> rag.AskResult:
    return rag.answer_question(
        db, embedder, llm, question, top_k=top_k, min_score=min_score, paper_ids=paper_ids
    )


# --- successful answers --------------------------------------------------------------


def test_answer_with_citation_mapping_to_real_passage(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(reply="They use sine and cosine waves [1].")

    result = ask(db_session, fake_embedder, llm, "positional encodings use sine and cosine waves")

    assert result.abstained is False
    assert result.abstention_reason is None
    assert result.answer == "They use sine and cosine waves [1]."
    (citation,) = result.citations
    assert citation.number == 1
    assert citation.hit.text == TRANSFORMER_TEXTS[1]
    stored = db_session.get(Passage, citation.hit.passage_id)
    assert stored is not None and stored.text == citation.hit.text  # a real stored passage
    assert result.best_score == pytest.approx(1.0)


def test_prompt_contains_rules_numbered_passages_and_question(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    llm = FakeLLM()

    ask(db_session, fake_embedder, llm, "positional encodings use sine and cosine waves")

    system, user = llm.prompts[0]
    assert "ONLY the numbered passages" in system
    assert "INSUFFICIENT_EVIDENCE" in system
    assert "Do not use LaTeX or Markdown" in system  # the UI shows answers as plain text
    assert '[1] (from "Transformer", page 2)\npositional encodings use sine' in user
    assert user.endswith(
        "Question: positional encodings use sine and cosine waves\n\n"
        "Reply in plain text only (no LaTeX, no Markdown) and cite passages as [n].\n\n"
        "Answer:"
    )


def test_only_passages_above_threshold_reach_the_model(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    llm = FakeLLM()

    ask(db_session, fake_embedder, llm, "positional encodings use sine and cosine waves")

    prompt = llm.last_user_prompt
    assert "[1]" in prompt and "[2]" not in prompt  # only the one strong match
    assert "masked language modeling" not in prompt


def test_citation_numbers_follow_context_order(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(reply="Training took twelve hours [2], and attention is global [1][2].")

    result = ask(
        db_session,
        fake_embedder,
        llm,
        "attention relates every token, training ran on eight gpus",
        min_score=0.1,
    )

    assert [c.number for c in result.citations] == [2, 1]  # order of first appearance
    for citation in result.citations:
        assert f"[{citation.number}]" in llm.last_user_prompt
        assert citation.hit.text in llm.last_user_prompt.split(f"[{citation.number}] ")[1]


def test_paper_filter_limits_evidence(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    transformer, bert = papers
    llm = FakeLLM(reply="Answer [1].")

    result = ask(
        db_session,
        fake_embedder,
        llm,
        "masked language modeling hides random input words",
        min_score=0.0,
        paper_ids=(transformer.id,),
    )

    passages_section = llm.last_user_prompt.split("Question:")[0]
    assert "masked language modeling" not in passages_section  # BERT passage filtered out
    assert all(c.hit.paper_id == transformer.id for c in result.citations)


# --- abstention ----------------------------------------------------------------------


def test_abstains_without_calling_model_when_nothing_is_relevant(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    llm = FakeLLM()

    result = ask(db_session, fake_embedder, llm, "best sourdough bread recipe")

    assert result.abstained is True
    assert result.abstention_reason == AbstentionReason.NO_RELEVANT_PASSAGES
    assert result.answer == rag.ABSTAIN_MESSAGE
    assert result.citations == []
    assert result.best_score is not None and result.best_score < 0.7
    assert llm.prompts == []


def test_abstains_when_nothing_is_indexed(db_session: Session, fake_embedder: FakeEmbedder) -> None:
    llm = FakeLLM()

    result = ask(db_session, fake_embedder, llm, "anything")

    assert result.abstention_reason == AbstentionReason.NO_RELEVANT_PASSAGES
    assert result.best_score is None
    assert llm.prompts == []


@pytest.mark.parametrize("reply", ["INSUFFICIENT_EVIDENCE", "  INSUFFICIENT_EVIDENCE.\n", ""])
def test_abstains_when_model_reports_insufficient_evidence(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder, reply: str
) -> None:
    result = ask(
        db_session, fake_embedder, FakeLLM(reply=reply), "positional encodings use sine waves"
    )

    assert result.abstained is True
    assert result.abstention_reason == AbstentionReason.MODEL_INSUFFICIENT_EVIDENCE
    assert result.citations == []


@pytest.mark.parametrize(
    "reply", ["They use sine waves.", "They use sine waves [7].", "See [0] and [99]."]
)
def test_abstains_when_answer_has_no_valid_citation(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder, reply: str
) -> None:
    result = ask(
        db_session, fake_embedder, FakeLLM(reply=reply), "positional encodings use sine waves"
    )

    assert result.abstained is True
    assert result.abstention_reason == AbstentionReason.NO_VALID_CITATIONS


# --- errors ----------------------------------------------------------------------------


def test_llm_error_propagates(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(error=LLMError("The language model did not respond."))

    with pytest.raises(LLMError, match="did not respond"):
        ask(db_session, fake_embedder, llm, "positional encodings use sine and cosine waves")


def test_missing_llm_only_matters_when_an_answer_is_needed(
    db_session: Session, papers: tuple[Paper, Paper], fake_embedder: FakeEmbedder
) -> None:
    abstained = ask(db_session, fake_embedder, None, "best sourdough bread recipe")
    assert abstained.abstained is True

    with pytest.raises(LLMNotConfiguredError):
        ask(db_session, fake_embedder, None, "positional encodings use sine and cosine waves")


# --- citation parsing -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected_text", "expected_numbers"),
    [
        ("A [1].", "A [1].", [1]),
        ("A [2] and B [1][2].", "A [2] and B [1][2].", [2, 1]),
        ("Grouped [1, 3].", "Grouped [1][3].", [1, 3]),
        ("Invalid [4] removed.", "Invalid removed.", []),
        ("Mixed [1, 9].", "Mixed [1].", [1]),
        ("Ends with invalid [5].", "Ends with invalid.", []),
        ("No citations.", "No citations.", []),
        ("Not a citation [a].", "Not a citation [a].", []),
    ],
)
def test_extract_citations(text: str, expected_text: str, expected_numbers: list[int]) -> None:
    assert extract_citations(text, valid_numbers=range(1, 4)) == (expected_text, expected_numbers)
