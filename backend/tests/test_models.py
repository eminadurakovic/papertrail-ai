import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Author,
    IngestionRun,
    IngestionRunStatus,
    PaperAuthor,
    PaperStatus,
    Passage,
)
from tests.factories import make_paper


def test_paper_is_created_with_defaults(db_session: Session) -> None:
    paper = make_paper(db_session)
    db_session.refresh(paper)

    assert paper.id is not None
    assert paper.ingestion_status == PaperStatus.IMPORTED
    assert paper.created_at is not None
    assert paper.updated_at is not None


def test_arxiv_id_must_be_unique(db_session: Session) -> None:
    make_paper(db_session, "2401.00001")

    with pytest.raises(IntegrityError, match="uq_papers_arxiv_id"):
        make_paper(db_session, "2401.00001")


def test_invalid_status_is_rejected_by_database(db_session: Session) -> None:
    paper = make_paper(db_session)

    with pytest.raises(IntegrityError, match="ck_papers_ingestion_status"):
        db_session.execute(
            text("UPDATE papers SET ingestion_status = 'banana' WHERE id = :id"), {"id": paper.id}
        )


def test_authors_keep_their_order(db_session: Session) -> None:
    paper = make_paper(db_session, authors=["Ada Lovelace", "Alan Turing", "Grace Hopper"])
    db_session.expire_all()  # force a reload from the database

    assert [author.name for author in paper.authors] == [
        "Ada Lovelace",
        "Alan Turing",
        "Grace Hopper",
    ]


def test_author_can_belong_to_many_papers(db_session: Session) -> None:
    make_paper(db_session, "2401.00001", authors=["Ada Lovelace"])
    make_paper(db_session, "2401.00002", authors=["Ada Lovelace", "Alan Turing"])

    ada = db_session.scalars(select(Author).where(Author.name == "Ada Lovelace")).one()
    assert len(ada.paper_links) == 2
    assert db_session.scalar(select(Author).where(Author.name == "Ada Lovelace")) is ada


def test_author_cannot_be_linked_twice_to_same_paper(db_session: Session) -> None:
    paper = make_paper(db_session, authors=["Ada Lovelace"])
    ada = paper.authors[0]

    with pytest.raises(IntegrityError, match="pk_paper_authors"):
        db_session.execute(
            insert(PaperAuthor).values(paper_id=paper.id, author_id=ada.id, position=1)
        )


def test_passages_belong_to_paper_in_order(db_session: Session) -> None:
    paper = make_paper(db_session)
    # Added out of order on purpose: the relationship must sort by position.
    db_session.add_all(
        [
            Passage(paper_id=paper.id, position=1, text="second", page=2),
            Passage(paper_id=paper.id, position=0, text="first", page=1, section="Intro"),
        ]
    )
    db_session.flush()
    db_session.expire_all()

    assert [p.text for p in paper.passages] == ["first", "second"]
    assert paper.passages[0].paper is paper
    assert paper.passages[0].section == "Intro"


def test_passage_position_is_unique_per_paper(db_session: Session) -> None:
    paper = make_paper(db_session)
    db_session.add(Passage(paper_id=paper.id, position=0, text="a"))
    db_session.flush()

    db_session.add(Passage(paper_id=paper.id, position=0, text="b"))
    with pytest.raises(IntegrityError, match="uq_passages_paper_id_position"):
        db_session.flush()


def test_same_position_is_allowed_in_different_papers(db_session: Session) -> None:
    first = make_paper(db_session, "2401.00001")
    second = make_paper(db_session, "2401.00002")

    db_session.add_all(
        [
            Passage(paper_id=first.id, position=0, text="a"),
            Passage(paper_id=second.id, position=0, text="b"),
        ]
    )
    db_session.flush()  # no error


def test_passage_requires_existing_paper(db_session: Session) -> None:
    db_session.add(Passage(paper_id=999_999, position=0, text="orphan"))

    with pytest.raises(IntegrityError, match="fk_passages_paper_id_papers"):
        db_session.flush()


def test_deleting_paper_removes_passages_and_links_but_keeps_authors(
    db_session: Session,
) -> None:
    paper = make_paper(db_session, authors=["Ada Lovelace"])
    db_session.add(Passage(paper_id=paper.id, position=0, text="text"))
    db_session.flush()

    db_session.delete(paper)
    db_session.flush()

    assert db_session.scalars(select(Passage)).all() == []
    assert db_session.scalars(select(PaperAuthor)).all() == []
    assert db_session.scalars(select(Author)).one().name == "Ada Lovelace"


def test_ingestion_run_is_created_as_running(db_session: Session) -> None:
    run = IngestionRun(requested_arxiv_id="2401.00001")
    db_session.add(run)
    db_session.flush()
    db_session.refresh(run)

    assert run.status == IngestionRunStatus.RUNNING
    assert run.started_at is not None
    assert run.completed_at is None
    assert run.error_message is None


def test_failed_ingestion_run_stores_error(db_session: Session) -> None:
    run = IngestionRun(
        requested_arxiv_id="not-an-id",
        status=IngestionRunStatus.FAILED,
        error_message="Invalid arXiv identifier",
    )
    db_session.add(run)
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(IngestionRun, run.id)
    assert stored is not None
    assert stored.status == IngestionRunStatus.FAILED
    assert stored.error_message == "Invalid arXiv identifier"
