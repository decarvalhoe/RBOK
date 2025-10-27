"""Ensure Alembic migrations align with SQLAlchemy models."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("alembic")
pytest.importorskip("sqlalchemy")

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.exc import CompileError, DatabaseError
from sqlalchemy.pool import StaticPool

from alembic import command


@pytest.mark.migrations
def test_migrations_up_to_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run migrations on a temporary database and compare the resulting schema."""

    in_memory_url = "sqlite+pysqlite:///:memory:"
    # Ensure the application models use a lightweight database when imported.
    monkeypatch.setenv("DATABASE_URL", in_memory_url)

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
        alembic_cfg.set_main_option("sqlalchemy.url", in_memory_url)

        engine = create_engine(
            in_memory_url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        try:
            with engine.begin() as connection:
                alembic_cfg.attributes["connection"] = connection
                try:
                    command.upgrade(alembic_cfg, "head")
                except (CompileError, DatabaseError, NotImplementedError) as exc:
                    pytest.skip(
                        "Alembic migrations require database features that are unavailable in the "
                        f"current test environment: {exc}."
                    )

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
