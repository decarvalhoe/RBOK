"""Tests for input validation."""
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


def test_run_creation_requires_procedure_id(client: TestClient) -> None:
    """Test that creating a run requires a procedure ID."""
    user_token = get_token(client, "bob", "userpass")
    
    response = client.post(
        "/runs",
        json={},
        headers=auth_header(user_token),
    )
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure(client: TestClient) -> None:
    """Test that creating a run requires an existing procedure."""
    user_token = get_token(client, "bob", "userpass")
    
    response = client.post(
        "/runs",
        json={"procedure_id": "missing"},
        headers=auth_header(user_token),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def test_procedure_creation_requires_steps_structure(client: TestClient) -> None:
    """Test that procedure creation validates step structure."""
    admin_token = get_token(client, "alice", "adminpass")
    
    payload = {
        "name": "Demo",
        "description": "A sample procedure",
        "steps": [
            {
                "key": "step-1",
                "title": "First Step",
                "prompt": "Do something",
                "slots": [],
            }
        ],
    }
    
    response = client.post("/procedures", json=payload, headers=auth_header(admin_token))
    assert response.status_code == 201
    data = response.json()
    assert len(data["steps"]) == 1
    assert data["steps"][0]["key"] == "step-1"
