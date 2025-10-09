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
    import app.main as main  # type: ignore[import-not-found]

    importlib.reload(main)
    with TestClient(main.app) as client:
        response = client.get("/healthz")
        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["missing"] == []
        assert body["insecure"] == []
