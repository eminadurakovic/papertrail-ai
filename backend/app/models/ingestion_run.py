from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestionRun(Base):
    """One attempt to import a paper. Kept even when it fails, as a simple audit log."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The identifier the user asked for, stored as given (it may be invalid).
    requested_arxiv_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[IngestionRunStatus] = mapped_column(
        Enum(
            IngestionRunStatus,
            name="status",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda statuses: [s.value for s in statuses],
        ),
        default=IngestionRunStatus.RUNNING,
        server_default=IngestionRunStatus.RUNNING.value,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
