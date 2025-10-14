from __future__ import annotations

from typing import List

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.models import (
    Procedure,
    ProcedureRun,
    ProcedureStep,
    ProcedureStepChecklistItem,
)


def _seed_procedure(test_session: Session) -> tuple[Procedure, ProcedureRun, ProcedureStep, List[ProcedureStepChecklistItem]]:
    procedure = Procedure(name="Demo", description="Demo procedure")
    step = ProcedureStep(
        procedure=procedure,
        key="step-one",
        title="Step One",
        prompt="Do the thing",
        position=1,
    )
    slot = models.ProcedureSlot(
        name="field",
        slot_type="string",
        required=True,
        position=0,
    )
    items = [
        ProcedureStepChecklistItem(step=step, key="item-a", label="Item A", position=1),
        ProcedureStepChecklistItem(step=step, key="item-b", label="Item B", position=2),
    ]
    step.slots.append(slot)
    run = ProcedureRun(procedure=procedure, user_id="user-1", state="pending")
    test_session.add_all([procedure, step, slot, *items, run])
    test_session.commit()
    return procedure, run, step, items


def test_list_procedures_includes_checklist_items(
    client: TestClient, test_session: Session
) -> None:
    _seed_procedure(test_session)

    response = client.get("/procedures")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    first_step = payload[0]["steps"][0]
    labels = [item["label"] for item in first_step["checklist_items"]]
    assert labels == ["Item A", "Item B"]


def test_commit_step_validates_and_updates_checklist(
    client: TestClient, test_session: Session
) -> None:
    _, run, step, items = _seed_procedure(test_session)

    response = client.post(
        f"/runs/{run.id}/commit-step",
        json={
            "step_key": step.key,
            "slots": {"field": "value"},
            "checklist": [
                {"key": items[0].key, "completed": True},
            ],
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "Checklist validation failed"
    assert any(issue.get("key") == items[1].key for issue in detail["issues"])

    response = client.post(
        f"/runs/{run.id}/commit-step",
        json={
            "step_key": step.key,
            "slots": {"field": "value"},
            "checklist": [
                {"key": item.key, "completed": True}
                for item in items
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "completed"
    checklist = {item["key"]: item for item in body["checklist_states"]}
    assert all(entry["completed"] for entry in checklist.values())
    assert body["checklist_progress"] == {"total": 2, "completed": 2, "percentage": 100.0}

    run_response = client.get(f"/runs/{run.id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["state"] == "completed"
    assert all(item["completed"] for item in run_payload["checklist_states"])
