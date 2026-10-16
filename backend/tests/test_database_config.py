from sqlalchemy import Engine

from app.core.config import Settings
from app.db.session import build_engine, check_database_connection


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_user": "alice",
        "postgres_password": "secret",
        "postgres_db": "papers",
        "postgres_host": "localhost",
        "postgres_port": 5433,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_database_url_uses_psycopg_driver_and_settings() -> None:
    url = make_settings().database_url

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "alice"
    assert url.password == "secret"
    assert url.host == "localhost"
    assert url.port == 5433
    assert url.database == "papers"


def test_database_url_escapes_special_characters_in_password() -> None:
    url = make_settings(postgres_password="p@ss:w/rd").database_url

    rendered = url.render_as_string(hide_password=False)
    assert "p%40ss%3Aw%2Frd" in rendered
    assert url.password == "p@ss:w/rd"


def test_database_url_hides_password_when_printed() -> None:
    url = make_settings().database_url

    assert "secret" not in str(url)


def test_engine_can_be_built_without_connecting() -> None:
    engine = build_engine(make_settings(postgres_port=1).database_url)

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_can_connect_to_test_database(engine: Engine) -> None:
    assert check_database_connection(engine) is True
