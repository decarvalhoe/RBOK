from __future__ import annotations

from typing import Dict, Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.runs import router as runs_router
from app.database import Base, get_db
from app import models


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    test_app = FastAPI()
    test_app.include_router(runs_router)

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            db_session.rollback()

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.pop(get_db, None)


def _create_procedure(session: Session) -> models.Procedure:
    procedure = models.Procedure(
        name="Diagnostic ventilation",
        description="Mesures de contrôle",
    )
    step_one = models.ProcedureStep(
        procedure=procedure,
        key="step-prepare",
        title="Préparer la zone",
        prompt="Vérifier les prérequis.",
        slots=[{"name": "operator_email", "type": "string", "required": True}],
        position=0,
    )
    step_two = models.ProcedureStep(
        procedure=procedure,
        key="step-measure",
        title="Mesurer la ventilation",
        prompt="Capturer les mesures.",
        slots=[{"name": "airflow", "type": "number", "required": False}],
        position=1,
    )
    session.add_all([procedure, step_one, step_two])
    session.commit()
    return procedure


def _start_run(client: TestClient, procedure_id: str, user_id: str = "tech-1") -> Dict[str, object]:
    response = client.post(
        "/runs",
        json={"procedure_id": procedure_id, "user_id": user_id},
    )
    assert response.status_code == 201
    return response.json()


def test_create_run_exposes_initial_state(client: TestClient, db_session: Session) -> None:
    procedure = _create_procedure(db_session)

    payload = _start_run(client, procedure.id, "tech-42")

    assert payload["state"] == "pending"
    assert payload["current_step"] == "step-prepare"
    assert payload["steps"][0]["status"] == "in_progress"
    assert payload["steps"][1]["status"] == "pending"

    get_response = client.get(f"/runs/{payload['id']}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["id"] == payload["id"]
    assert body["steps"][0]["status"] == "in_progress"


def test_commit_step_advances_run(client: TestClient, db_session: Session) -> None:
    procedure = _create_procedure(db_session)
    run = _start_run(client, procedure.id)

    commit_first = client.post(
        f"/runs/{run['id']}/commit-step",
        json={
            "step_key": "step-prepare",
            "slots": {"operator_email": "tech@example.com"},
            "checklist": [
                {"key": "ppe", "label": "PPE vérifié", "completed": True},
            ],
        },
    )
    assert commit_first.status_code == 200
    after_first = commit_first.json()
    assert after_first["state"] == "in_progress"
    assert after_first["steps"][0]["status"] == "completed"
    assert after_first["steps"][1]["status"] == "in_progress"

    commit_second = client.post(
        f"/runs/{run['id']}/commit-step",
        json={
            "step_key": "step-measure",
            "slots": {"airflow": 32.5},
            "checklist": [],
        },
    )
    assert commit_second.status_code == 200
    after_second = commit_second.json()
    assert after_second["state"] == "completed"
    assert after_second["current_step"] is None
    assert after_second["steps"][1]["status"] == "completed"
    assert after_second["closed_at"] is not None


def test_commit_step_validates_required_slots(client: TestClient, db_session: Session) -> None:
    procedure = _create_procedure(db_session)
    run = _start_run(client, procedure.id)

    response = client.post(
        f"/runs/{run['id']}/commit-step",
        json={
            "step_key": "step-prepare",
            "slots": {},
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["error"] == "slot_validation_failed"
    assert any(
        issue.get("slot") == "operator_email"
        for issue in body["detail"].get("issues", [])
    )


def test_commit_step_rejects_out_of_order(client: TestClient, db_session: Session) -> None:
    procedure = _create_procedure(db_session)
    run = _start_run(client, procedure.id)

    response = client.post(
        f"/runs/{run['id']}/commit-step",
        json={
            "step_key": "step-measure",
            "slots": {"airflow": 12.0},
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"] == "invalid_transition"
