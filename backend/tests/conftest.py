"""Test fixtures: a separate test database built with Alembic; each test is rolled back."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import get_arxiv_client, get_embedder, get_llm, get_pdf_downloader
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from tests.arxiv_fakes import FakeArxiv
from tests.fake_embedder import FakeEmbedder
from tests.fake_llm import FakeLLM
from tests.pdf_fakes import FakePdfServer

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(url: URL) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return config


def _create_database_if_missing(url: URL) -> None:
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            ).scalar()
            if not exists:
                quoted = admin_engine.dialect.identifier_preparer.quote(str(url.database))
                connection.execute(text(f"CREATE DATABASE {quoted}"))
    except OperationalError as exc:
        pytest.exit(
            f"PostgreSQL is not reachable at {url.host}:{url.port}. "
            f"Start it with `docker compose up -d`.\n{exc.orig}",
            returncode=1,
        )
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> URL:
    settings = get_settings()
    return settings.database_url.set(database=f"{settings.postgres_db}_test")


@pytest.fixture(scope="session")
def engine(test_database_url: URL) -> Iterator[Engine]:
    _create_database_if_missing(test_database_url)
    config = alembic_config(test_database_url)
    command.downgrade(config, "base")  # start from an empty schema every run
    command.upgrade(config, "head")

    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A session whose changes are rolled back after the test, even if it commits."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def fake_arxiv() -> FakeArxiv:
    return FakeArxiv()


@pytest.fixture
def fake_pdf_server() -> FakePdfServer:
    return FakePdfServer()


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(
    db_session: Session,
    fake_arxiv: FakeArxiv,
    fake_pdf_server: FakePdfServer,
    fake_embedder: FakeEmbedder,
    fake_llm: FakeLLM,
) -> Iterator[TestClient]:
    """API client using the test session and fakes for every external dependency."""

    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arxiv_client] = fake_arxiv.client
    app.dependency_overrides[get_pdf_downloader] = fake_pdf_server.downloader
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_llm] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
