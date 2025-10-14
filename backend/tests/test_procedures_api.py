from __future__ import annotations

from typing import Dict

import pytest

from app.auth import User, get_current_user, get_current_user_optional
from app.main import app


@pytest.fixture()
def admin_user() -> User:
    return User(subject="admin", username="admin", email="admin@example.com", roles=["app-admin"], role="admin")


@pytest.fixture(autouse=True)
def override_auth_dependencies(admin_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_current_user_optional] = lambda: admin_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


def test_create_and_list_procedures(client) -> None:
    payload: Dict[str, object] = {
        "name": "Identity verification",
        "description": "Two-step KYC flow",
        "steps": [
            {
                "key": "collect_email",
                "title": "Collect email",
                "prompt": "Please provide your contact email",
                "slots": [
                    {"name": "email", "type": "email", "required": True},
                ],
                "checklist": [
                    {"name": "privacy_ack", "required": True},
                ],
            },
            {
                "key": "verify_document",
                "title": "Verify document",
                "prompt": "Upload your passport",
                "slots": [
                    {"name": "document", "type": "string", "required": True},
                ],
                "checklist": [],
            },
        ],
    }

    response = client.post("/procedures", json=payload)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == payload["name"]
    assert len(created["steps"]) == 2
    assert created["steps"][0]["key"] == "collect_email"
    assert created["steps"][0]["position"] == 0

    list_response = client.get("/procedures")
    assert list_response.status_code == 200
    procedures = list_response.json()
    assert len(procedures) == 1
    assert procedures[0]["name"] == payload["name"]

    detail_response = client.get(f"/procedures/{created['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == created["id"]
    assert detail["steps"][1]["key"] == "verify_document"


def test_duplicate_step_keys_return_error(client) -> None:
    payload = {
        "name": "Invalid procedure",
        "description": "Steps share a key",
        "steps": [
            {
                "key": "step",
                "title": "One",
                "prompt": "Do A",
                "slots": [],
                "checklist": [],
            },
            {
                "key": "step",
                "title": "Two",
                "prompt": "Do B",
                "slots": [],
                "checklist": [],
            },
        ],
    }

    response = client.post("/procedures", json=payload)
    assert response.status_code == 400
    assert "Duplicate" in response.json()["detail"]


def test_get_unknown_procedure_returns_404(client) -> None:
    response = client.get("/procedures/unknown")
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"
