import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.main import app, procedures_db, runs_db  # noqa: E402

client = TestClient(app)


def get_token(username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def setup_module(module):  # noqa: D401 - pytest style hook
    """Ensure the in-memory stores are reset before the test module runs."""

    procedures_db.clear()
    runs_db.clear()


def teardown_function(function):
    procedures_db.clear()
    runs_db.clear()


def test_create_procedure_requires_authentication():
    response = client.post(
        "/procedures",
        json={
            "name": "Procédure de test",
            "description": "Une description",
            "steps": [],
        },
    )
    assert response.status_code == 401


def test_create_procedure_requires_admin_role():
    user_token = get_token("bob", "userpass")
    response = client.post(
        "/procedures",
        json={
            "name": "Procédure utilisateur",
            "description": "Une description",
            "steps": [],
        },
        headers=auth_header(user_token),
    )
    assert response.status_code == 403


def test_create_procedure_with_admin_succeeds():
    admin_token = get_token("alice", "adminpass")
    response = client.post(
        "/procedures",
        json={
            "name": "Procédure admin",
            "description": "Une description",
            "steps": [],
        },
        headers=auth_header(admin_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Procédure admin"
    assert body["id"]


def test_start_run_requires_token_and_uses_requesting_user():
    admin_token = get_token("alice", "adminpass")
    proc_response = client.post(
        "/procedures",
        json={
            "name": "Procédure exécution",
            "description": "Une description",
            "steps": [],
        },
        headers=auth_header(admin_token),
    )
    procedure_id = proc_response.json()["id"]

    response = client.post("/runs", params={"procedure_id": procedure_id})
    assert response.status_code == 401

    user_token = get_token("bob", "userpass")
    response = client.post(
        "/runs",
        params={"procedure_id": procedure_id},
        headers=auth_header(user_token),
    )
    assert response.status_code == 201
    run_body = response.json()
    assert run_body["procedure_id"] == procedure_id
    assert run_body["user_id"] == "bob"
