from datetime import date

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Author, IngestionRun, IngestionRunStatus, Paper, PaperAuthor, PaperStatus
from app.services import ingestion
from app.services.arxiv import (
    ArxivMetadata,
    ArxivPaperNotFoundError,
    ArxivResponseError,
    ArxivUnavailableError,
    InvalidArxivIdError,
)
from tests.arxiv_fakes import FakeArxiv, make_feed


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def only_run(db: Session) -> IngestionRun:
    return db.scalars(select(IngestionRun)).one()


def test_successful_import_stores_paper_authors_and_run(db_session: Session) -> None:
    result = ingestion.import_paper(db_session, "1706.03762", FakeArxiv().client())

    assert result.created is True
    paper = result.paper
    assert paper.arxiv_id == "1706.03762"
    assert paper.title == "Attention Is All You Need"
    assert paper.published_date == date(2017, 6, 12)
    assert paper.ingestion_status == PaperStatus.IMPORTED
    assert paper.source_url == "https://arxiv.org/abs/1706.03762"
    assert [a.name for a in paper.authors][:2] == ["Ashish Vaswani", "Noam Shazeer"]
    assert count(db_session, Author) == 8

    run = only_run(db_session)
    assert run.requested_arxiv_id == "1706.03762"
    assert run.status == IngestionRunStatus.SUCCEEDED
    assert run.completed_at is not None
    assert run.error_message is None


def test_duplicate_import_is_a_no_op(db_session: Session) -> None:
    fake = FakeArxiv()
    first = ingestion.import_paper(db_session, "1706.03762", fake.client())

    second = ingestion.import_paper(db_session, "1706.03762", fake.client())

    assert second.created is False
    assert second.paper.id == first.paper.id
    assert len(fake.requests) == 1  # arXiv is not called again
    assert count(db_session, Paper) == 1
    assert count(db_session, Author) == 8
    assert count(db_session, PaperAuthor) == 8
    runs = db_session.scalars(select(IngestionRun)).all()
    assert [run.status for run in runs] == [IngestionRunStatus.SUCCEEDED] * 2


def test_versioned_and_prefixed_ids_map_to_the_same_paper(db_session: Session) -> None:
    fake = FakeArxiv()
    ingestion.import_paper(db_session, "1706.03762", fake.client())

    for variant in ["1706.03762v7", "arXiv:1706.03762", "  1706.03762v1 "]:
        assert ingestion.import_paper(db_session, variant, fake.client()).created is False

    assert count(db_session, Paper) == 1


def test_authors_shared_between_papers_are_stored_once(db_session: Session) -> None:
    fake = FakeArxiv()
    fake.feeds["2401.00001"] = make_feed("2401.00001", authors=["Ada Lovelace", "Alan Turing"])
    fake.feeds["2401.00002"] = make_feed("2401.00002", authors=["Grace Hopper", "Ada Lovelace"])

    ingestion.import_paper(db_session, "2401.00001", fake.client())
    second = ingestion.import_paper(db_session, "2401.00002", fake.client())

    assert count(db_session, Author) == 3
    assert [a.name for a in second.paper.authors] == ["Grace Hopper", "Ada Lovelace"]


@pytest.mark.parametrize(
    ("requested_id", "configure", "expected_error"),
    [
        ("not-an-id", None, InvalidArxivIdError),
        ("2501.99999", None, ArxivPaperNotFoundError),
        ("1706.03762", "network", ArxivUnavailableError),
        ("1706.03762", "malformed", ArxivResponseError),
    ],
)
def test_failed_import_records_failed_run_and_stores_nothing(
    db_session: Session,
    requested_id: str,
    configure: str | None,
    expected_error: type[Exception],
) -> None:
    fake = FakeArxiv()
    if configure == "network":
        fake.error = httpx.ConnectError("connection refused")
    if configure == "malformed":
        fake.feeds["1706.03762"] = b"<not-a-feed"

    with pytest.raises(expected_error) as raised:
        ingestion.import_paper(db_session, requested_id, fake.client())

    assert count(db_session, Paper) == 0
    assert count(db_session, Author) == 0
    run = only_run(db_session)
    assert run.requested_arxiv_id == requested_id
    assert run.status == IngestionRunStatus.FAILED
    assert run.completed_at is not None
    assert run.error_message == str(raised.value)


def test_invalid_id_does_not_call_arxiv(db_session: Session) -> None:
    fake = FakeArxiv()

    with pytest.raises(InvalidArxivIdError):
        ingestion.import_paper(db_session, "not-an-id", fake.client())

    assert fake.requests == []


def test_database_failure_rolls_back_and_records_failed_run(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_store(db: Session, metadata: ArxivMetadata) -> Paper:
        raise OperationalError("INSERT ...", {}, Exception("disk full"))

    monkeypatch.setattr(ingestion, "_store_paper", broken_store)

    with pytest.raises(ingestion.IngestionDatabaseError) as raised:
        ingestion.import_paper(db_session, "1706.03762", FakeArxiv().client())

    assert "disk full" not in str(raised.value)  # internal details are not leaked
    assert count(db_session, Paper) == 0
    run = only_run(db_session)
    assert run.status == IngestionRunStatus.FAILED
    assert run.error_message == "Database error while saving the paper."


def test_concurrent_duplicate_insert_returns_existing_paper(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates another request storing the same paper between our check and our insert."""
    fake = FakeArxiv()
    real_fetch = fake.client().fetch_metadata

    def fetch_while_someone_else_imports(arxiv_id: str) -> ArxivMetadata:
        metadata = real_fetch(arxiv_id)
        db_session.add(
            Paper(
                arxiv_id=arxiv_id,
                title="Stored by a parallel request",
                abstract="...",
                published_date=metadata.published_date,
                source_url=metadata.source_url,
                pdf_url=metadata.pdf_url,
            )
        )
        db_session.flush()
        return metadata

    client = fake.client()
    monkeypatch.setattr(client, "fetch_metadata", fetch_while_someone_else_imports)

    result = ingestion.import_paper(db_session, "1706.03762", client)

    assert result.created is False
    assert result.paper.title == "Stored by a parallel request"
    assert count(db_session, Paper) == 1
    assert only_run(db_session).status == IngestionRunStatus.SUCCEEDED
