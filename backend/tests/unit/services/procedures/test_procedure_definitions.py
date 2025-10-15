from __future__ import annotations

import os
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.database import Base
from app.services.procedure_definitions import (
    ProcedureDefinitionError,
    ProcedureService,
)

os.environ.setdefault("REALISONS_SECRET_KEY", "test-secret-key")
os.environ.setdefault("RBOK_SKIP_MAIN_IMPORT", "1")


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_save_procedure_rejects_duplicate_structure(db_session: Session) -> None:
    service = ProcedureService(db_session)

    payload = {
        "name": "Safety checklist",
        "description": "Ensure safety steps",
        "steps": [
            {
                "key": "prepare",
                "title": "Prepare site",
                "prompt": "Get ready",
                "slots": [
                    {"name": "operator", "type": "string", "required": True},
                    {"name": "operator", "type": "string", "required": False},
                ],
                "checklists": [
                    {"key": "ppe", "label": "PPE verified", "required": True},
                    {"key": "ppe", "label": "PPE confirmed", "required": True},
                ],
            },
            {
                "key": "prepare",
                "title": "Duplicate step",
                "prompt": "",
                "slots": [],
                "checklists": [],
            },
        ],
    }

    with pytest.raises(ProcedureDefinitionError) as exc_info:
        service.save_procedure(payload, actor="tester")

    issues = exc_info.value.issues
    assert any(issue["field"] == "steps[1].key" for issue in issues)
    assert any("slots" in issue["field"] for issue in issues)
    assert any("checklists" in issue["field"] for issue in issues)
    assert db_session.query(models.Procedure).count() == 0
