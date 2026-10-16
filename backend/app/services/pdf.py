"""Downloading PDFs and extracting their text.

PDFs are kept in memory only (never written to disk), so no temporary files accumulate.
OCR is deliberately not supported: scanned, image-only PDFs fail with a clear message.
"""

import logging
from io import BytesIO

import httpx
from pypdf import PdfReader

from app.services.chunking import clean_text

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Base class for processing problems. Messages are safe to show to users."""


class PdfUnavailableError(ProcessingError):
    """Network failure, timeout, rate limiting or a server error while downloading."""


class PdfDownloadError(ProcessingError):
    """The server answered with an unexpected status (e.g. 404)."""


class UnprocessableDocumentError(ProcessingError):
    """The file is not a usable PDF: too large, corrupt, not a PDF, or has no text."""


class PdfDownloader:
    def __init__(self, http_client: httpx.Client, max_bytes: int) -> None:
        self._http = http_client
        self._max_bytes = max_bytes

    def download(self, url: str) -> bytes:
        try:
            with self._http.stream("GET", url) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    raise PdfUnavailableError(
                        f"The PDF server is temporarily unavailable (HTTP {response.status_code})."
                    )
                if response.status_code != 200:
                    raise PdfDownloadError(
                        f"Could not download the PDF (HTTP {response.status_code})."
                    )
                content = self._read_limited(response)
        except httpx.TimeoutException as exc:
            raise PdfUnavailableError("Downloading the PDF timed out. Try again later.") from exc
        except httpx.HTTPError as exc:
            raise PdfUnavailableError("Could not download the PDF. Check your connection.") from exc

        if not content.startswith(b"%PDF-"):
            raise UnprocessableDocumentError("The downloaded file is not a PDF.")
        return content

    def _read_limited(self, response: httpx.Response) -> bytes:
        """Read the body in pieces, stopping early if it exceeds the size limit."""
        content = bytearray()
        for piece in response.iter_bytes():
            content.extend(piece)
            if len(content) > self._max_bytes:
                limit_mb = self._max_bytes // 1_000_000
                raise UnprocessableDocumentError(f"The PDF is larger than {limit_mb} MB.")
        return bytes(content)


def extract_pages(pdf_bytes: bytes) -> list[str]:
    """Return the cleaned text of each page, in order."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages = [clean_text(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # pypdf raises many different exception types for broken files
        logger.warning("PDF text extraction failed: %r", exc)
        raise UnprocessableDocumentError("The PDF could not be read.") from exc

    if not any(pages):
        raise UnprocessableDocumentError(
            "No text could be extracted from the PDF. Scanned (image-only) PDFs are not supported."
        )
    return pages
