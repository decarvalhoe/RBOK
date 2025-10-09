"""Integration tests covering authentication and authorization."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_procedure_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/procedures",
        json={"name": "Procédure", "description": "Desc", "steps": []},
    )
    assert response.status_code == 401


def test_create_procedure_requires_admin_role(client: TestClient, token_headers) -> None:
    user_headers = token_headers("bob", "userpass")
    response = client.post(
        "/procedures",
        json={"name": "Procédure", "description": "Desc", "steps": []},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_create_procedure_with_admin_succeeds(client: TestClient, token_headers) -> None:
    admin_headers = token_headers("alice", "adminpass")
    response = client.post(
        "/procedures",
        json={"name": "Procédure admin", "description": "Desc", "steps": []},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Procédure admin"
    assert body["id"]


def test_start_run_requires_token_and_uses_requesting_user(
    client: TestClient, token_headers
) -> None:
    admin_headers = token_headers("alice", "adminpass")
    proc_response = client.post(
        "/procedures",
        json={"name": "Procédure exécution", "description": "Desc", "steps": []},
        headers=admin_headers,
    )
    proc_response.raise_for_status()
    procedure_id = proc_response.json()["id"]

    response = client.post(
        "/runs",
        json={"procedure_id": procedure_id},
    )
    assert response.status_code == 401

    user_headers = token_headers("bob", "userpass")
    response = client.post(
        "/runs",
        json={"procedure_id": procedure_id},
        headers=user_headers,
    )
    assert response.status_code == 201
    run_body = response.json()
    assert run_body["procedure_id"] == procedure_id
    assert run_body["user_id"] == "bob"
