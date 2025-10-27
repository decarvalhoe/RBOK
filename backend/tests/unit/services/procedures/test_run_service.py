from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.procedure_runs import (
    ChecklistValidationError,
    InvalidTransitionError,
    ProcedureNotFoundError,
    ProcedureRunNotFoundError,
    ProcedureRunService,
    SlotValidationError,
)
from app.services.procedures.exceptions import (  # type: ignore[no-redef]
    ChecklistValidationError as ProcedureChecklistValidationError,
)
from app.services.procedures.exceptions import (
    InvalidTransitionError as ProcedureFSMInvalidTransitionError,
)
from app.services.procedures.exceptions import (
    SlotValidationError as ProcedureSlotValidationError,
)
from app.services.procedures.fsm import ProcedureRunState


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
            "field": "phone",
            "code": "validation.mask",
            "params": {"mask": "+41 XX XXX XX XX"},
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

    assert {issue["code"] for issue in exc.value.issues} == {"validation.duplicate"}
    assert {issue["field"] for issue in exc.value.issues} == {
        "checklist.safety_briefing"
    }


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


def test_commit_step_rejects_unknown_step(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    with pytest.raises(InvalidTransitionError):
        service.commit_step(
            run_id=run.id,
            step_key="missing",
            slots={},
            checklist=[],
        )


def test_start_run_requires_existing_procedure(service: ProcedureRunService) -> None:
    with pytest.raises(ProcedureNotFoundError):
        service.start_run(procedure_id="missing", user_id="user-1")


def test_commit_step_uses_next_pending_when_key_missing(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    snapshot = service.commit_step(
        run_id=run.id,
        step_key="",
        slots={"phone": "+41 21 555 77 88"},
        checklist=[{"key": "safety_briefing", "completed": True}],
    )

    assert "collect_contact" in snapshot.step_states


def test_validate_slots_reports_multiple_issues(
    service: ProcedureRunService, procedure: models.Procedure
) -> None:
    step = procedure.steps[0]

    with pytest.raises(SlotValidationError) as exc:
        service._validate_slots(
            step,
            {"unknown": "value", "phone": "+41-21-555-77-88", "badge": "A"},
        )

    details = {(issue["field"], issue["code"]) for issue in exc.value.issues}
    assert details == {
        ("phone", "validation.mask"),
        ("badge", "validation.type"),
        ("unknown", "validation.unexpected_slot"),
    }


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

    details = {(issue["field"], issue["code"]) for issue in exc.value.issues}
    assert details == {
        ("checklist.safety_briefing", "validation.duplicate"),
        ("checklist.unknown", "validation.unexpected_item"),
        ("checklist.safety_briefing", "validation.required"),
    }


def test_fail_run_transitions_state(
    test_session: Session,
    service: ProcedureRunService,
    run: models.ProcedureRun,
) -> None:
    service.commit_step(
        run_id=run.id,
        step_key="collect_contact",
        slots={"phone": "+41 21 555 77 88"},
        checklist=[{"key": "safety_briefing", "completed": True}],
    )

    snapshot = service.fail_run(run_id=run.id)

    test_session.refresh(run)
    assert snapshot.run.state == "failed"


def test_fail_run_rejects_completed_runs(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "completed"

    with pytest.raises(InvalidTransitionError):
        service.fail_run(run_id=run.id)


def test_ensure_run_active_rejects_terminal_states(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "failed"

    with pytest.raises(InvalidTransitionError):
        service._ensure_run_active(run)


def test_ensure_run_active_rejects_unknown_states(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "paused"

    with pytest.raises(InvalidTransitionError):
        service._ensure_run_active(run)


def test_transition_to_in_progress_rejects_unexpected_states(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "completed"

    with pytest.raises(InvalidTransitionError):
        service._transition_to_in_progress(run)


def test_transition_to_completed_rejects_failed_state(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "failed"

    with pytest.raises(InvalidTransitionError):
        service._transition_to_completed(run)


def test_transition_to_completed_returns_false_for_completed_state(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "completed"

    assert service._transition_to_completed(run) is False


def test_transition_to_completed_rejects_unknown_state(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "paused"

    with pytest.raises(InvalidTransitionError):
        service._transition_to_completed(run)


def test_transition_to_failed_rejects_completed_state(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "completed"

    with pytest.raises(InvalidTransitionError):
        service._transition_to_failed(run)


def test_transition_to_failed_returns_false_for_failed_state(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "failed"

    assert service._transition_to_failed(run) is False


def test_transition_to_failed_rejects_unknown_state(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    run.state = "paused"

    with pytest.raises(InvalidTransitionError):
        service._transition_to_failed(run)


def test_apply_transition_wraps_fsm_errors(
    monkeypatch: pytest.MonkeyPatch,
    service: ProcedureRunService,
    run: models.ProcedureRun,
) -> None:
    run.state = "pending"

    def raiser(*_args: object, **_kwargs: object) -> None:
        raise ProcedureFSMInvalidTransitionError("invalid")

    monkeypatch.setattr("app.services.procedure_runs.apply_transition", raiser)

    with pytest.raises(InvalidTransitionError):
        service._apply_transition(run, ProcedureRunState.IN_PROGRESS)


def test_load_run_raises_for_unknown_identifier(service: ProcedureRunService) -> None:
    with pytest.raises(ProcedureRunNotFoundError):
        service._load_run("missing")


def test_slot_definition_supports_model_instances(
    service: ProcedureRunService, procedure: models.Procedure
) -> None:
    slot = procedure.steps[0].slots[0]
    slot.configuration["validate"] = r"^\+41"
    definition = service._slot_definition(slot)

    assert definition == {
        "name": slot.name,
        "type": slot.slot_type,
        "required": slot.required,
        "metadata": slot.configuration,
        "mask": slot.configuration["mask"],
        "validate": slot.configuration["validate"],
    }


def test_slot_definition_supports_mapping_configuration(
    service: ProcedureRunService
) -> None:
    slot = {
        "name": "level",
        "type": "enum",
        "required": True,
        "options": ["low", "high"],
        "mask": "XX",
        "validate": r"^[A-Z]{2}$",
    }

    definition = service._slot_definition(slot)

    assert definition["metadata"]["options"] == ["low", "high"]
    assert definition["metadata"]["mask"] == "XX"
    assert definition["metadata"]["validate"] == r"^[A-Z]{2}$"


def test_validate_slots_wraps_errors_without_issues(
    monkeypatch: pytest.MonkeyPatch,
    service: ProcedureRunService,
    procedure: models.Procedure,
) -> None:
    step = procedure.steps[0]

    def raiser(*_args: object, **_kwargs: object) -> Dict[str, Any]:
        raise ProcedureSlotValidationError("bad")

    monkeypatch.setattr(
        "app.services.procedures.validators.SlotValidator.validate",
        lambda _self, _payload: raiser(),
    )

    with pytest.raises(SlotValidationError) as exc:
        service._validate_slots(step, {"phone": "+41"})

    assert exc.value.issues == [
        {
            "field": None,
            "code": "invalid",
            "params": {"message": "bad"},
        }
    ]


def test_next_pending_step_returns_none_when_complete(
    service: ProcedureRunService,
    run: models.ProcedureRun,
    procedure: models.Procedure,
) -> None:
    step = procedure.steps[0]
    run.step_states.append(
        models.ProcedureRunStepState(run_id=run.id, step_key=step.key, payload={})
    )
    next_step = procedure.steps[1]
    run.step_states.append(
        models.ProcedureRunStepState(run_id=run.id, step_key=next_step.key, payload={})
    )

    assert (
        service._next_pending_step(
            run,
            {
                step.key: run.step_states[0],
                next_step.key: run.step_states[1],
            },
        )
        is None
    )


def test_validate_checklist_wraps_errors_without_issues(
    monkeypatch: pytest.MonkeyPatch,
    service: ProcedureRunService,
    procedure: models.Procedure,
) -> None:
    step = procedure.steps[0]

    def raiser(*_args: object, **_kwargs: object) -> Dict[str, Any]:
        raise ProcedureChecklistValidationError("invalid")

    monkeypatch.setattr(
        "app.services.procedures.validators.ChecklistValidator.validate",
        lambda _self, _payload: raiser(),
    )

    with pytest.raises(ChecklistValidationError) as exc:
        service._validate_checklist(step, [])

    assert exc.value.issues == [
        {
            "field": "checklist",
            "code": "validation.invalid",
            "params": {"message": "invalid"},
        }
    ]


def test_checklist_definitions_include_descriptions(
    service: ProcedureRunService, procedure: models.Procedure
) -> None:
    procedure.steps[0].checklist_items[0].description = "Ensure briefing"

    definitions = service._checklist_definitions(procedure.steps[0])

    assert definitions[0]["metadata"]["description"] == "Ensure briefing"


def test_normalise_completed_at_parses_strings() -> None:
    assert ProcedureRunService._normalise_completed_at("2024-01-02T03:04:05") == datetime(2024, 1, 2, 3, 4, 5)
    assert ProcedureRunService._normalise_completed_at("invalid") is None
    now = datetime.utcnow()
    assert ProcedureRunService._normalise_completed_at(now) == now


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
