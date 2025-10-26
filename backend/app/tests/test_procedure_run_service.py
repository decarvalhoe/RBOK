from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.database import Base
from app.services.procedure_runs import InvalidTransitionError, ProcedureRunService
from app.services.procedures.fsm import ProcedureRunState


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with TestingSession() as session:
        yield session
        session.rollback()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def procedure(db_session: Session) -> models.Procedure:
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
            )
        ],
        checklist_items=[
            models.ProcedureStepChecklistItem(
                key="safety_briefing",
                label="Safety briefing delivered",
                required=True,
            ),
        ],
    )
    final_step = models.ProcedureStep(
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
    procedure.steps = [first_step, final_step]
    db_session.add(procedure)
    db_session.commit()
    db_session.refresh(procedure)
    return procedure


@pytest.fixture()
def service(db_session: Session) -> ProcedureRunService:
    return ProcedureRunService(db_session)


@pytest.fixture()
def run(service: ProcedureRunService, procedure: models.Procedure) -> models.ProcedureRun:
    return service.start_run(procedure_id=procedure.id, user_id="tech-42")


def test_start_run_through_public_api(service: ProcedureRunService, procedure: models.Procedure) -> None:
    run = service.start_run(procedure_id=procedure.id, user_id="operator")

    assert run.state == ProcedureRunState.PENDING.value
    assert run.procedure_id == procedure.id


def test_commit_step_via_public_api(
    db_session: Session, service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    snapshot = service.commit_step(
        run_id=run.id,
        step_key="collect_contact",
        slots={"phone": "+41 21 555 77 88"},
        checklist=[{"key": "safety_briefing", "completed": True}],
        actor="tech-42",
    )

    step_state = db_session.execute(
        select(models.ProcedureRunStepState).where(
            models.ProcedureRunStepState.run_id == run.id,
            models.ProcedureRunStepState.step_key == "collect_contact",
        )
    ).scalar_one()

    assert snapshot.run.state == ProcedureRunState.IN_PROGRESS.value
    assert step_state.payload["slots"]["phone"] == "+41 21 555 77 88"


def test_commit_step_via_public_api_protects_against_duplicates(
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

    assert exc.value.run_id == run.id


def test_fail_run_marks_snapshot_failed(
    service: ProcedureRunService, run: models.ProcedureRun
) -> None:
    snapshot = service.fail_run(run_id=run.id, actor="operator")

    assert snapshot.run.state == ProcedureRunState.FAILED.value
    assert isinstance(snapshot.run.closed_at, datetime)
