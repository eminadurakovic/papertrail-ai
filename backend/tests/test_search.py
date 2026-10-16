import math

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.models import Paper, Passage
from app.models.passage import EMBEDDING_DIMENSION
from app.services.search import UnknownPapersError, search_by_vector, semantic_search
from tests.factories import make_paper
from tests.fake_embedder import FakeEmbedder


def axis(index: int) -> list[float]:
    """Unit vector pointing along one axis: [0, ..., 1, ..., 0]."""
    vector = [0.0] * EMBEDDING_DIMENSION
    vector[index] = 1.0
    return vector


def between(first: int, second: int, weight: float) -> list[float]:
    """Unit vector between two axes; weight=1 -> exactly `first`, weight=0 -> `second`."""
    vector = np.zeros(EMBEDDING_DIMENSION)
    vector[first], vector[second] = weight, 1 - weight
    return list(vector / np.linalg.norm(vector))


def add_passage(
    db: Session, paper: Paper, position: int, text: str, embedding: list[float] | None
) -> Passage:
    passage = Passage(paper_id=paper.id, position=position, text=text, embedding=embedding)
    db.add(passage)
    db.flush()
    return passage


@pytest.fixture
def paper(db_session: Session) -> Paper:
    return make_paper(db_session, "2401.00001", title="Paper A")


def test_results_are_sorted_by_cosine_similarity(db_session: Session, paper: Paper) -> None:
    add_passage(db_session, paper, 0, "far", axis(1))  # orthogonal -> score 0
    add_passage(db_session, paper, 1, "exact", axis(0))  # identical -> score 1
    add_passage(db_session, paper, 2, "close", between(0, 1, 0.9))
    add_passage(db_session, paper, 3, "medium", between(0, 1, 0.5))  # 45 degrees

    hits = search_by_vector(db_session, axis(0), limit=10)

    assert [hit.text for hit in hits] == ["exact", "close", "medium", "far"]
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(1.0)
    assert scores[2] == pytest.approx(math.cos(math.radians(45)))
    assert scores[3] == pytest.approx(0.0, abs=1e-6)


def test_opposite_vector_has_negative_score(db_session: Session, paper: Paper) -> None:
    add_passage(db_session, paper, 0, "opposite", [-x for x in axis(0)])

    assert search_by_vector(db_session, axis(0), limit=1)[0].score == pytest.approx(-1.0)


def test_limit_caps_the_number_of_results(db_session: Session, paper: Paper) -> None:
    for position in range(8):
        add_passage(db_session, paper, position, f"p{position}", axis(position))

    assert len(search_by_vector(db_session, axis(0), limit=3)) == 3
    assert len(search_by_vector(db_session, axis(0), limit=50)) == 8


def test_hits_carry_passage_and_paper_details(db_session: Session, paper: Paper) -> None:
    passage = add_passage(db_session, paper, 7, "the text", axis(0))
    passage.page = 4

    (hit,) = search_by_vector(db_session, axis(0), limit=1)

    assert hit.passage_id == passage.id
    assert (hit.paper_id, hit.paper_title, hit.arxiv_id) == (paper.id, "Paper A", "2401.00001")
    assert (hit.position, hit.page, hit.text) == (7, 4, "the text")


def test_passages_without_embeddings_are_skipped(db_session: Session, paper: Paper) -> None:
    add_passage(db_session, paper, 0, "indexed", axis(0))
    add_passage(db_session, paper, 1, "not indexed yet", None)

    assert [hit.text for hit in search_by_vector(db_session, axis(0), limit=10)] == ["indexed"]


def test_no_indexed_passages_gives_empty_results(db_session: Session, paper: Paper) -> None:
    assert search_by_vector(db_session, axis(0), limit=5) == []
    add_passage(db_session, paper, 0, "not indexed", None)
    assert search_by_vector(db_session, axis(0), limit=5) == []


def test_paper_filter(db_session: Session, paper: Paper) -> None:
    other = make_paper(db_session, "2401.00002", title="Paper B")
    third = make_paper(db_session, "2401.00003", title="Paper C")
    add_passage(db_session, paper, 0, "A best match", axis(0))
    add_passage(db_session, other, 0, "B weaker match", between(0, 1, 0.5))
    add_passage(db_session, third, 0, "C weak match", between(0, 1, 0.2))

    only_b = search_by_vector(db_session, axis(0), limit=10, paper_ids=[other.id])
    b_and_c = search_by_vector(db_session, axis(0), limit=10, paper_ids=[other.id, third.id])
    everything = search_by_vector(db_session, axis(0), limit=10)

    assert [hit.text for hit in only_b] == ["B weaker match"]
    assert [hit.text for hit in b_and_c] == ["B weaker match", "C weak match"]
    assert len(everything) == 3


def test_equal_scores_are_ordered_by_passage_id(db_session: Session, paper: Paper) -> None:
    first = add_passage(db_session, paper, 0, "first", axis(1))
    second = add_passage(db_session, paper, 1, "second", axis(2))

    hits = search_by_vector(db_session, axis(0), limit=2)  # both score exactly 0

    assert [hit.passage_id for hit in hits] == [first.id, second.id]


def test_unknown_paper_filter_is_rejected(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder
) -> None:
    with pytest.raises(UnknownPapersError, match="999998, 999999"):
        semantic_search(
            db_session, fake_embedder, "q", limit=5, paper_ids=[paper.id, 999999, 999998]
        )


def test_semantic_search_embeds_query_and_finds_best_passage(
    db_session: Session, paper: Paper, fake_embedder: FakeEmbedder
) -> None:
    """End to end with the deterministic fake: shared words -> closer vectors."""
    texts = [
        "convolutional networks for image classification",
        "attention lets the model relate distant words",
        "we report bleu scores on translation benchmarks",
    ]
    for position, text in enumerate(texts):
        add_passage(db_session, paper, position, text, fake_embedder.vector(text).tolist())

    hits = semantic_search(db_session, fake_embedder, "how does attention relate words", limit=3)

    assert hits[0].text == texts[1]
