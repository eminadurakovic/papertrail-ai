"""A fake arXiv API for tests. No network requests are made."""

from pathlib import Path
from xml.sax.saxutils import escape

import httpx

from app.services.arxiv import ArxivClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "arxiv"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def make_feed(
    arxiv_id: str,
    *,
    title: str = "A Synthetic Paper",
    summary: str = "A synthetic abstract.",
    published: str = "2024-03-01T12:00:00Z",
    authors: list[str] | None = None,
    entry_id: str | None = None,
) -> bytes:
    """Build a minimal arXiv-style Atom feed with one entry."""
    author_xml = "".join(
        f"<author><name>{escape(name)}</name></author>" for name in authors or ["Jane Doe"]
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>{entry_id or f"http://arxiv.org/abs/{arxiv_id}v1"}</id>
    <title>{escape(title)}</title>
    <summary>{escape(summary)}</summary>
    <published>{published}</published>
    {author_xml}
  </entry>
</feed>""".encode()


class FakeArxiv:
    """Serves canned feeds by ID through httpx.MockTransport and records every request."""

    def __init__(self) -> None:
        self.feeds: dict[str, bytes] = {"1706.03762": fixture_bytes("found_1706.03762.xml")}
        self.requests: list[httpx.Request] = []
        self.status_code = 200
        # Optional per-request overrides: (status, headers) consumed in order, then status_code.
        self.scripted: list[tuple[int, dict[str, str]]] = []
        self.sleeps: list[float] = []
        self.error: httpx.HTTPError | None = None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.scripted:
            status_code, headers = self.scripted.pop(0)
            return httpx.Response(status_code, headers=headers, content=b"")
        arxiv_id = request.url.params["id_list"]
        body = self.feeds.get(arxiv_id, fixture_bytes("not_found.xml"))
        return httpx.Response(self.status_code, content=body)

    def client(self) -> ArxivClient:
        http_client = httpx.Client(transport=httpx.MockTransport(self._handle))
        return ArxivClient(http_client, "https://arxiv.test/api/query", sleep=self.sleeps.append)
