import httpx
import pytest

from app.services.arxiv import (
    ArxivPaperNotFoundError,
    ArxivResponseError,
    ArxivUnavailableError,
    InvalidArxivIdError,
)
from tests.arxiv_fakes import FakeArxiv


def test_fetches_metadata_with_expected_query() -> None:
    fake = FakeArxiv()

    metadata = fake.client().fetch_metadata("1706.03762")

    assert metadata.title == "Attention Is All You Need"
    assert len(fake.requests) == 1
    assert fake.requests[0].url.params["id_list"] == "1706.03762"
    assert fake.requests[0].url.params["max_results"] == "1"


def test_unknown_paper_raises_not_found() -> None:
    with pytest.raises(ArxivPaperNotFoundError):
        FakeArxiv().client().fetch_metadata("2501.99999")


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        httpx.RemoteProtocolError("server hung up"),
    ],
)
def test_network_errors_mean_unavailable(error: httpx.HTTPError) -> None:
    fake = FakeArxiv()
    fake.error = error

    with pytest.raises(ArxivUnavailableError):
        fake.client().fetch_metadata("1706.03762")


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_rate_limit_and_server_errors_mean_unavailable(status_code: int) -> None:
    fake = FakeArxiv()
    fake.status_code = status_code

    with pytest.raises(ArxivUnavailableError, match=str(status_code)):
        fake.client().fetch_metadata("1706.03762")


def test_http_400_means_invalid_id() -> None:
    fake = FakeArxiv()
    fake.status_code = 400

    with pytest.raises(InvalidArxivIdError):
        fake.client().fetch_metadata("1706.03762")


def test_other_unexpected_status_is_a_response_error() -> None:
    fake = FakeArxiv()
    fake.status_code = 403

    with pytest.raises(ArxivResponseError, match="403"):
        fake.client().fetch_metadata("1706.03762")


# --- rate limiting (HTTP 429) ---------------------------------------------------------


def test_rate_limit_is_retried_once_after_default_delay() -> None:
    fake = FakeArxiv()
    fake.scripted = [(429, {})]  # first request throttled, second one succeeds

    metadata = fake.client().fetch_metadata("1706.03762")

    assert metadata.title == "Attention Is All You Need"
    assert len(fake.requests) == 2
    assert fake.sleeps == [3.0]


def test_retry_after_header_is_respected_but_capped() -> None:
    for header, expected in [("5", 5.0), ("120", 10.0), ("soon", 3.0), ("-4", 0.0)]:
        fake = FakeArxiv()
        fake.scripted = [(429, {"Retry-After": header})]

        fake.client().fetch_metadata("1706.03762")

        assert fake.sleeps == [expected], header


def test_second_rate_limit_is_reported_without_a_third_attempt() -> None:
    fake = FakeArxiv()
    fake.scripted = [(429, {}), (429, {})]

    with pytest.raises(ArxivUnavailableError, match="429"):
        fake.client().fetch_metadata("1706.03762")

    assert len(fake.requests) == 2
    assert len(fake.sleeps) == 1


def test_other_server_errors_are_not_retried() -> None:
    fake = FakeArxiv()
    fake.scripted = [(503, {})]

    with pytest.raises(ArxivUnavailableError, match="503"):
        fake.client().fetch_metadata("1706.03762")

    assert len(fake.requests) == 1
    assert fake.sleeps == []
