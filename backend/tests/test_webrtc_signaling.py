from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_session_persists_offer(client: TestClient) -> None:
    payload = {
        "client_id": "caller-1",
        "offer_sdp": "v=0\r\no=- 46117392 2 IN IP4 127.0.0.1\r\n",
        "metadata": {"role": "initiator"},
    }

    response = client.post("/webrtc/sessions", json=payload)
    body = response.json()

    assert response.status_code == 201
    assert body["client_id"] == payload["client_id"]
    assert body["offer_sdp"] == payload["offer_sdp"]
    assert body["metadata"] == payload["metadata"]
    assert body["status"] == "awaiting_answer"
    assert body["ice_candidates"] == []

    session_id = body["id"]
    follow_up = client.get(f"/webrtc/sessions/{session_id}")
    assert follow_up.status_code == 200
    assert follow_up.json()["id"] == session_id


def test_answer_and_candidate_flow(client: TestClient) -> None:
    create_response = client.post(
        "/webrtc/sessions",
        json={
            "client_id": "caller-2",
            "offer_sdp": "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\n",
            "metadata": {"room": "alpha"},
        },
    )
    session_id = create_response.json()["id"]

    answer_response = client.post(
        f"/webrtc/sessions/{session_id}/answer",
        json={
            "responder_id": "responder-1",
            "answer_sdp": "v=0\r\no=- 3 4 IN IP4 127.0.0.1\r\n",
            "responder_metadata": {"role": "helper"},
        },
    )
    assert answer_response.status_code == 200
    answer_body = answer_response.json()
    assert answer_body["status"] == "answered"
    assert answer_body["responder_id"] == "responder-1"
    assert answer_body["responder_metadata"] == {"role": "helper"}

    candidate_response = client.post(
        f"/webrtc/sessions/{session_id}/candidates",
        json={
            "candidate": {
                "candidate": "candidate:1 1 UDP 2122252543 192.0.2.1 3478 typ host",
                "sdpMid": "0",
                "sdpMLineIndex": 0,
            }
        },
    )
    assert candidate_response.status_code == 200
    candidates = candidate_response.json()["ice_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["sdpMid"] == "0"

    close_response = client.post(f"/webrtc/sessions/{session_id}/close")
    assert close_response.status_code == 200
    assert close_response.json()["status"] == "closed"


def test_webrtc_config_hides_empty_values(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("WEBRTC_STUN_SERVERS", "stun:stun.example.com:3478")
    monkeypatch.setenv("WEBRTC_TURN_SERVERS", "turns:turn.example.com:5349")
    monkeypatch.setenv("WEBRTC_TURN_USERNAME", "demo-user")
    monkeypatch.setenv("WEBRTC_TURN_PASSWORD", "demo-pass")

    response = client.get("/webrtc/config")
    assert response.status_code == 200
    body = response.json()

    assert body["ice_servers"][0]["urls"] == ["stun:stun.example.com:3478"]
    assert body["ice_servers"][1]["username"] == "demo-user"
    assert body["ice_servers"][1]["credential"] == "demo-pass"
