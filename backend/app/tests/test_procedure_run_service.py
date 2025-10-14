from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app import models
from app.services.procedures import (
    ProcedureRunService,
    ProcedureRunState,
    InvalidProcedureRunTransition,
)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with TestingSession() as session:
        yield session
        session.rollback()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def procedure(db_session: Session) -> models.Procedure:
    proc = models.Procedure(name="Test", description="Testing procedure")
    proc.steps = [
        models.ProcedureStep(
            procedure=proc,
            key="step-1",
            title="Step 1",
            prompt="Do something",
            slots=[],
            position=1,
        ),
        models.ProcedureStep(
            procedure=proc,
            key="step-2",
            title="Step 2",
            prompt="Do something else",
            slots=[],
            position=2,
        ),
    ]
    db_session.add(proc)
    db_session.commit()
    db_session.refresh(proc)
    return proc


@pytest.fixture
def run(db_session: Session, procedure: models.Procedure) -> models.ProcedureRun:
    procedure_id = procedure.id
    run = models.ProcedureRun(
        procedure_id=procedure_id,
        user_id="user-1",
        state=ProcedureRunState.PENDING.value,
        created_at=datetime.utcnow(),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_valid_transition_persists_and_audits(db_session: Session, run: models.ProcedureRun) -> None:
    service = ProcedureRunService(db_session)

    service.transition_run(run, ProcedureRunState.IN_PROGRESS, actor="tester")

    db_session.refresh(run)
    assert run.state == ProcedureRunState.IN_PROGRESS.value

    audit_events = db_session.execute(
        select(models.AuditEvent).where(models.AuditEvent.action == "run.updated")
    ).scalars().all()
    assert len(audit_events) == 1
    assert audit_events[0].actor == "tester"


def test_invalid_transition_raises(db_session: Session, run: models.ProcedureRun) -> None:
    service = ProcedureRunService(db_session)
    run.state = ProcedureRunState.COMPLETED.value
    db_session.add(run)
    db_session.commit()

    with pytest.raises(InvalidProcedureRunTransition):
        service.transition_run(run, ProcedureRunState.IN_PROGRESS, actor="tester")


def test_commit_step_creates_state_and_audit_event(
    db_session: Session, run: models.ProcedureRun
) -> None:
    service = ProcedureRunService(db_session)

    service.commit_step(run, step_key="step-1", payload={"value": 1}, actor="tester")

    states = db_session.execute(select(models.ProcedureRunStepState)).scalars().all()
    assert len(states) == 1
    assert states[0].payload == {"value": 1}

    audit_events = db_session.execute(
        select(models.AuditEvent).where(models.AuditEvent.action == "run.step_committed")
    ).scalars().all()
    assert len(audit_events) == 1
    assert audit_events[0].actor == "tester"


def test_get_step_progress_counts_committed_steps(
    db_session: Session, run: models.ProcedureRun
) -> None:
    service = ProcedureRunService(db_session)
    service.commit_step(run, step_key="step-1", payload={"value": 1}, actor="tester")

    progress = service.get_step_progress(run)

    assert progress == {"total": 2, "completed": 1, "remaining": 1}
