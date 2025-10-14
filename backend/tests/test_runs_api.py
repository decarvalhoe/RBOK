from __future__ import annotations

from typing import Dict

import pytest

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


@pytest.fixture()
def standard_user() -> User:
    return User(
        subject="user",
        username="user",
        email="user@example.com",
        roles=["app-user"],
        role="user",
    )


def _set_user(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _create_procedure(client, *, name: str) -> str:
    response = client.post(
        "/procedures",
        json={
            "name": name,
            "description": f"{name} workflow",
            "steps": [
                {
                    "key": "profile",
                    "title": "Profile",
                    "prompt": "Collect contact info",
                    "slots": [
                        {
                            "name": "email",
                            "type": "string",
                            "required": True,
                            "label": "Email",
                        }
                    ],
                    "checklists": [
                        {
                            "key": "consent",
                            "label": "Consent collected",
                            "required": True,
                        }
                    ],
                },
                {
                    "key": "verification",
                    "title": "Verification",
                    "prompt": "Upload ID",
                    "slots": [
                        {
                            "name": "document",
                            "type": "string",
                            "required": True,
                            "label": "Document",
                        }
                    ],
                    "checklists": [],
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_run_lifecycle_success(client, admin_user: User, standard_user: User) -> None:
    _set_user(admin_user)
    procedure_payload = {
        "name": "Customer onboarding",
        "description": "Collect profile and verify",
        "steps": [
            {
                "key": "profile",
                "title": "Profile",
                "prompt": "Collect contact info",
                "slots": [{"name": "email", "type": "email", "required": True}],
                "checklists": [
                    {"key": "consent", "label": "Consent", "required": True}
                ],
            },
            {
                "key": "verification",
                "title": "Verification",
                "prompt": "Upload ID",
                "slots": [{"name": "document", "type": "string", "required": True}],
                "checklists": [],
            },
        ],
    }
    create_response = client.post("/procedures", json=procedure_payload)
    assert create_response.status_code == 201
    procedure_id = create_response.json()["id"]
    procedure_id = _create_procedure(client, name="Customer onboarding")

    _set_user(standard_user)
    run_response = client.post(
        "/runs", json={"procedure_id": procedure_id, "user_id": "user-1"}
    )
    assert run_response.status_code == 201, run_response.text
    run_payload = run_response.json()
    assert run_payload["state"] == "pending"
    assert "checklist_statuses" in run_payload
    assert "checklist_progress" in run_payload
    assert run_payload["step_states"] == []

    commit_first = client.post(
        f"/runs/{run_payload['id']}/commit-step",
        json={
            "step_key": "profile",
            "slots": {"email": "user@example.com"},
            "checklist": [{"key": "consent", "completed": True}],
        },
    )
    assert commit_first.status_code == 200, commit_first.text
    first_state = commit_first.json()
    assert first_state["state"] == "in_progress"

    commit_second = client.post(
        f"/runs/{run_payload['id']}/commit-step",
        json={
            "step_key": "verification",
            "slots": {"document": "passport"},
            "checklist": [],
        },
    )
    assert commit_second.status_code == 200, commit_second.text
    assert commit_second.json()["state"] == "completed"

    final_state = client.get(f"/runs/{run_payload['id']}")
    assert final_state.status_code == 200
    payload = final_state.json()
    assert payload["state"] == "completed"
    assert payload["checklist_progress"]["percentage"] >= 0.0
    if payload["checklist_statuses"]:
        first_status = payload["checklist_statuses"][0]
        assert {"id", "label", "completed", "completed_le"} <= set(first_status.keys())


def test_commit_step_missing_slot_returns_422(
    client, admin_user: User, standard_user: User
) -> None:
    _set_user(admin_user)
    procedure_payload = {
        "name": "Restricted",
        "description": "Blocked by policy",
        "steps": [
            {
                "key": "only",
                "title": "Only",
                "prompt": "Do it",
                "slots": [],
                "checklists": [],
            }
        ],
    }
    create_response = client.post("/procedures", json=procedure_payload)
    assert create_response.status_code == 201
    procedure_id = create_response.json()["id"]

    patch_opa.denied_resources.add(procedure_id)
    _set_user(standard_user)
    denied = client.post("/runs", json={"procedure_id": procedure_id, "user_id": "user-2"})
    assert denied.status_code == 403

    _set_user(standard_user)
    run_id = client.post("/runs", json={"procedure_id": procedure_id, "user_id": "user-3"}).json()[
        "id"
    ]

    response = client.post(
        f"/runs/{run_id}/commit-step",
        json={
            "name": "Validation",
            "description": "Check slot validation",
            "steps": [
                {
                    "key": "step",
                    "title": "Step",
                    "prompt": "Provide email",
                    "slots": [{"name": "email", "type": "email", "required": True}],
                    "checklists": [],
                }
            "step_key": "profile",
            "slots": {},
            "checklist": [
                {"key": "consent", "completed": True},
            ],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "Slot validation failed"
    assert any(issue["reason"] == "missing_required_value" for issue in detail["issues"])


def test_commit_step_missing_required_checklist_returns_422(
    client, admin_user: User, standard_user: User
) -> None:
    _set_user(admin_user)
    procedure_id = _create_procedure(client, name="Checklist validation")

    _set_user(standard_user)
    run_id = client.post("/runs", json={"procedure_id": procedure_id, "user_id": "user-4"}).json()[
        "id"
    ]

    response = client.post(
        f"/runs/{run_id}/commit-step",
        json={"step_key": "step", "slots": {}, "checklist": []},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "Slot validation failed"
    assert any(issue["slot"] == "email" for issue in detail["issues"])
