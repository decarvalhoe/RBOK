from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.procedure_runs import (
    ChecklistValidationError,
    InvalidTransitionError,
    ProcedureRunService,
    SlotValidationError,
)


@pytest.fixture()
def procedure(test_session: Session) -> models.Procedure:
    procedure = models.Procedure(name="Safety inspection", description="Ensure site is safe")
    first_step = models.ProcedureStep(
        key="collect_contact",
        title="Collect contact information",
        prompt="Record how to reach the site manager",
        position=0,
        slots=[
            models.ProcedureSlot(
                name="phone",
                slot_type="string",
                required=True,
                configuration={"mask": "+41 XX XXX XX XX"},
            ),
            models.ProcedureSlot(
                name="badge", slot_type="integer", required=False
            ),
        ],
        checklist_items=[
            models.ProcedureStepChecklistItem(
                key="safety_briefing",
                label="Safety briefing delivered",
                required=True,
            ),
            models.ProcedureStepChecklistItem(
                key="notes",
                label="Notes documented",
                required=False,
            ),
        ],
    )
    second_step = models.ProcedureStep(
        key="finalise",
        title="Finalise inspection",
        prompt="Confirm all tasks are complete",
        position=1,
        slots=[
            models.ProcedureSlot(
                name="summary",
                slot_type="string",
                required=True,
            )
        ],
        checklist_items=[
            models.ProcedureStepChecklistItem(
                key="sign_off",
                label="Supervisor sign-off",
                required=True,
            )
        ],
    )
    procedure.steps = [first_step, second_step]
    test_session.add(procedure)
    test_session.commit()
    test_session.refresh(procedure)
    return procedure


@pytest.fixture()
def run(test_session: Session, procedure: models.Procedure) -> models.ProcedureRun:
    run = models.ProcedureRun(procedure_id=procedure.id, user_id="tech-42")
    test_session.add(run)
    test_session.commit()
    test_session.refresh(run)
    return run


@pytest.fixture()
def service(test_session: Session) -> ProcedureRunService:
    return ProcedureRunService(test_session)


def test_commit_step_persists_state_and_values(
    test_session: Session, service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    snapshot = service.commit_step(
        run_id=run.id,
        step_key="collect_contact",
        slots={"phone": "+41 21 555 77 88", "badge": 57},
        checklist=[{"key": "safety_briefing", "completed": True}],
    )

    step_state = test_session.execute(
        select(models.ProcedureRunStepState).where(
            models.ProcedureRunStepState.run_id == run.id,
            models.ProcedureRunStepState.step_key == "collect_contact",
        )
    ).scalar_one()

    slot_value = test_session.execute(
        select(models.ProcedureRunSlotValue).where(
            models.ProcedureRunSlotValue.run_id == run.id,
            models.ProcedureRunSlotValue.slot.has(models.ProcedureSlot.name == "phone"),
        )
    ).scalar_one()

    assert snapshot.run.state == "in_progress"
    assert step_state.payload["slots"]["phone"] == "+41 21 555 77 88"
    assert slot_value.value == "+41 21 555 77 88"


def test_commit_step_enforces_mask(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    with pytest.raises(SlotValidationError) as exc:
        service.commit_step(
            run_id=run.id,
            step_key="collect_contact",
            slots={"phone": "+41-21-555-77-88"},
            checklist=[{"key": "safety_briefing", "completed": True}],
        )

    assert exc.value.issues == [
        {
            "slot": "phone",
            "reason": "mask_mismatch",
            "mask": "+41 XX XXX XX XX",
        }
    ]


def test_commit_step_rejects_duplicate_checklist_entries(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    with pytest.raises(ChecklistValidationError) as exc:
        service.commit_step(
            run_id=run.id,
            step_key="collect_contact",
            slots={"phone": "+41 21 555 77 88"},
            checklist=[
                {"key": "safety_briefing", "completed": True},
                {"key": "safety_briefing", "completed": True},
            ],
        )

    assert {issue["reason"] for issue in exc.value.issues} == {"duplicate_key"}


def test_commit_step_requires_previous_steps(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        service.commit_step(
            run_id=run.id,
            step_key="finalise",
            slots={"summary": "All clear"},
            checklist=[{"key": "sign_off", "completed": True}],
        )

    assert "must be committed" in str(exc.value)


def test_commit_step_prevents_duplicate_commits(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    service.commit_step(
        run_id=run.id,
        step_key="collect_contact",
        slots={"phone": "+41 21 555 77 88"},
        checklist=[{"key": "safety_briefing", "completed": True}],
    )

    with pytest.raises(InvalidTransitionError) as exc:
        service.commit_step(
            run_id=run.id,
            step_key="collect_contact",
            slots={"phone": "+41 21 555 77 88"},
            checklist=[{"key": "safety_briefing", "completed": True}],
        )

    assert "already committed" in str(exc.value)


def test_commit_step_completes_run_when_all_steps_committed(
    test_session: Session, service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    service.commit_step(
        run_id=run.id,
        step_key="collect_contact",
        slots={"phone": "+41 21 555 77 88"},
        checklist=[{"key": "safety_briefing", "completed": True}],
    )

    snapshot = service.commit_step(
        run_id=run.id,
        step_key="finalise",
        slots={"summary": "Inspection passed"},
        checklist=[{"key": "sign_off", "completed": True}],
    )

    assert snapshot.run.state == "completed"
    assert isinstance(snapshot.run.closed_at, datetime)


def test_validate_slots_reports_multiple_issues(
    service: ProcedureRunService, procedure: models.Procedure
) -> None:
    step = procedure.steps[0]

    with pytest.raises(SlotValidationError) as exc:
        service._validate_slots(
            step,
            {"unknown": "value", "phone": "+41-21-555-77-88", "badge": "A"},
        )

    reasons = {(issue["slot"], issue["reason"]) for issue in exc.value.issues}
    assert (
        ("phone", "mask_mismatch") in reasons
        and ("unknown", "unknown_slot") in reasons
        and ("badge", "invalid_type") in reasons
    )


def test_validate_checklist_detects_duplicates_and_missing(
    service: ProcedureRunService, procedure: models.Procedure
) -> None:
    step = procedure.steps[0]

    with pytest.raises(ChecklistValidationError) as exc:
        service._validate_checklist(
            step,
            [
                {"key": "safety_briefing", "completed": False},
                {"key": "safety_briefing", "completed": True},
                {"key": "unknown", "completed": True},
            ],
        )

    reasons = {issue["reason"] for issue in exc.value.issues}
    assert {"duplicate_key", "required_not_completed", "unknown_checklist_item"}.issubset(
        reasons
    )


def test_validate_checklist_accepts_valid_submission(
    service: ProcedureRunService, procedure: models.Procedure
) -> None:
    step = procedure.steps[0]

    service._validate_checklist(
        step,
        [
            {"key": "safety_briefing", "completed": True},
            {"key": "notes", "completed": False},
        ],
    )
