from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.config import Settings, get_settings
from app.main import app, configure_rate_limiter


def test_requests_are_throttled_when_limit_exceeded():
    test_settings = Settings(rate_limit_default="1/minute")
    app.dependency_overrides[get_settings] = lambda: test_settings
    configure_rate_limiter(app, test_settings)

    with TestClient(app) as client:
        first = client.get("/health")
        assert first.status_code == 200

        second = client.get("/health")
        assert second.status_code == 429
        body = second.json()
        assert body["error"].startswith("Rate limit exceeded")
        assert "Retry-After" in second.headers
        assert second.headers.get("X-RateLimit-Limit") is not None

    app.dependency_overrides.pop(get_settings, None)
    configure_rate_limiter(app, get_settings())
