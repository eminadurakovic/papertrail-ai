"""Small helpers for creating test data."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Author, Paper, PaperAuthor


def make_paper(
    db: Session,
    arxiv_id: str = "2401.00001",
    *,
    title: str = "A Test Paper",
    authors: list[str] | None = None,
) -> Paper:
    # Look up existing authors before building the paper, so autoflush never sees half-built rows.
    author_rows = [
        db.scalar(select(Author).where(Author.name == name)) or Author(name=name)
        for name in authors or []
    ]
    paper = Paper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=f"Abstract of {title}.",
        published_date=date(2024, 1, 15),
        source_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        author_links=[
            PaperAuthor(author=author, position=position)
            for position, author in enumerate(author_rows)
        ],
    )
    db.add(paper)
    # Commit like the real import does; the test's outer transaction still rolls it back.
    db.commit()
    return paper
