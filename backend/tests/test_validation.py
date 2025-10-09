import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.auth import User, get_current_user, oauth2_scheme
from app.database import get_db
from app.main import app, procedures_db, runs_db


app.dependency_overrides[get_current_user] = lambda: User(
    subject="test",
    username="admin",
    roles=["app-admin"],
    role="admin",
)
app.dependency_overrides[oauth2_scheme] = lambda: "test-token"

client = TestClient(app)

AUTH_HEADERS = {"Authorization": "Bearer test-token"}


def setup_function():
    procedures_db.clear()
    runs_db.clear()
    class _DummySession:
        def query(self, *args, **kwargs):
            return self

        def options(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

        def add(self, *args, **kwargs):
            return None

        def commit(self):
            return None

        def refresh(self, *args, **kwargs):
            return None

    dummy_session = _DummySession()

    def override_get_db():
        yield dummy_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: User(
        subject="test",
        username="admin",
        roles=["app-admin"],
        role="admin",
    )
    app.dependency_overrides[oauth2_scheme] = lambda: "test-token"


def test_run_creation_requires_procedure_id():
    response = client.post("/runs", json={}, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure():
    response = client.post("/runs", json={"procedure_id": "missing"}, headers=AUTH_HEADERS)
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def test_procedure_creation_requires_steps_structure():
    payload = {
        "name": "Demo",
        "description": "A sample procedure",
        "steps": [
            {
                "key": "step-1",
                "title": "Title",
                "prompt": "Prompt",
                "slots": {"not": "a list"},
            }
        ],
    }
    response = client.post("/procedures", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422
