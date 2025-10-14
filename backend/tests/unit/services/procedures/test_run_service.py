from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.database import Base
from app.services.procedures.run import ProcedureRunService


def _build_session() -> tuple[Session, Any]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
    session = SessionLocal()
    return session, engine


def _teardown_session(session: Session, engine: Any) -> None:
    try:
        session.close()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_commit_step_persists_valid_payload() -> None:
    session, engine = _build_session()
    try:
        procedure = models.Procedure(name="Proc", description="Test procedure")
        step = models.ProcedureStep(
            procedure=procedure,
            key="intro",
            title="Intro",
            prompt="Fill in details",
            slots=[
                {"name": "email", "type": "email", "required": True},
                {"name": "age", "type": "number", "required": False},
            ],
            position=0,
        )
        run = models.ProcedureRun(procedure=procedure, user_id="user-1", state="in_progress")

        session.add_all([procedure, step, run])
        session.commit()
        session.refresh(run)

        service = ProcedureRunService(session)
        payload = {"email": "user@example.com", "age": "33"}
        state, errors = service.commit_step(run_id=run.id, step_key="intro", payload=payload)

        assert errors == []
        assert state is not None
        assert state.payload == {"email": "user@example.com", "age": 33}

        stored = session.execute(
            select(models.ProcedureRunStepState).where(
                models.ProcedureRunStepState.run_id == run.id,
                models.ProcedureRunStepState.step_key == "intro",
            )
        ).scalar_one()
        assert stored.payload == {"email": "user@example.com", "age": 33}
    finally:
        _teardown_session(session, engine)


def test_commit_step_rejects_invalid_payload() -> None:
    session, engine = _build_session()
    try:
        procedure = models.Procedure(name="Proc", description="Test procedure")
        step = models.ProcedureStep(
            procedure=procedure,
            key="intro",
            title="Intro",
            prompt="Fill in details",
            slots=[
                {"name": "email", "type": "email", "required": True},
            ],
            position=0,
        )
        run = models.ProcedureRun(procedure=procedure, user_id="user-1", state="in_progress")

        session.add_all([procedure, step, run])
        session.commit()
        session.refresh(run)

        service = ProcedureRunService(session)
        _, errors = service.commit_step(
            run_id=run.id,
            step_key="intro",
            payload={"email": "invalid"},
        )

        assert errors == [
            {"field": "email", "code": "validation.email", "params": {}},
        ]
        states = session.execute(select(models.ProcedureRunStepState)).scalars().all()
        assert states == []
    finally:
        _teardown_session(session, engine)
