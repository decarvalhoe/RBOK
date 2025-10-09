from __future__ import annotations

from fastapi.testclient import TestClient


def get_token(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_create_procedure_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/procedures",
        json={
            "name": "Procédure de test",
            "description": "Une description",
            "steps": [],
        },
    )
    assert response.status_code == 401


def test_create_procedure_requires_admin_role(client: TestClient, auth_header) -> None:
    user_token = get_token(client, "bob", "userpass")
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


def test_create_procedure_with_admin_succeeds(client: TestClient, auth_header) -> None:
    admin_token = get_token(client, "alice", "adminpass")
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


def test_start_run_requires_token_and_uses_requesting_user(
    client: TestClient, auth_header
) -> None:
    admin_token = get_token(client, "alice", "adminpass")
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

    response = client.post(
        "/runs",
        json={"procedure_id": procedure_id},
    )
    assert response.status_code == 401

    user_token = get_token(client, "bob", "userpass")
    response = client.post(
        "/runs",
        json={"procedure_id": procedure_id},
        headers=auth_header(user_token),
    )
    assert response.status_code == 201
    run_body = response.json()
    assert run_body["procedure_id"] == procedure_id
    assert run_body["user_id"] == "bob"
