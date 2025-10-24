from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.auth import User, get_current_user, get_current_user_optional
from app.main import app
from fastapi.testclient import TestClient


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


def _build_procedure_payload(
    *,
    procedure_id: str = "demo-procedure",
    name: str = "Identity verification",
    description: str = "Two-step KYC flow",
    actor: str | None = None,
    steps: list[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": procedure_id,
        "name": name,
        "description": description,
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
                    {"key": "privacy_ack", "label": "Privacy acknowledgement", "required": True},
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

    if actor is not None:
        payload["actor"] = actor

    if steps is not None:
        payload["steps"] = steps

    return payload


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
    assert detail["steps"][1]["key"] == "verify_document"


def test_slot_constraints_survive_round_trip(client: TestClient) -> None:
    procedure_id = "constraints-procedure"
    payload = _build_procedure_payload(
        procedure_id=procedure_id,
        steps=[
            {
                "key": "collect_constraints",
                "title": "Collect constrained data",
                "prompt": "Provide values that satisfy each constraint",
                "slots": [
                    {
                        "name": "language",
                        "type": "enum",
                        "label": "Language",
                        "required": True,
                        "options": ["fr", "en"],
                        "metadata": {"ui": {"component": "select"}},
                    },
                    {
                        "name": "code",
                        "type": "string",
                        "label": "Country code",
                        "required": True,
                        "validate": r"^[A-Z]{2}$",
                        "metadata": {"hint": "Two capital letters"},
                    },
                    {
                        "name": "phone",
                        "type": "phone",
                        "label": "Phone",
                        "required": True,
                        "mask": "+41 XX XXX XX XX",
                    },
                ],
                "checklists": [],
            }
        ],
    )

    response = client.post("/procedures", json=payload)
    assert response.status_code == 201, response.text
    created = response.json()

    slots = {slot["name"]: slot for slot in created["steps"][0]["slots"]}
    assert slots["language"]["options"] == ["fr", "en"]
    assert slots["language"]["metadata"]["options"] == ["fr", "en"]
    assert slots["language"]["metadata"]["ui"] == {"component": "select"}

    assert slots["code"]["validate"] == r"^[A-Z]{2}$"
    assert slots["code"]["metadata"]["validate"] == r"^[A-Z]{2}$"
    assert slots["code"]["metadata"]["hint"] == "Two capital letters"

    assert slots["phone"]["mask"] == "+41 XX XXX XX XX"
    assert slots["phone"]["metadata"]["mask"] == "+41 XX XXX XX XX"

    detail_response = client.get(f"/procedures/{created['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    detail_slots = {slot["name"]: slot for slot in detail["steps"][0]["slots"]}
    assert detail_slots["language"]["options"] == ["fr", "en"]
    assert detail_slots["code"]["validate"] == r"^[A-Z]{2}$"
    assert detail_slots["phone"]["mask"] == "+41 XX XXX XX XX"

    run_response = client.post(
        "/runs",
        json={"procedure_id": created["id"], "user_id": "operator"},
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()

    commit_response = client.post(
        f"/runs/{run['id']}/commit-step",
        json={
            "step_key": "collect_constraints",
            "slots": {
                "language": "es",
                "code": "A1",
                "phone": "+41-12-345-6789",
            },
            "checklist": [],
        },
    )
    assert commit_response.status_code == 422, commit_response.text
    detail = commit_response.json()["detail"]
    issues = {issue["field"]: issue for issue in detail["issues"]}

    assert issues["language"]["code"] == "validation.enum"
    assert issues["language"]["params"]["allowed"] == ["fr", "en"]

    assert issues["code"]["code"] == "validation.pattern"
    assert issues["code"]["params"]["pattern"] == r"^[A-Z]{2}$"

    assert issues["phone"]["code"] == "validation.mask"
    assert issues["phone"]["params"]["mask"] == "+41 XX XXX XX XX"


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
                "checklists": [],
            },
            {
                "key": "step",
                "title": "Two",
                "prompt": "Do B",
                "slots": [],
                "checklists": [],
            },
        ],
    }

    response = client.post("/procedures", json=payload)
    assert response.status_code == 400

    detail = response.json()["detail"]
    assert detail["message"] == "Duplicate keys detected in procedure definition."
    assert any(issue["field"] == "steps[1].key" for issue in detail["issues"])


def test_duplicate_slots_and_checklists_return_error(client) -> None:
    payload = {
        "name": "Invalid procedure",
        "description": "Slots or checklist keys duplicated",
        "steps": [
            {
                "key": "collect",
                "title": "Collect data",
                "prompt": "Gather details",
                "slots": [
                    {"name": "serial", "type": "string"},
                    {"name": "serial", "type": "string"},
                ],
                "checklists": [
                    {"key": "ppe", "label": "PPE ready"},
                    {"key": "ppe", "label": "PPE confirmed"},
                ],
            }
        ],
    }

    response = client.post("/procedures", json=payload)
    assert response.status_code == 400

    detail = response.json()["detail"]
    fields = {issue["field"] for issue in detail["issues"]}
    assert any(field.startswith("steps[0].slots") for field in fields)
    assert any(field.startswith("steps[0].checklists") for field in fields)


def test_get_unknown_procedure_returns_404(client) -> None:
    response = client.get("/procedures/unknown")
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def _build_audit_procedure_payload() -> Dict[str, Any]:
    return _build_procedure_payload(
        actor='demo-admin',
        name='Demo procedure',
        description='A complete lifecycle for testing',
        steps=[
            {
                'key': 'introduction',
                'title': 'Introduction',
                'prompt': 'Say hello',
                'slots': [{'name': 'greeting', 'type': 'string'}],
                'checklists': [],
            },
            {
                'key': 'summary',
                'title': 'Summary',
                'prompt': 'Wrap up the conversation',
                'slots': [{'name': 'summary', 'type': 'string'}],
                'checklists': [],
            },
        ],
    )


def test_procedure_lifecycle_generates_audit_trail(
    client: TestClient, test_session
) -> None:
    create_response = client.post("/procedures", json=_build_audit_procedure_payload())
    assert create_response.status_code == 201

    procedure_id = create_response.json()["id"]

    run_response = client.post('/runs', json={'procedure_id': 'demo-procedure', 'user_id': 'operator'})
    assert run_response.status_code == 201
    run_payload = run_response.json()
    run_id = run_payload['id']
    assert run_payload['state'] == 'pending'

    first_commit = client.post(
        f'/runs/{run_id}/commit-step',
        json={'step_key': 'introduction', 'slots': {'greeting': 'Bonjour'}, 'checklist': []},
    )
    assert first_commit.status_code == 200
    assert first_commit.json()['state'] == 'in_progress'

    second_commit = client.post(
        f'/runs/{run_id}/commit-step',
        json={'step_key': 'summary', 'slots': {'summary': 'All done'}, 'checklist': []},
    )
    assert second_commit.status_code == 200
    assert second_commit.json()['state'] == 'completed'

    procedure_events = test_session.execute(
        select(models.AuditEvent).where(
            models.AuditEvent.entity_type == 'procedure',
            models.AuditEvent.entity_id == procedure_id,
        )
    ).scalars().all()
    procedure_actions = {event.action for event in procedure_events}
    assert 'procedure.created' in procedure_actions

    run_events = test_session.execute(
        select(models.AuditEvent).where(
            models.AuditEvent.entity_type == 'procedure_run',
            models.AuditEvent.entity_id == run_id,
        )
    ).scalars().all()
    run_actions = {event.action for event in run_events}
    assert {'run.created', 'run.updated'} <= run_actions

    step_events = test_session.execute(
        select(models.AuditEvent).where(
            models.AuditEvent.entity_type == 'procedure_run_step',
            models.AuditEvent.entity_id == f'{run_id}:summary',
        )
    ).scalars().all()
    assert [event.action for event in step_events] == ['run.step_committed']
