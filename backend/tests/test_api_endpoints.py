from __future__ import annotations

from fastapi.testclient import TestClient  # FastAPI's official testing client

from app.config import Settings
from app.main import app, get_settings


def test_root_endpoint_reports_status(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_endpoint_includes_environment_analysis(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["missing"] == []
    assert payload["insecure"] == []


def test_chat_endpoint_echoes_message_in_french(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "Bonjour"})

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"].startswith("Message reçu: Bonjour")


def test_chat_endpoint_validates_non_empty_messages(client: TestClient) -> None:
    response = client.post("/chat", json={"message": ""})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"][-1] == "message" for error in detail)


def test_webrtc_config_alias_uses_application_settings(client: TestClient) -> None:
    test_settings = Settings(
        allow_origins=["https://example.com"],
        webrtc_stun_servers=["stun:stun.example.com:3478"],
        webrtc_turn_servers=["turns:turn.example.com:5349"],
        webrtc_turn_username="turn-user",
        webrtc_turn_password="turn-pass",
    )

    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        response = client.get("/config/webrtc")

        assert response.status_code == 200
        body = response.json()
        assert body["ice_servers"][0]["urls"] == ["stun:stun.example.com:3478"]
        assert body["ice_servers"][1]["urls"] == ["turns:turn.example.com:5349"]
        assert body["ice_servers"][1]["username"] == "turn-user"
        assert body["ice_servers"][1]["credential"] == "turn-pass"
    finally:
        app.dependency_overrides.pop(get_settings, None)
