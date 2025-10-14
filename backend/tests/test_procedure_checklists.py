from __future__ import annotations

from typing import List

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
        slots=[{"name": "field"}],
        position=1,
    )
    items = [
        ProcedureStepChecklistItem(step=step, key="item-a", label="Item A", position=1),
        ProcedureStepChecklistItem(step=step, key="item-b", label="Item B", position=2),
    ]
    run = ProcedureRun(procedure=procedure, user_id="user-1", state="pending")
    test_session.add(procedure)
    test_session.add(run)
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
            "payload": {"field": "value"},
            "checklist": {"completed_item_ids": [items[0].id]},
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "checklist_incomplete"
    assert items[1].id in detail["missing_item_ids"]

    response = client.post(
        f"/runs/{run.id}/commit-step",
        json={
            "step_key": step.key,
            "payload": {"field": "value"},
            "checklist": {"completed_item_ids": [item.id for item in items]},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "completed"
    checklist = {item["id"]: item for item in body["checklist_statuses"]}
    assert all(entry["completed"] for entry in checklist.values())
    assert body["checklist_progress"] == {"total": 2, "completed": 2, "percentage": 100.0}

    run_response = client.get(f"/runs/{run.id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["state"] == "completed"
    assert all(item["completed"] for item in run_payload["checklist_statuses"])
    assert run_payload["checklist_progress"]["percentage"] == 100.0
