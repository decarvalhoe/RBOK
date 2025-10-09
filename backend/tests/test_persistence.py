from typing import Generator
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.auth import User, get_current_user, oauth2_scheme
from app.main import app
from app.database import get_db, Base


@pytest.fixture()
def test_session(tmp_path) -> Generator[Session, None, None]:
    database_url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(test_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_session
        finally:
            test_session.rollback()

    app.dependency_overrides[get_db] = override_get_db

    def override_user() -> User:
        return User(subject="test", username="admin", roles=["app-admin"], role="admin")

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[oauth2_scheme] = lambda: "test-token"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(oauth2_scheme, None)


def test_create_and_fetch_procedure(client: TestClient) -> None:
    payload = {
        "name": "Test Procedure",
        "description": "Testing persistence",
        "steps": [
            {
                "key": "step-1",
                "title": "Step 1",
                "prompt": "Do something",
                "slots": [{"name": "slot1"}],
            },
            {
                "key": "step-2",
                "title": "Step 2",
                "prompt": "Do something else",
                "slots": [],
            },
        ],
    }

    response = client.post("/procedures", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"]
    assert data["name"] == payload["name"]
    assert len(data["steps"]) == 2
    assert data["steps"][0]["key"] == "step-1"

    list_response = client.get("/procedures")
    assert list_response.status_code == 200
    procedures = list_response.json()
    assert len(procedures) == 1
    assert procedures[0]["id"] == data["id"]

    get_response = client.get(f"/procedures/{data['id']}")
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["description"] == payload["description"]
    assert fetched["steps"][1]["key"] == "step-2"


def test_start_and_get_run(client: TestClient) -> None:
    procedure_response = client.post(
        "/procedures",
        json={
            "name": "Run Procedure",
            "description": "For run test",
            "steps": [],
        },
    )
    procedure_response.raise_for_status()
    procedure_id = procedure_response.json()["id"]

    run_response = client.post(
        "/runs",
        json={"procedure_id": procedure_id, "user_id": "alice"},
    )
    assert run_response.status_code == 201
    run_data = run_response.json()
    assert run_data["procedure_id"] == procedure_id
    assert run_data["user_id"] == "alice"
    assert run_data["state"] == "started"

    get_response = client.get(f"/runs/{run_data['id']}")
    assert get_response.status_code == 200
    fetched_run = get_response.json()
    assert fetched_run["id"] == run_data["id"]
    assert fetched_run["procedure_id"] == procedure_id
