from datetime import date

import pytest

from app.services.arxiv import (
    ArxivPaperNotFoundError,
    ArxivResponseError,
    InvalidArxivIdError,
    parse_arxiv_feed,
)
from tests.arxiv_fakes import fixture_bytes, make_feed


def test_parses_real_arxiv_response() -> None:
    metadata = parse_arxiv_feed(fixture_bytes("found_1706.03762.xml"), "1706.03762")

    assert metadata.arxiv_id == "1706.03762"
    assert metadata.title == "Attention Is All You Need"
    assert metadata.abstract.startswith("The dominant sequence transduction models")
    assert metadata.published_date == date(2017, 6, 12)
    assert metadata.authors[0] == "Ashish Vaswani"
    assert metadata.authors[-1] == "Illia Polosukhin"
    assert len(metadata.authors) == 8
    assert metadata.source_url == "https://arxiv.org/abs/1706.03762"
    assert metadata.pdf_url == "https://arxiv.org/pdf/1706.03762"


def test_empty_feed_means_not_found() -> None:
    with pytest.raises(ArxivPaperNotFoundError):
        parse_arxiv_feed(fixture_bytes("not_found.xml"), "2501.99999")


def test_arxiv_error_entry_means_invalid_id() -> None:
    with pytest.raises(InvalidArxivIdError):
        parse_arxiv_feed(fixture_bytes("error_invalid_id.xml"), "2501.99999")


def test_whitespace_in_title_and_abstract_is_collapsed() -> None:
    feed = make_feed(
        "2401.00001",
        title="  A Title\n    Split Over Lines ",
        summary="\n  First line.\n  Second   line.\n",
    )

    metadata = parse_arxiv_feed(feed, "2401.00001")

    assert metadata.title == "A Title Split Over Lines"
    assert metadata.abstract == "First line. Second line."


def test_duplicate_authors_are_removed_keeping_order() -> None:
    feed = make_feed("2401.00001", authors=["Ada Lovelace", "Alan Turing", "Ada  Lovelace"])

    metadata = parse_arxiv_feed(feed, "2401.00001")

    assert metadata.authors == ["Ada Lovelace", "Alan Turing"]


def test_old_style_id_is_matched() -> None:
    feed = make_feed("hep-th/9901001", entry_id="http://arxiv.org/abs/hep-th/9901001v3")

    assert parse_arxiv_feed(feed, "hep-th/9901001").arxiv_id == "hep-th/9901001"


@pytest.mark.parametrize(
    ("feed", "reason"),
    [
        (b"this is not xml", "not XML"),
        (b"<feed><entry>", "truncated XML"),
        (make_feed("2401.00001", title="   "), "empty title"),
        (make_feed("2401.00001", summary=""), "empty abstract"),
        (make_feed("2401.00001", published="yesterday"), "unparseable date"),
        (make_feed("2401.00001", published=""), "missing date"),
        (make_feed("2401.00001", authors=["   "]), "no usable authors"),
        (make_feed("2401.00001", authors=["x" * 301]), "author name too long"),
        (make_feed("2401.00001", entry_id="http://arxiv.org/abs/2401.99999v1"), "wrong paper"),
    ],
)
def test_malformed_responses_are_rejected(feed: bytes, reason: str) -> None:
    with pytest.raises(ArxivResponseError):
        parse_arxiv_feed(feed, "2401.00001")
