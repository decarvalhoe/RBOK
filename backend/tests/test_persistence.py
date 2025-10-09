"""Tests for procedure and run persistence."""
from __future__ import annotations

from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import User, get_current_user, oauth2_scheme
from app.database import get_db
from app.main import app


@pytest.fixture()
def client(test_session: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database and auth overrides."""
    
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_session
        finally:
            test_session.rollback()
    
    app.dependency_overrides[get_db] = override_get_db
    
    def override_user() -> User:
        return User(subject="test", username="admin", roles=["app-admin"], role="admin")
    
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[oauth2_scheme] = lambda: "test-token"
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(oauth2_scheme, None)


def get_token(client: TestClient, username: str, password: str) -> str:
    """Helper function to obtain an authentication token."""
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    """Helper function to create authorization headers."""
    return {"Authorization": f"Bearer {token}"}


def test_create_and_fetch_procedure(client: TestClient) -> None:
    """Test creating and fetching a procedure."""
    admin_token = get_token(client, "alice", "adminpass")
    
    payload = {
        "name": "Test Procedure",
        "description": "Testing persistence",
        "steps": [
            {
                "key": "step-1",
                "title": "Step 1",
                "prompt": "Do something",
                "slots": [{"name": "slot1"}],
            },
            {
                "key": "step-2",
                "title": "Step 2",
                "prompt": "Do something else",
                "slots": [],
            },
        ],
    }
    
    response = client.post("/procedures", json=payload, headers=auth_header(admin_token))
    assert response.status_code == 201
    data = response.json()
    assert data["id"]
    assert data["name"] == payload["name"]
    assert len(data["steps"]) == 2
    
    list_response = client.get("/procedures")
    assert list_response.status_code == 200
    procedures = list_response.json()
    assert len(procedures) == 1
    assert procedures[0]["id"] == data["id"]
    
    get_response = client.get(f"/procedures/{data['id']}")
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["description"] == payload["description"]
    assert fetched["steps"][1]["key"] == "step-2"


def test_start_and_get_run(client: TestClient) -> None:
    """Test starting and fetching a procedure run."""
    admin_token = get_token(client, "alice", "adminpass")
    
    procedure_response = client.post(
        "/procedures",
        json={
            "name": "Run Procedure",
            "description": "For run test",
            "steps": [],
        },
        headers=auth_header(admin_token),
    )
    procedure_response.raise_for_status()
    procedure_id = procedure_response.json()["id"]
    
    user_token = get_token(client, "bob", "userpass")
    run_response = client.post(
        "/runs",
        json={"procedure_id": procedure_id},
        headers=auth_header(user_token),
    )
    assert run_response.status_code == 201
    run_data = run_response.json()
    assert run_data["procedure_id"] == procedure_id
    assert run_data["user_id"] == "bob"
    assert run_data["state"] == "started"
    
    update_response = client.patch(
        f"/runs/{run_data['id']}",
        json={"state": "completed"},
        headers=auth_header(user_token),
    )
    assert update_response.status_code == 200
    updated_run = update_response.json()
    assert updated_run["state"] == "completed"
