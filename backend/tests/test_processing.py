import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Paper, PaperStatus, Passage
from app.services import processing
from app.services.chunking import Chunk
from app.services.pdf import PdfUnavailableError, UnprocessableDocumentError
from tests.factories import make_paper
from tests.pdf_fakes import FakePdfServer, make_pdf, numbered_words

SIZE, OVERLAP = 10, 2


def run(db: Session, paper: Paper, server: FakePdfServer) -> processing.ProcessResult:
    return processing.process_paper(
        db, paper.id, server.downloader(), chunk_size=SIZE, chunk_overlap=OVERLAP
    )


def stored_passages(db: Session, paper: Paper) -> list[Passage]:
    statement = select(Passage).where(Passage.paper_id == paper.id).order_by(Passage.position)
    return list(db.scalars(statement))


@pytest.fixture
def paper(db_session: Session) -> Paper:
    return make_paper(db_session, "2401.00001")


@pytest.fixture
def server(paper: Paper) -> FakePdfServer:
    server = FakePdfServer()
    # 2 pages x 20 words = 40 words -> windows start at 0, 8, 16, 24, 32 -> 5 chunks
    server.files[paper.pdf_url] = make_pdf([numbered_words(20, "a"), numbered_words(20, "b")])
    return server


def test_successful_processing_stores_passages(
    db_session: Session, paper: Paper, server: FakePdfServer
) -> None:
    result = run(db_session, paper, server)

    assert result.page_count == 2
    assert result.passage_count == 5
    assert result.extracted_characters > 0
    assert paper.ingestion_status == PaperStatus.PROCESSED
    assert paper.processing_error is None

    passages = stored_passages(db_session, paper)
    assert [p.position for p in passages] == [0, 1, 2, 3, 4]
    assert all(p.paper_id == paper.id for p in passages)
    assert passages[0].text.split()[:2] == ["a0", "a1"]
    assert passages[0].page == 1
    assert passages[-1].page == 2
    assert server.requested_urls == [paper.pdf_url]


def test_reprocessing_gives_equivalent_passages(
    db_session: Session, paper: Paper, server: FakePdfServer
) -> None:
    run(db_session, paper, server)
    first = [(p.position, p.text, p.page) for p in stored_passages(db_session, paper)]

    run(db_session, paper, server)
    second = [(p.position, p.text, p.page) for p in stored_passages(db_session, paper)]

    assert second == first  # replaced, not duplicated


def test_reprocessing_with_a_shorter_document_removes_old_passages(
    db_session: Session, paper: Paper, server: FakePdfServer
) -> None:
    run(db_session, paper, server)
    server.files[paper.pdf_url] = make_pdf([["only", "three", "words"]])

    run(db_session, paper, server)

    assert [p.text for p in stored_passages(db_session, paper)] == ["only three words"]


def test_passages_of_other_papers_are_not_touched(
    db_session: Session, paper: Paper, server: FakePdfServer
) -> None:
    other = make_paper(db_session, "2401.00002")
    db_session.add(Passage(paper_id=other.id, position=0, text="keep me"))
    db_session.flush()

    run(db_session, paper, server)

    assert [p.text for p in stored_passages(db_session, other)] == ["keep me"]


def test_empty_document_marks_paper_failed(
    db_session: Session, paper: Paper, server: FakePdfServer
) -> None:
    server.files[paper.pdf_url] = make_pdf([[], []])

    with pytest.raises(UnprocessableDocumentError) as raised:
        run(db_session, paper, server)

    assert paper.ingestion_status == PaperStatus.FAILED
    assert paper.processing_error == str(raised.value)
    assert stored_passages(db_session, paper) == []


def test_failure_keeps_passages_from_previous_success(
    db_session: Session, paper: Paper, server: FakePdfServer
) -> None:
    run(db_session, paper, server)
    server.error = httpx.ConnectError("offline")

    with pytest.raises(PdfUnavailableError):
        run(db_session, paper, server)

    assert paper.ingestion_status == PaperStatus.FAILED
    assert len(stored_passages(db_session, paper)) == 5


def test_successful_retry_clears_previous_error(
    db_session: Session, paper: Paper, server: FakePdfServer
) -> None:
    server.error = httpx.ConnectError("offline")
    with pytest.raises(PdfUnavailableError):
        run(db_session, paper, server)

    server.error = None
    run(db_session, paper, server)

    assert paper.ingestion_status == PaperStatus.PROCESSED
    assert paper.processing_error is None


def test_unknown_paper_raises_not_found(db_session: Session) -> None:
    with pytest.raises(processing.PaperNotFoundError):
        processing.process_paper(
            db_session, 999_999, FakePdfServer().downloader(), chunk_size=10, chunk_overlap=2
        )


def test_database_failure_rolls_back_and_marks_failed(
    db_session: Session, paper: Paper, server: FakePdfServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_replace(db: Session, paper: Paper, chunks: list[Chunk]) -> None:
        raise OperationalError("INSERT ...", {}, Exception("disk full"))

    monkeypatch.setattr(processing, "_replace_passages", broken_replace)

    with pytest.raises(processing.ProcessingDatabaseError) as raised:
        run(db_session, paper, server)

    assert "disk full" not in str(raised.value)
    db_session.refresh(paper)
    assert paper.ingestion_status == PaperStatus.FAILED
    assert paper.processing_error == "Database error while saving passages."
    assert stored_passages(db_session, paper) == []
