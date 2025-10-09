from typing import List

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    data = response.json()
    return data["access_token"]


def test_audit_events_recorded(client: TestClient, test_session: Session) -> None:
    procedure_payload = {
        "name": "Audited Procedure",
        "description": "Check audit trail",
        "steps": [
            {"key": "intro", "title": "Intro", "prompt": "Start", "slots": []},
        ],
    }
    create_response = client.post("/procedures", json=procedure_payload)
    create_response.raise_for_status()
    procedure_id = create_response.json()["id"]

    updated_payload = {
        **procedure_payload,
        "description": "Updated description",
        "steps": [
            {"key": "intro", "title": "Intro", "prompt": "Start", "slots": []},
            {"key": "end", "title": "End", "prompt": "Finish", "slots": []},
        ],
    }
    update_response = client.put(f"/procedures/{procedure_id}", json=updated_payload)
    update_response.raise_for_status()

    run_response = client.post(
        "/runs",
        json={"procedure_id": procedure_id, "user_id": "bob"},
    )
    run_response.raise_for_status()
    run_id = run_response.json()["id"]

    run_update = client.patch(f"/runs/{run_id}", json={"state": "in_progress"})
    run_update.raise_for_status()

    commit_response = client.post(
        f"/runs/{run_id}/steps/intro/commit",
        json={"payload": {"answer": "ok"}},
    )
    commit_response.raise_for_status()

    actions: List[str] = [
        event.action
        for event in test_session.query(models.AuditEvent).order_by(models.AuditEvent.occurred_at).all()
    ]
    assert "procedure.created" in actions
    assert "procedure.updated" in actions
    assert "run.created" in actions
    assert "run.updated" in actions
    assert "run.step_committed" in actions


def test_audit_events_endpoint_requires_auditor(client: TestClient) -> None:
    response = client.get("/audit-events")
    assert response.status_code == 401


def test_audit_events_endpoint_filters(client: TestClient, test_session: Session) -> None:
    # Seed at least one audit event
    procedure_response = client.post(
        "/procedures",
        json={
            "name": "Filter Procedure",
            "description": "Created for filtering",
            "steps": [],
        },
    )
    procedure_response.raise_for_status()

    token = _login(client, "audra", "auditpass")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/audit-events", headers=headers, params={"action": "procedure.created"})
    response.raise_for_status()
    events = response.json()
    assert all(event["action"] == "procedure.created" for event in events)

    if events:
        entity_id = events[0]["entity_id"]
        filtered = client.get(
            "/audit-events",
            headers=headers,
            params={"entity_id": entity_id, "entity_type": "procedure"},
        )
        filtered.raise_for_status()
        filtered_events = filtered.json()
        assert all(event["entity_id"] == entity_id for event in filtered_events)
