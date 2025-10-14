from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app import models
from app.services.procedures.exceptions import (
    ChecklistValidationError,
    InvalidTransitionError,
    SlotValidationError,
    StepOrderError,
)
from app.services.procedures.fsm import RUN_COMPLETED, RUN_IN_PROGRESS, ProcedureFSM


@pytest.fixture()
def procedure(test_session: Session) -> models.Procedure:
    procedure = models.Procedure(
        name="Onboarding",
        description="User onboarding workflow",
    )
    procedure.steps = [
        models.ProcedureStep(
            key="collect_profile",
            title="Collect profile",
            prompt="Request the basic profile information",
            position=0,
            slots=[
                models.ProcedureSlot(
                    name="email",
                    slot_type="email",
                    required=True,
                ),
                models.ProcedureSlot(
                    name="phone",
                    slot_type="phone",
                    required=True,
                    configuration={"mask": "+41 XX XXX XX XX"},
                ),
            ],
            checklist_items=[
                models.ProcedureStepChecklistItem(
                    key="consent",
                    label="Consent given",
                    required=True,
                )
            ],
        ),
        models.ProcedureStep(
            key="verify_identity",
            title="Verify identity",
            prompt="Validate the submitted identity document",
            position=1,
            slots=[
                models.ProcedureSlot(
                    name="document",
                    slot_type="string",
                    required=True,
                )
            ],
            checklist_items=[
                models.ProcedureStepChecklistItem(
                    key="signature",
                    label="Signature verified",
                    required=False,
                )
            ],
        ),
    ]
    test_session.add(procedure)
    test_session.commit()
    test_session.refresh(procedure)
    return procedure


@pytest.fixture()
def run(test_session: Session, procedure: models.Procedure) -> models.ProcedureRun:
    run = models.ProcedureRun(procedure_id=procedure.id, user_id="user-123")
    test_session.add(run)
    test_session.commit()
    test_session.refresh(run)
    return run


def test_start_transition_updates_state(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)

    updated = fsm.start(run)

    assert updated.state == RUN_IN_PROGRESS
    assert updated.closed_at is None


def test_start_rejects_non_pending_runs(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)
    fsm.start(run)

    with pytest.raises(InvalidTransitionError):
        fsm.start(run)


def test_commit_steps_progresses_and_completes(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)

    first_state = fsm.commit_step(
        run,
        "collect_profile",
        slots={"email": "user@example.com", "phone": "+41 21 555 77 88"},
        checklist=[{"name": "consent", "completed": True}],
    )
    test_session.commit()
    test_session.refresh(run)

    assert run.state == RUN_IN_PROGRESS
    assert first_state.payload["slots"]["phone"] == "+41 21 555 77 88"

    second_state = fsm.commit_step(
        run,
        "verify_identity",
        slots={"document": "passport"},
        checklist=[{"name": "signature", "completed": False}],
    )
    test_session.commit()
    test_session.refresh(run)

    assert run.state == RUN_COMPLETED
    assert isinstance(run.closed_at, datetime)
    assert second_state.payload["slots"]["document"] == "passport"


def test_commit_step_requires_required_slots(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)

    with pytest.raises(SlotValidationError) as exc:
        fsm.commit_step(
            run,
            "collect_profile",
            slots={"email": "user@example.com"},
            checklist=[{"name": "consent", "completed": True}],
        )

    assert "Slot 'phone' is required" in str(exc.value)


def test_commit_step_enforces_step_order(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)

    with pytest.raises(StepOrderError):
        fsm.commit_step(
            run,
            "verify_identity",
            slots={"document": "passport"},
            checklist=[{"name": "signature", "completed": True}],
        )


def test_commit_step_validates_checklists(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)

    with pytest.raises(ChecklistValidationError) as exc:
        fsm.commit_step(
            run,
            "collect_profile",
            slots={"email": "user@example.com", "phone": "+41 21 555 77 88"},
            checklist=[{"name": "consent", "completed": False}],
        )

    assert "Checklist item 'consent' must be completed" in str(exc.value)


def test_commit_step_rejects_unknown_slots(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)

    with pytest.raises(SlotValidationError) as exc:
        fsm.commit_step(
            run,
            "collect_profile",
            slots={
                "email": "user@example.com",
                "phone": "+41 21 555 77 88",
                "unknown": "value",
            },
            checklist=[{"name": "consent", "completed": True}],
        )

    assert "Unknown slots provided" in str(exc.value)


def test_commit_step_rejects_mask_violations(test_session: Session, run: models.ProcedureRun) -> None:
    fsm = ProcedureFSM(test_session)

    with pytest.raises(SlotValidationError) as exc:
        fsm.commit_step(
            run,
            "collect_profile",
            slots={"email": "user@example.com", "phone": "+41-21-555-77-88"},
            checklist=[{"name": "consent", "completed": True}],
        )

    assert "must follow mask" in str(exc.value)
