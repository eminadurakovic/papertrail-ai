"""Text cleanup and deterministic chunking. Pure functions: no I/O, no randomness.

Chunking algorithm (sliding window over words):
  1. Split all pages into one list of words, remembering each word's page number.
  2. Take `size` words as a chunk, then move the window forward by `size - overlap`.
  3. Stop once a window reaches the last word.

Example with size=5, overlap=2 (step=3), words a..h:
    chunk 0: a b c d e
    chunk 1:       d e f g h    <- "d e" is the overlap
Same input + same settings => exactly the same chunks.
"""

import re
import unicodedata
from dataclasses import dataclass

# A word split across lines with a hyphen: "trans-\n former" -> "transformer".
_HYPHENATED_LINE_BREAK = re.compile(r"(\w)-[ \t]*\n[ \t]*(\w)")


@dataclass(frozen=True)
class Chunk:
    position: int  # 0-based order within the paper
    text: str
    page: int  # 1-based page on which the chunk starts


def clean_text(text: str) -> str:
    """Normalize extracted PDF text into single-spaced plain text."""
    # NFKC turns typographic ligatures like "ﬁ" into "fi" and full-width forms into ASCII.
    text = unicodedata.normalize("NFKC", text)
    text = _HYPHENATED_LINE_BREAK.sub(r"\1\2", text)
    # Postgres TEXT cannot store NUL bytes; other control characters are just noise.
    text = "".join(char if char.isprintable() or char.isspace() else " " for char in text)
    return " ".join(text.split())


def chunk_pages(pages: list[str], size: int, overlap: int) -> list[Chunk]:
    """Split page texts into overlapping word windows (see module docstring)."""
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be between 0 and size - 1")

    words = [
        (word, page_number)
        for page_number, page_text in enumerate(pages, start=1)
        for word in page_text.split()
    ]

    chunks: list[Chunk] = []
    step = size - overlap
    for start in range(0, len(words), step):
        window = words[start : start + size]
        chunks.append(
            Chunk(
                position=len(chunks),
                text=" ".join(word for word, _ in window),
                page=window[0][1],
            )
        )
        if start + size >= len(words):
            break
    return chunks
