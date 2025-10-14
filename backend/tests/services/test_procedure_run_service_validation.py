from __future__ import annotations

import pytest

from app import models
from app.services.procedure_runs import ProcedureRunService, SlotValidationError


def _create_service_with_slot(
    session,
    *,
    slot: models.ProcedureSlot,
) -> tuple[ProcedureRunService, models.ProcedureRun]:
    procedure = models.Procedure(name="Proc", description="Validation procedure")
    step = models.ProcedureStep(
        procedure=procedure,
        key="collect",
        title="Collect",
        prompt="Collect data",
        slots=[slot],
        position=0,
    )
    run = models.ProcedureRun(procedure=procedure, user_id="user-1")
    session.add_all([procedure, step, run])
    session.commit()
    session.refresh(run)
    return ProcedureRunService(session), run


def test_commit_step_reports_mask_error(test_session) -> None:
    slot = models.ProcedureSlot(
        name="phone",
        slot_type="phone",
        required=True,
        configuration={"mask": "+41 XX XXX XX XX"},
    )
    service, run = _create_service_with_slot(test_session, slot=slot)

    with pytest.raises(SlotValidationError) as exc:
        service.commit_step(
            run_id=run.id,
            step_key="collect",
            slots={"phone": "+41-12-345-6789"},
            checklist=[],
            actor="tester",
        )

    assert exc.value.issues == [
        {"field": "phone", "code": "validation.mask", "params": {"mask": "+41 XX XXX XX XX"}}
    ]


def test_commit_step_reports_pattern_error(test_session) -> None:
    slot = models.ProcedureSlot(
        name="code",
        slot_type="string",
        required=True,
        configuration={"validate": r"^[A-Z]{2}$"},
    )
    service, run = _create_service_with_slot(test_session, slot=slot)

    with pytest.raises(SlotValidationError) as exc:
        service.commit_step(
            run_id=run.id,
            step_key="collect",
            slots={"code": "A1"},
            checklist=[],
            actor="tester",
        )

    assert exc.value.issues == [
        {"field": "code", "code": "validation.pattern", "params": {"pattern": r"^[A-Z]{2}$"}}
    ]


def test_commit_step_reports_options_error(test_session) -> None:
    slot = models.ProcedureSlot(
        name="language",
        slot_type="enum",
        required=True,
        configuration={"options": ["fr", "en"]},
    )
    service, run = _create_service_with_slot(test_session, slot=slot)

    with pytest.raises(SlotValidationError) as exc:
        service.commit_step(
            run_id=run.id,
            step_key="collect",
            slots={"language": "es"},
            checklist=[],
            actor="tester",
        )

    assert exc.value.issues == [
        {
            "field": "language",
            "code": "validation.enum",
            "params": {"allowed": ["fr", "en"]},
        }
    ]
