"""Validation tests for API payloads."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_run_creation_requires_procedure_id(client: TestClient, token_headers) -> None:
    user_headers = token_headers("bob", "userpass")
    response = client.post("/runs", json={}, headers=user_headers)
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure(client: TestClient, token_headers) -> None:
    user_headers = token_headers("bob", "userpass")
    response = client.post(
        "/runs",
        json={"procedure_id": "missing"},
        headers=user_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def test_procedure_creation_requires_steps_structure(client: TestClient, token_headers) -> None:
    admin_headers = token_headers("alice", "adminpass")
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
    response = client.post("/procedures", json=payload, headers=admin_headers)
    assert response.status_code == 422
