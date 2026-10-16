import pytest

from app.services.chunking import Chunk, chunk_pages, clean_text
from tests.pdf_fakes import numbered_words

# --- clean_text ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  many   spaces\n\nand\tlines  ", "many spaces and lines"),
        ("ﬁne-tuning with ﬂoat", "fine-tuning with float"),  # ligatures
        ("trans-\nformer", "transformer"),  # hyphenated line break
        ("trans- \n  former", "transformer"),
        ("state-of-the-art", "state-of-the-art"),  # real hyphens stay
        ("null\x00byte and\x07bell", "null byte and bell"),  # control characters removed
        ("", ""),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


# --- chunk_pages ---------------------------------------------------------------


def test_no_text_gives_no_chunks() -> None:
    assert chunk_pages([], size=5, overlap=2) == []
    assert chunk_pages(["", "   "], size=5, overlap=2) == []


def test_short_text_gives_one_chunk() -> None:
    assert chunk_pages(["a b c"], size=5, overlap=2) == [Chunk(position=0, text="a b c", page=1)]


def test_documented_example() -> None:
    chunks = chunk_pages(["a b c d e f g h"], size=5, overlap=2)

    assert [c.text for c in chunks] == ["a b c d e", "d e f g h"]


def test_text_exactly_one_chunk_long_does_not_create_an_extra_chunk() -> None:
    chunks = chunk_pages([" ".join(numbered_words(5))], size=5, overlap=2)

    assert len(chunks) == 1


def test_consecutive_chunks_share_exactly_overlap_words() -> None:
    chunks = chunk_pages([" ".join(numbered_words(100))], size=20, overlap=5)

    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.text.split()[-5:] == current.text.split()[:5]


def test_zero_overlap_partitions_the_text() -> None:
    chunks = chunk_pages([" ".join(numbered_words(10))], size=4, overlap=0)

    assert [c.text for c in chunks] == ["w0 w1 w2 w3", "w4 w5 w6 w7", "w8 w9"]


def test_every_word_is_covered_in_order() -> None:
    words = numbered_words(237)
    size, overlap = 20, 5
    chunks = chunk_pages([" ".join(words)], size=size, overlap=overlap)

    rebuilt = chunks[0].text.split()
    for chunk in chunks[1:]:
        rebuilt += chunk.text.split()[overlap:]
    assert rebuilt == words
    assert all(len(c.text.split()) <= size for c in chunks)


def test_positions_are_sequential_from_zero() -> None:
    chunks = chunk_pages([" ".join(numbered_words(100))], size=10, overlap=3)

    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_chunking_is_deterministic() -> None:
    pages = [" ".join(numbered_words(80, "p1_")), " ".join(numbered_words(80, "p2_"))]

    assert chunk_pages(pages, size=25, overlap=5) == chunk_pages(pages, size=25, overlap=5)


def test_chunks_cross_page_boundaries_and_record_starting_page() -> None:
    pages = ["a b c", "", "d e f g"]  # page 2 is blank

    chunks = chunk_pages(pages, size=4, overlap=1)

    assert [(c.text, c.page) for c in chunks] == [("a b c d", 1), ("d e f g", 3)]


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (-1, 0), (5, 5), (5, 6), (5, -1)])
def test_invalid_settings_are_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_pages(["a b c"], size=size, overlap=overlap)
