"""Réalisons backend package."""

from __future__ import annotations

import os
from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from .main import app as app


def __getattr__(name: str) -> Any:  # pragma: no cover - thin wrapper
    if name == "app":
        module = import_module("app.main")
        return module.app
    raise AttributeError(f"module '{__name__}' has no attribute {name!r}")


if not os.getenv("RBOK_SKIP_MAIN_IMPORT"):
    from .main import app

    __all__ = ["app"]
else:  # pragma: no cover - used for tooling (e.g. Alembic)
    __all__ = []
