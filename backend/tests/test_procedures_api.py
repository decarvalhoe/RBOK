from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

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
                "checklists": [
                    {"key": "privacy_ack", "required": True},
                ],
            },
            {
                "key": "verify_document",
                "title": "Verify document",
                "prompt": "Upload your passport",
                "slots": [
                    {"name": "document", "type": "string", "required": True},
                ],
                "checklists": [],
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
    assert response.json()["detail"] == "Duplicate step key(s): step"


def test_duplicate_slot_names_return_error(client) -> None:
    payload = {
        "name": "Invalid procedure",
        "description": "Slots share a name",
        "steps": [
            {
                "key": "collect",
                "title": "Collect",
                "prompt": "Collect data",
                "slots": [
                    {"name": "email", "type": "string"},
                    {"name": "email", "type": "string"},
                ],
                "checklists": [],
            }
        ],
    }

    response = client.post("/procedures", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Duplicate slot name(s) in step 'collect': email"


def test_duplicate_checklist_keys_return_error(client) -> None:
    payload = {
        "name": "Invalid procedure",
        "description": "Checklist items share a key",
        "steps": [
            {
                "key": "verify",
                "title": "Verify",
                "prompt": "Verify data",
                "slots": [],
                "checklists": [
                    {"key": "ack", "label": "Acknowledge"},
                    {"key": "ack", "label": "Duplicate"},
                ],
            }
        ],
    }

    response = client.post("/procedures", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Duplicate checklist key(s) in step 'verify': ack"


def test_get_unknown_procedure_returns_404(client) -> None:
    response = client.get("/procedures/unknown")
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def _build_procedure_payload() -> Dict[str, Any]:
    return {
        'actor': 'demo-admin',
        'id': 'demo-procedure',
        'name': 'Demo procedure',
        'description': 'A complete lifecycle for testing',
        'steps': [
            {
                'key': 'introduction',
                'title': 'Introduction',
                'prompt': 'Say hello',
                'slots': [{'name': 'greeting', 'type': 'string'}],
            },
            {
                'key': 'summary',
                'title': 'Summary',
                'prompt': 'Wrap up the conversation',
                'slots': [],
            },
        ],
    }


def test_procedure_lifecycle_generates_audit_trail(client: TestClient) -> None:
    create_response = client.post('/procedures', json=_build_procedure_payload())
    assert create_response.status_code == 201
    created_procedure = create_response.json()
    assert created_procedure['id'] == 'demo-procedure'
    assert len(created_procedure['steps']) == 2

    list_response = client.get('/procedures')
    assert list_response.status_code == 200
    procedures = list_response.json()
    assert any(procedure['id'] == 'demo-procedure' for procedure in procedures)

    detail_response = client.get('/procedures/demo-procedure')
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload['steps'][0]['key'] == 'introduction'

    run_response = client.post('/runs', json={'actor': 'operator', 'procedure_id': 'demo-procedure'})
    assert run_response.status_code == 201
    run_payload = run_response.json()
    run_id = run_payload['id']
    assert run_payload['state'] == 'in_progress'

    first_commit = client.post(
        f'/runs/{run_id}/steps/introduction/commit',
        json={'actor': 'operator', 'payload': {'greeting': 'Bonjour'}},
    )
    assert first_commit.status_code == 200
    assert first_commit.json()['run']['state'] == 'in_progress'

    second_commit = client.post(
        f'/runs/{run_id}/steps/summary/commit',
        json={'actor': 'operator', 'payload': {'summary': 'All done'}},
    )
    assert second_commit.status_code == 200
    assert second_commit.json()['run']['state'] == 'completed'

    procedure_events = client.get(
        '/audit-events',
        params={'entity_type': 'procedure', 'entity_id': 'demo-procedure'},
    )
    assert procedure_events.status_code == 200
    actions = [event['action'] for event in procedure_events.json()]
    assert 'procedure.created' in actions

    run_events = client.get('/audit-events', params={'entity_type': 'procedure_run', 'entity_id': run_id})
    assert run_events.status_code == 200
    run_actions = [event['action'] for event in run_events.json()]
    assert 'run.created' in run_actions
    assert 'run.updated' in run_actions

    step_events = client.get(
        '/audit-events',
        params={'entity_type': 'procedure_run_step', 'entity_id': f'{run_id}:summary'},
    )
    assert step_events.status_code == 200
    step_actions = [event['action'] for event in step_events.json()]
    assert step_actions == ['run.step_committed']
