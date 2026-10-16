import httpx
import pytest

from app.services.pdf import (
    PdfDownloadError,
    PdfUnavailableError,
    UnprocessableDocumentError,
    extract_pages,
)
from tests.pdf_fakes import FakePdfServer, make_pdf

URL = "https://arxiv.test/pdf/2401.00001"

# --- extract_pages -------------------------------------------------------------


def test_extracts_and_cleans_text_per_page() -> None:
    pdf = make_pdf([["Deep learning for", "trans-", "formers (2024)"], ["Second page."]])

    assert extract_pages(pdf) == ["Deep learning for transformers (2024)", "Second page."]


def test_blank_pages_are_kept_as_empty_strings() -> None:
    assert extract_pages(make_pdf([["text"], [], ["more"]])) == ["text", "", "more"]


def test_pdf_without_any_text_is_rejected() -> None:
    """This is what a scanned, image-only PDF looks like to a text extractor."""
    with pytest.raises(UnprocessableDocumentError, match="Scanned"):
        extract_pages(make_pdf([[], []]))


@pytest.mark.parametrize(
    "content",
    [b"%PDF-1.4\nthis is not really a pdf", b"", make_pdf([["text"]])[:200]],
)
def test_corrupt_pdf_is_rejected(content: bytes) -> None:
    with pytest.raises(UnprocessableDocumentError):
        extract_pages(content)


# --- PdfDownloader ---------------------------------------------------------------


def test_downloads_pdf() -> None:
    server = FakePdfServer()
    server.files[URL] = make_pdf([["hello"]])

    assert server.downloader().download(URL) == server.files[URL]
    assert server.requested_urls == [URL]


def test_non_pdf_content_is_rejected() -> None:
    server = FakePdfServer()
    server.files[URL] = b"<html>Please solve this captcha</html>"

    with pytest.raises(UnprocessableDocumentError, match="not a PDF"):
        server.downloader().download(URL)


def test_too_large_pdf_is_rejected() -> None:
    server = FakePdfServer()
    server.files[URL] = b"%PDF-" + b"x" * 2_000_000

    with pytest.raises(UnprocessableDocumentError, match="larger than 1 MB"):
        server.downloader(max_bytes=1_000_000).download(URL)


def test_missing_pdf_is_a_download_error() -> None:
    with pytest.raises(PdfDownloadError, match="404"):
        FakePdfServer().downloader().download(URL)


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_server_errors_mean_unavailable(status_code: int) -> None:
    server = FakePdfServer()
    server.files[URL] = make_pdf([["hello"]])
    server.status_code = status_code

    with pytest.raises(PdfUnavailableError):
        server.downloader().download(URL)


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_network_errors_mean_unavailable(error: httpx.HTTPError) -> None:
    server = FakePdfServer()
    server.error = error

    with pytest.raises(PdfUnavailableError):
        server.downloader().download(URL)
