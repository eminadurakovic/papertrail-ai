"""Unhandled failures must produce JSON errors without internal details."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app


def make_client(error: Exception) -> Iterator[TestClient]:
    def broken_db() -> Iterator[Session]:
        raise error
        yield  # pragma: no cover  (makes this a generator, like the real dependency)

    app.dependency_overrides[get_db] = broken_db
    try:
        # raise_server_exceptions=False: behave like a real server and return the response.
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def db_down() -> Iterator[TestClient]:
    yield from make_client(OperationalError("SELECT 1", {}, Exception("password=hunter2")))


@pytest.fixture
def bug() -> Iterator[TestClient]:
    yield from make_client(RuntimeError("secret internal detail"))


def test_database_outage_returns_json_503(db_down: TestClient) -> None:
    response = db_down.get("/papers")

    assert response.status_code == 503
    assert response.json() == {"detail": "The database is unavailable. Try again later."}
    assert "hunter2" not in response.text


def test_unexpected_error_returns_json_500_without_internals(bug: TestClient) -> None:
    response = bug.get("/papers")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert "secret" not in response.text
    assert "Traceback" not in response.text
