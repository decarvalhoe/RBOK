from __future__ import annotations

import importlib

import pytest


def test_settings_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_GATEWAY_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    import ai_gateway.config as config

    importlib.reload(config)
    config.get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        config.get_settings()
