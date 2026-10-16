"""ORM models. Importing this package registers every table on Base.metadata (used by Alembic)."""

from app.models.author import Author, PaperAuthor
from app.models.ingestion_run import IngestionRun, IngestionRunStatus
from app.models.paper import Paper, PaperStatus
from app.models.passage import Passage

__all__ = [
    "Author",
    "IngestionRun",
    "IngestionRunStatus",
    "Paper",
    "PaperAuthor",
    "PaperStatus",
    "Passage",
]
