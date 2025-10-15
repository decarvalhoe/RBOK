from __future__ import annotations

from datetime import datetime
from typing import Dict, Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.procedure_runs import InvalidTransitionError, ProcedureRunService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_procedure(session: Session) -> models.Procedure:
    procedure = models.Procedure(name="Test", description="Test procedure")
    first_step = models.ProcedureStep(
        procedure=procedure,
        key="step-1",
        title="First",
        prompt="Do the first thing",
        position=0,
    )
    second_step = models.ProcedureStep(
        procedure=procedure,
        key="step-2",
        title="Second",
        prompt="Do the second thing",
        position=1,
    )
    session.add_all([procedure, first_step, second_step])
    session.commit()
    session.refresh(procedure)
    return procedure


def _list_run_updates(session: Session) -> list[models.AuditEvent]:
    return (
        session.execute(
            select(models.AuditEvent)
            .where(models.AuditEvent.action == "run.updated")
            .order_by(models.AuditEvent.occurred_at)
        )
        .scalars()
        .all()
    )


def _commit_step(
    service: ProcedureRunService,
    *,
    run_id: str,
    step_key: str,
    actor: str,
) -> None:
    service.commit_step(
        run_id=run_id,
        step_key=step_key,
        slots={},
        checklist=[],
        actor=actor,
    )


def test_commit_step_records_audit_trail_until_completion(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ProcedureRunService(db_session)
    procedure = _create_procedure(db_session)
    run = service.start_run(procedure_id=procedure.id, user_id="tech-1", actor="initiator")

    _commit_step(service, run_id=run.id, step_key="step-1", actor="initiator")

    db_session.refresh(run)
    assert run.state == "in_progress"
    assert run.closed_at is None

    run_updates = _list_run_updates(db_session)
    assert len(run_updates) == 1
    first_diff: Dict[str, Dict[str, object]] = run_updates[0].payload_diff["changed"]
    assert first_diff["state"] == {"from": "pending", "to": "in_progress"}
    assert "closed_at" not in first_diff

    completion_time = datetime(2024, 5, 1, 9, 30, 0)
    monkeypatch.setattr(service, "_now", lambda: completion_time)

    _commit_step(service, run_id=run.id, step_key="step-2", actor="initiator")

    db_session.refresh(run)
    assert run.state == "completed"
    assert run.closed_at == completion_time

    run_updates = _list_run_updates(db_session)
    assert len(run_updates) == 2
    second_diff: Dict[str, Dict[str, object]] = run_updates[-1].payload_diff["changed"]
    assert second_diff["state"] == {"from": "in_progress", "to": "completed"}
    assert second_diff["closed_at"]["from"] is None
    assert second_diff["closed_at"]["to"] == completion_time.isoformat()


def test_fail_run_updates_state_and_closed_at(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ProcedureRunService(db_session)
    procedure = _create_procedure(db_session)
    run = service.start_run(procedure_id=procedure.id, user_id="tech-1", actor="initiator")

    _commit_step(service, run_id=run.id, step_key="step-1", actor="initiator")

    failure_time = datetime(2024, 6, 10, 8, 15, 0)
    monkeypatch.setattr(service, "_now", lambda: failure_time)

    snapshot = service.fail_run(run_id=run.id, actor="initiator")

    assert snapshot.run.state == "failed"
    assert snapshot.run.closed_at == failure_time

    run_updates = _list_run_updates(db_session)
    assert len(run_updates) == 2
    last_diff: Dict[str, Dict[str, object]] = run_updates[-1].payload_diff["changed"]
    assert last_diff["state"] == {"from": "in_progress", "to": "failed"}
    assert last_diff["closed_at"]["from"] is None
    assert last_diff["closed_at"]["to"] == failure_time.isoformat()


def test_fail_run_rejects_completed_run(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ProcedureRunService(db_session)
    procedure = _create_procedure(db_session)
    run = service.start_run(procedure_id=procedure.id, user_id="tech-1", actor="initiator")

    _commit_step(service, run_id=run.id, step_key="step-1", actor="initiator")
    monkeypatch.setattr(service, "_now", lambda: datetime(2024, 7, 1, 12, 0, 0))
    _commit_step(service, run_id=run.id, step_key="step-2", actor="initiator")

    with pytest.raises(InvalidTransitionError) as exc:
        service.fail_run(run_id=run.id, actor="initiator")

    assert str(exc.value) == "Run already terminal with state 'completed'"


def test_commit_step_rejects_after_failure(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ProcedureRunService(db_session)
    procedure = _create_procedure(db_session)
    run = service.start_run(procedure_id=procedure.id, user_id="tech-1", actor="initiator")

    _commit_step(service, run_id=run.id, step_key="step-1", actor="initiator")
    monkeypatch.setattr(service, "_now", lambda: datetime(2024, 7, 2, 15, 0, 0))
    service.fail_run(run_id=run.id, actor="initiator")

    with pytest.raises(InvalidTransitionError) as exc:
        _commit_step(service, run_id=run.id, step_key="step-2", actor="initiator")

    assert str(exc.value) == "Run already terminal with state 'failed'"
