"""Ensure Alembic migrations align with SQLAlchemy models."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine


@pytest.mark.migrations
def test_migrations_up_to_date(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run migrations on a temporary database and compare the resulting schema."""

    db_file = tmp_path / "migrations.sqlite"
    database_url = f"sqlite+pysqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    modules_to_reset = ["app.database", "app.models"]
    original_modules: dict[str, ModuleType | None] = {
        name: sys.modules.get(name) for name in modules_to_reset
    }
    for name in modules_to_reset:
        sys.modules.pop(name, None)

    diffs: list[object]
    try:
        importlib.import_module("app.database")
        models = importlib.import_module("app.models")

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        alembic_cfg = Config(str(config_path))
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(database_url, future=True)
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                diffs = compare_metadata(context, models.Base.metadata)
        finally:
            engine.dispose()
    finally:
        for name, module in original_modules.items():
            if module is not None:
                sys.modules[name] = module
            else:
                sys.modules.pop(name, None)

    assert diffs == [], f"Found differences between migrations and models: {diffs!r}"
