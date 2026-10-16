"""Database engine and session factory."""

from collections.abc import Iterator

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(url: URL | str | None = None) -> Engine:
    """Create a SQLAlchemy engine. Creating an engine does not open a connection yet."""
    return create_engine(url or get_settings().database_url, pool_pre_ping=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection(db_engine: Engine = engine) -> bool:
    """Return True if a trivial query succeeds against the database."""
    with db_engine.connect() as connection:
        return bool(connection.execute(text("SELECT 1")).scalar_one() == 1)
