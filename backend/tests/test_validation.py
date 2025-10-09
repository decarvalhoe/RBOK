from __future__ import annotations

from fastapi.testclient import TestClient


def get_token(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def test_run_creation_requires_procedure_id(client: TestClient, auth_header) -> None:
    user_token = get_token(client, "bob", "userpass")
    response = client.post(
        "/runs",
        json={},
        headers=auth_header(user_token),
    )
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure(client: TestClient, auth_header) -> None:
    user_token = get_token(client, "bob", "userpass")
    response = client.post(
        "/runs",
        json={"procedure_id": "missing"},
        headers=auth_header(user_token),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def test_procedure_creation_requires_steps_structure(client: TestClient, auth_header) -> None:
    admin_token = get_token(client, "alice", "adminpass")
    payload = {
        "name": "Demo",
        "description": "A sample procedure",
        "steps": [
            {
                "key": "step-1",
                "title": "Title",
                "prompt": "Prompt",
                "slots": {"not": "a list"},
            }
        ],
    }
    response = client.post("/procedures", json=payload, headers=auth_header(admin_token))
    assert response.status_code == 422
