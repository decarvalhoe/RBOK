from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.auth import User, get_current_user, get_current_user_optional
from app.main import app


@pytest.fixture()
def admin_user() -> User:
    return User(
        subject="admin",
        username="admin",
        email="admin@example.com",
        roles=["app-admin"],
        role="admin",
    )


@pytest.fixture(autouse=True)
def override_auth_dependencies(admin_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_current_user_optional] = lambda: admin_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


def _build_procedure_payload() -> Dict[str, Any]:
    return {
        "id": "demo-procedure",
        "name": "Identity verification",
        "description": "Two-step KYC flow",
        "steps": [
            {
                "key": "collect_email",
                "title": "Collect email",
                "prompt": "Please provide your contact email",
                "slots": [
                    {
                        "name": "email",
                        "type": "string",
                        "required": True,
                        "label": "Email",
                    },
                ],
                "checklists": [
                    {
                        "key": "privacy_ack",
                        "label": "Privacy notice acknowledged",
                        "required": True,
                    },
                ],
            },
            {
                "key": "verify_document",
                "title": "Verify document",
                "prompt": "Upload your passport",
                "slots": [
                    {
                        "name": "document",
                        "type": "string",
                        "required": True,
                        "label": "Document",
                    },
                ],
                "checklists": [],
            },
        ],
    }


def test_create_and_list_procedures(client: TestClient) -> None:
    payload = _build_procedure_payload()

    response = client.post("/procedures", json=payload)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["id"] == payload["id"]
    assert created["name"] == payload["name"]
    assert created["steps"][0]["key"] == "collect_email"
    assert created["steps"][0]["position"] == 0
    assert created["steps"][0]["checklists"][0]["key"] == "privacy_ack"

    list_response = client.get("/procedures")
    assert list_response.status_code == 200
    procedures = list_response.json()
    assert len(procedures) == 1
    assert procedures[0]["name"] == payload["name"]
    assert procedures[0]["steps"][1]["key"] == "verify_document"

    detail_response = client.get(f"/procedures/{created['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == created["id"]
    assert detail["steps"][0]["slots"][0]["label"] == "Email"


def test_procedure_lifecycle_generates_audit_trail(
    client: TestClient, test_session
) -> None:
    create_response = client.post("/procedures", json=_build_procedure_payload())
    assert create_response.status_code == 201

    procedure_id = create_response.json()["id"]

    run_response = client.post(
        "/runs",
        json={"procedure_id": procedure_id, "user_id": "operator"},
    )
    assert run_response.status_code == 201
    run_payload = run_response.json()
    assert run_payload["state"] == "pending"
    assert run_payload["step_states"] == []
    assert run_payload["checklist_states"] == []

    first_commit = client.post(
        f"/runs/{run_payload['id']}/commit-step",
        json={
            "step_key": "collect_email",
            "slots": {"email": "agent@example.com"},
            "checklist": [
                {"key": "privacy_ack", "completed": True},
            ],
        },
    )
    assert first_commit.status_code == 200, first_commit.text
    first_state = first_commit.json()
    assert first_state["state"] == "in_progress"
    assert len(first_state["step_states"]) == 1
    assert first_state["step_states"][0]["payload"]["slots"] == {
        "email": "agent@example.com"
    }
    assert first_state["checklist_states"][0]["key"] == "privacy_ack"
    assert first_state["checklist_states"][0]["completed"] is True

    second_commit = client.post(
        f"/runs/{run_payload['id']}/commit-step",
        json={
            "step_key": "verify_document",
            "slots": {"document": "passport"},
            "checklist": [],
        },
    )
    assert second_commit.status_code == 200, second_commit.text
    final_state = second_commit.json()
    assert final_state["state"] == "completed"
    assert final_state["closed_at"] is not None
    assert len(final_state["step_states"]) == 2

    refreshed = client.get(f"/runs/{run_payload['id']}")
    assert refreshed.status_code == 200
    refreshed_payload = refreshed.json()
    assert refreshed_payload["state"] == "completed"

    events = test_session.execute(
        select(models.AuditEvent).order_by(models.AuditEvent.occurred_at)
    ).scalars().all()
    actions = [event.action for event in events]
    assert actions.count("procedure.created") == 1
    assert actions.count("run.created") == 1
    assert actions.count("run.step_committed") == 2
    assert actions.count("run.updated") == 2


def test_get_unknown_procedure_returns_404(client: TestClient) -> None:
    response = client.get("/procedures/unknown")
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"
