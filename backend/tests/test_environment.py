from __future__ import annotations

import importlib
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import env  # type: ignore[import-not-found]


def test_validate_environment_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REALISONS_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        env.validate_environment()


def test_health_check_endpoint_flags_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REALISONS_SECRET_KEY", "another-test-secret")
    # Prometheus collectors are module-level singletons, so importing the
    # application twice during the same test session (via ``reload``) would
    # otherwise try to re-register the same metrics and raise.  Explicitly
    # unregister the previous collectors to keep the test isolated.
    from prometheus_client import REGISTRY

    import app.main as main  # type: ignore[import-not-found]

    for collector in (
        getattr(main, "REQUEST_DURATION", None),
        getattr(main, "REQUEST_COUNT", None),
        getattr(main, "DATABASE_HEALTH", None),
        getattr(main, "CACHE_HEALTH", None),
    ):
        if collector is None:
            continue
        try:
            REGISTRY.unregister(collector)
        except KeyError:  # pragma: no cover - defensive guard
            pass

    importlib.reload(main)
    with TestClient(main.app) as client:
        response = client.get("/healthz")
        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["missing"] == []
        assert body["insecure"] == []
