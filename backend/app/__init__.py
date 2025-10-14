"""Réalisons backend package."""

from importlib import import_module
from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        module = import_module(".main", __name__)
        return module.app
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from .main import app as app


def __getattr__(name: str):  # pragma: no cover - thin wrapper
    if name == "app":
        module = import_module("app.main")
        return module.app
    raise AttributeError(f"module 'app' has no attribute {name!r}")

import os

if not os.getenv("RBOK_SKIP_MAIN_IMPORT"):
    from .main import app

    __all__ = ["app"]
else:  # pragma: no cover - used for tooling (e.g. Alembic)
    __all__ = []
