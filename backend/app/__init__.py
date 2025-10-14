"""Réalisons backend package."""

import os

if not os.getenv("RBOK_SKIP_MAIN_IMPORT"):
    from .main import app

    __all__ = ["app"]
else:  # pragma: no cover - used for tooling (e.g. Alembic)
    __all__ = []
