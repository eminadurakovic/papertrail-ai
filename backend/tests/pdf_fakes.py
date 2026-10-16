"""Test helpers: generate small, valid PDFs in code and serve them without a network."""

import httpx

from app.services.pdf import PdfDownloader


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    """Build a minimal PDF where each page is a list of text lines (Helvetica, Latin-1).

    A page with no lines is blank, which is how a scanned (image-only) page looks to
    a text extractor.
    """
    page_ids = [4 + 2 * index for index in range(len(pages))]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_id, lines in zip(page_ids, pages, strict=True):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode()
        )
        operations = ["BT", "/F1 11 Tf", "14 TL", "72 740 Td"]
        operations += [f"({_escape(line)}) Tj T*" for line in lines]
        operations.append("ET")
        stream = "\n".join(operations).encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref_offset = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_offset,
    )
    return bytes(pdf)


def numbered_words(count: int, prefix: str = "w") -> list[str]:
    return [f"{prefix}{number}" for number in range(count)]


class FakePdfServer:
    """Serves bytes by URL through httpx.MockTransport and records requested URLs."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.requested_urls: list[str] = []
        self.status_code = 200
        self.error: httpx.HTTPError | None = None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requested_urls.append(str(request.url))
        if self.error is not None:
            raise self.error
        content = self.files.get(str(request.url))
        if content is None:
            return httpx.Response(404, content=b"not found")
        return httpx.Response(self.status_code, content=content)

    def downloader(self, max_bytes: int = 1_000_000) -> PdfDownloader:
        http_client = httpx.Client(transport=httpx.MockTransport(self._handle))
        return PdfDownloader(http_client, max_bytes=max_bytes)
