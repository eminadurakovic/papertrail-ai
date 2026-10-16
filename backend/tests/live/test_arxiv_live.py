"""One real arXiv request. Run with: pytest -m live"""

import pytest

from app.api.deps import get_arxiv_client


@pytest.mark.live
def test_real_arxiv_returns_expected_metadata() -> None:
    # Keep a reference, otherwise the generator is collected and closes the HTTP client.
    dependency = get_arxiv_client()
    try:
        metadata = next(dependency).fetch_metadata("1706.03762")
    finally:
        dependency.close()

    assert metadata.title == "Attention Is All You Need"
    assert "Ashish Vaswani" in metadata.authors
