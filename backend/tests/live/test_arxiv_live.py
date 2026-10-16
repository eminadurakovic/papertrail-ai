"""Smoke test against the real arXiv API (one request, nothing stored).

Excluded from normal runs. Run explicitly with:  pytest -m live
"""

import pytest

from app.api.deps import get_arxiv_client


@pytest.mark.live
def test_real_arxiv_returns_expected_metadata() -> None:
    # Keep a reference to the dependency generator: if it were garbage-collected,
    # its `with` block would exit and close the HTTP client before we use it.
    dependency = get_arxiv_client()
    try:
        metadata = next(dependency).fetch_metadata("1706.03762")
    finally:
        dependency.close()

    assert metadata.title == "Attention Is All You Need"
    assert "Ashish Vaswani" in metadata.authors
