from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, procedures_db, runs_db

client = TestClient(app)


def setup_function() -> None:
    procedures_db.clear()
    runs_db.clear()


def get_token(username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_run_creation_requires_procedure_id() -> None:
    user_token = get_token("bob", "userpass")
    response = client.post("/runs", json={}, headers=auth_header(user_token))
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure() -> None:
    user_token = get_token("bob", "userpass")
    response = client.post(
        "/runs",
        json={"procedure_id": "missing"},
        headers=auth_header(user_token),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def test_procedure_creation_requires_steps_structure() -> None:
    admin_token = get_token("alice", "adminpass")
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
