import pytest

from app.services.arxiv import InvalidArxivIdError, normalize_arxiv_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1706.03762", "1706.03762"),
        ("0704.0001", "0704.0001"),  # first new-style ID (4-digit number)
        ("2403.12345", "2403.12345"),
        ("2403.12345v2", "2403.12345"),  # version suffix is dropped
        ("  2403.12345  ", "2403.12345"),  # surrounding whitespace
        ("arXiv:2403.12345", "2403.12345"),
        ("arxiv:2403.12345v11", "2403.12345"),
        ("hep-th/9901001", "hep-th/9901001"),  # old-style
        ("math.GT/0309136v1", "math.GT/0309136"),  # old-style with subject class
    ],
)
def test_valid_ids_are_normalized(raw: str, expected: str) -> None:
    assert normalize_arxiv_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not-an-id",
        "2403.123",  # too few digits
        "2403.123456",  # too many digits
        "24031.2345",
        "2403.12345v",  # empty version
        "https://arxiv.org/abs/2403.12345",  # URLs are not accepted
        "2403.12345; DROP TABLE papers",
        "HEP-TH/9901001",  # archive names are lower-case
    ],
)
def test_invalid_ids_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidArxivIdError):
        normalize_arxiv_id(raw)
