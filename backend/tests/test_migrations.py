from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import URL, Engine, inspect

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.db.base import Base
from tests.conftest import alembic_config

APP_TABLES = {"papers", "authors", "paper_authors", "passages", "ingestion_runs"}


def test_migration_creates_expected_tables(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())

    assert tables == APP_TABLES | {"alembic_version"}


def test_models_and_migrations_are_in_sync(engine: Engine) -> None:
    """Fails if someone changes a model without writing a migration (or vice versa)."""
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []


def test_migration_can_be_downgraded_and_reapplied(engine: Engine, test_database_url: URL) -> None:
    config = alembic_config(test_database_url)

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) & APP_TABLES == set()

    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) >= APP_TABLES
