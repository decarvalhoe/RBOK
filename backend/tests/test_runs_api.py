from __future__ import annotations

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
                "checklists": [
                    {
                        "key": "documents_verified",
                        "label": "Documents verified",
                        "required": True,
                    }
                ],
            },
        ],
    }
    create_response = client.post("/procedures", json=procedure_payload)
    assert create_response.status_code == 201
    procedure_id = create_response.json()["id"]

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
    assert len(run_payload["checklist_statuses"]) == 2
    assert run_payload["checklist_progress"] == {
        "total": 2,
        "completed": 0,
        "percentage": 0.0,
    }

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
    assert first_state["checklist_progress"] == {
        "total": 2,
        "completed": 1,
        "percentage": 50.0,
    }
    assert [status["completed"] for status in first_state["checklist_statuses"]] == [
        True,
        False,
    ]

    commit_second = client.post(
        f"/runs/{run_payload['id']}/commit-step",
        json={
            "step_key": "verification",
            "slots": {"document": "passport"},
            "checklist": [
                {"key": "documents_verified", "completed": True}
            ],
        },
    )
    assert commit_second.status_code == 200, commit_second.text
    assert commit_second.json()["state"] == "completed"
    assert commit_second.json()["checklist_progress"] == {
        "total": 2,
        "completed": 2,
        "percentage": 100.0,
    }

    final_state = client.get(f"/runs/{run_payload['id']}")
    assert final_state.status_code == 200
    payload = final_state.json()
    assert payload["state"] == "completed"
    assert payload["checklist_progress"] == {
        "total": 2,
        "completed": 2,
        "percentage": 100.0,
    }
    assert [status["completed"] for status in payload["checklist_statuses"]] == [
        True,
        True,
    ]


def test_commit_step_v2_exposes_pending_checklists(
    client, admin_user: User, standard_user: User
) -> None:
    _set_user(admin_user)
    response = client.post(
        "/procedures",
        json={
            "name": "Step commit v2",
            "description": "Verify pending checklist entries",
            "steps": [
                {
                    "key": "profile",
                    "title": "Profile",
                    "prompt": "Collect contact info",
                    "slots": [
                        {"name": "email", "type": "email", "required": True}
                    ],
                    "checklists": [
                        {"key": "consent", "label": "Consent", "required": True}
                    ],
                },
                {
                    "key": "verification",
                    "title": "Verification",
                    "prompt": "Upload ID",
                    "slots": [
                        {"name": "document", "type": "string", "required": True}
                    ],
                    "checklists": [
                        {
                            "key": "documents_verified",
                            "label": "Documents verified",
                            "required": True,
                        }
                    ],
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    procedure_id = response.json()["id"]

    _set_user(standard_user)
    run_id = client.post(
        "/runs", json={"procedure_id": procedure_id, "user_id": "user-commit-v2"}
    ).json()["id"]

    first_commit = client.post(
        f"/runs/{run_id}/steps/profile/commit",
        json={
            "slots": {"email": "user@example.com"},
            "checklist": [{"key": "consent", "completed": True}],
        },
    )
    assert first_commit.status_code == 200, first_commit.text
    payload = first_commit.json()
    assert payload["run_state"] == "in_progress"
    assert [status["key"] for status in payload["checklist_statuses"]] == [
        "consent",
        "documents_verified",
    ]
    assert [status["completed"] for status in payload["checklist_statuses"]] == [
        True,
        False,
    ]

    second_commit = client.post(
        f"/runs/{run_id}/steps/verification/commit",
        json={
            "slots": {"document": "passport"},
            "checklist": [
                {"key": "documents_verified", "completed": True}
            ],
        },
    )
    assert second_commit.status_code == 200, second_commit.text
    second_payload = second_commit.json()
    assert second_payload["run_state"] == "completed"
    assert [status["completed"] for status in second_payload["checklist_statuses"]] == [
        True,
        True,
    ]


def test_commit_step_missing_slot_returns_422(
    client, admin_user: User, standard_user: User, patch_opa
) -> None:
    _set_user(admin_user)
    procedure_payload = {
        "name": "Restricted",
        "description": "Blocked by policy",
        "steps": [
            {
                "key": "profile",
                "title": "Profile",
                "prompt": "Collect email",
                "slots": [
                    {
                        "name": "email",
                        "type": "email",
                        "required": True,
                        "label": "Email",
                    }
                ],
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

    patch_opa.denied_resources.discard(procedure_id)
    _set_user(standard_user)
    allowed = client.post("/runs", json={"procedure_id": procedure_id, "user_id": "user-3"})
    assert allowed.status_code == 201, allowed.text
    run_id = allowed.json()["id"]

    response = client.post(
        f"/runs/{run_id}/commit-step",
        json={
            "step_key": "profile",
            "slots": {},
            "checklist": [{"key": "consent", "completed": True}],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "Slot validation failed"
    assert any(issue.get("field") == "email" for issue in detail["issues"])


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
        json={
            "step_key": "profile",
            "slots": {"email": "user@example.com"},
            "checklist": [],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "Checklist validation failed"
    assert any(issue["field"] == "checklist.consent" for issue in detail["issues"])
