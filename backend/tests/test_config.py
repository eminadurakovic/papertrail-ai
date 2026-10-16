from pathlib import Path

import pytest

from app.core.config import Settings

ENV_VARS = [
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "LOG_LEVEL",
    "CHUNK_SIZE_WORDS",
    "CHUNK_OVERLAP_WORDS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure the developer's shell environment doesn't leak into these tests."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_used_without_env() -> None:
    settings = Settings(_env_file=None)

    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5433
    assert settings.postgres_db == "papertrail"


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "6000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.postgres_host == "db.internal"
    assert settings.postgres_port == 6000
    assert settings.log_level == "DEBUG"


def test_values_are_read_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_DB=from_file\nPOSTGRES_PORT=7777\n")

    settings = Settings(_env_file=env_file)

    assert settings.postgres_db == "from_file"
    assert settings.postgres_port == 7777


def test_invalid_port_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PORT", "not-a-number")

    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_chunk_overlap_must_be_smaller_than_chunk_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUNK_SIZE_WORDS", "50")
    monkeypatch.setenv("CHUNK_OVERLAP_WORDS", "50")

    with pytest.raises(ValueError, match="chunk_overlap_words"):
        Settings(_env_file=None)


def test_chunk_settings_can_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUNK_SIZE_WORDS", "200")
    monkeypatch.setenv("CHUNK_OVERLAP_WORDS", "0")

    settings = Settings(_env_file=None)

    assert (settings.chunk_size_words, settings.chunk_overlap_words) == (200, 0)
