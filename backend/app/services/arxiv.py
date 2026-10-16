"""Fetch and parse paper metadata from the arXiv API.

Unknown IDs return HTTP 200 with no entries; malformed IDs return HTTP 400."""

import re
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

ATOM = "{http://www.w3.org/2005/Atom}"

# New-style IDs (2007+): 0704.0001, 2403.12345
_NEW_STYLE_ID = re.compile(r"^\d{4}\.\d{4,5}$")
# Old-style IDs: hep-th/9901001, math.GT/0309136
_OLD_STYLE_ID = re.compile(r"^[a-z]+(-[a-z]+)*(\.[A-Z]{2})?/\d{7}$")
_VERSION_SUFFIX = re.compile(r"v\d+$")


class ArxivError(Exception):
    """Base class for arXiv problems. Messages are safe to show to users."""


class InvalidArxivIdError(ArxivError):
    pass


class ArxivPaperNotFoundError(ArxivError):
    pass


class ArxivUnavailableError(ArxivError):
    """Network failure, timeout, rate limiting or an arXiv server error."""


class ArxivResponseError(ArxivError):
    """arXiv answered, but with something we could not understand or trust."""


AuthorName = Annotated[str, StringConstraints(min_length=1, max_length=300)]


class ArxivMetadata(BaseModel):
    """Validated, normalized metadata for one paper."""

    model_config = ConfigDict(frozen=True)

    arxiv_id: str
    title: str = Field(min_length=1, max_length=1000)
    abstract: str = Field(min_length=1)
    published_date: date
    authors: list[AuthorName] = Field(min_length=1)

    @property
    def source_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"


def normalize_arxiv_id(raw: str) -> str:
    """Canonical ID without version suffix or "arXiv:" prefix; raises InvalidArxivIdError."""
    value = raw.strip()
    if value.lower().startswith("arxiv:"):
        value = value[len("arxiv:") :]
    value = _VERSION_SUFFIX.sub("", value)

    if not (_NEW_STYLE_ID.match(value) or _OLD_STYLE_ID.match(value)):
        raise InvalidArxivIdError(
            f"'{raw.strip()}' is not a valid arXiv ID. Expected something like 2403.12345."
        )
    return value


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _child_text(element: ElementTree.Element, tag: str) -> str:
    child = element.find(f"{ATOM}{tag}")
    return _collapse_whitespace(child.text or "") if child is not None else ""


def _unique_in_order(names: list[str]) -> list[str]:
    return list(dict.fromkeys(name for name in names if name))


def parse_arxiv_feed(content: bytes, arxiv_id: str) -> ArxivMetadata:
    """Turn an arXiv Atom feed for a single ID into validated metadata."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ArxivResponseError("arXiv returned a response that could not be read.") from exc

    entry = root.find(f"{ATOM}entry")
    if entry is None:
        raise ArxivPaperNotFoundError(f"No arXiv paper found with ID {arxiv_id}.")

    entry_id = _child_text(entry, "id")
    if "/api/errors" in entry_id:
        raise InvalidArxivIdError(f"arXiv rejected the ID {arxiv_id}.")

    returned_id = _VERSION_SUFFIX.sub("", entry_id.rsplit("/abs/", 1)[-1])
    if returned_id != arxiv_id:
        raise ArxivResponseError("arXiv returned a different paper than the one requested.")

    try:
        published = datetime.fromisoformat(_child_text(entry, "published")).date()
        authors = [
            _collapse_whitespace(author.findtext(f"{ATOM}name") or "")
            for author in entry.findall(f"{ATOM}author")
        ]
        return ArxivMetadata(
            arxiv_id=arxiv_id,
            title=_child_text(entry, "title"),
            abstract=_child_text(entry, "summary"),
            published_date=published,
            authors=_unique_in_order(authors),
        )
    except (ValueError, ValidationError) as exc:
        raise ArxivResponseError(
            f"arXiv returned incomplete or invalid metadata for {arxiv_id}."
        ) from exc


# arXiv asks API clients to wait at least 3 seconds between requests.
DEFAULT_RETRY_DELAY_SECONDS = 3.0
MAX_RETRY_DELAY_SECONDS = 10.0


def _retry_delay(response: httpx.Response) -> float:
    """Seconds to wait before retrying a 429: arXiv's Retry-After if sent, else 3 s (max 10 s)."""
    try:
        delay = float(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return DEFAULT_RETRY_DELAY_SECONDS
    return min(max(delay, 0.0), MAX_RETRY_DELAY_SECONDS)


class ArxivClient:
    """Thin wrapper around the arXiv HTTP API. The httpx client is injected for testability."""

    def __init__(
        self,
        http_client: httpx.Client,
        api_url: str,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http_client
        self._api_url = api_url
        self._sleep = sleep

    def fetch_metadata(self, arxiv_id: str) -> ArxivMetadata:
        response = self._get(arxiv_id)
        if response.status_code == 429:
            # Rate limited: wait once and retry.
            self._sleep(_retry_delay(response))
            response = self._get(arxiv_id)

        if response.status_code == 400:
            raise InvalidArxivIdError(f"arXiv rejected the ID {arxiv_id}.")
        if response.status_code == 429 or response.status_code >= 500:
            raise ArxivUnavailableError(
                f"arXiv is temporarily unavailable (HTTP {response.status_code}). Try again later."
            )
        if response.status_code != 200:
            raise ArxivResponseError(
                f"Unexpected response from arXiv (HTTP {response.status_code})."
            )

        return parse_arxiv_feed(response.content, arxiv_id)

    def _get(self, arxiv_id: str) -> httpx.Response:
        try:
            return self._http.get(self._api_url, params={"id_list": arxiv_id, "max_results": 1})
        except httpx.TimeoutException as exc:
            raise ArxivUnavailableError("arXiv did not respond in time. Try again later.") from exc
        except httpx.HTTPError as exc:
            raise ArxivUnavailableError("Could not reach arXiv. Check your connection.") from exc
