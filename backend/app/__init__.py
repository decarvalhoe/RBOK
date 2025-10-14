"""Réalisons backend package."""

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


__all__ = ["app"]
