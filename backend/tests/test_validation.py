from __future__ import annotations

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.auth import User, get_current_user, oauth2_scheme
from app.database import get_db
from app.main import app, procedures_db, runs_db

from fastapi.testclient import TestClient


def test_run_creation_requires_procedure_id(client: TestClient) -> None:
    response = client.post("/runs", json={})
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure(client: TestClient) -> None:
    response = client.post("/runs", json={"procedure_id": "missing"})
from __future__ import annotations

from fastapi.testclient import TestClient

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


def setup_function() -> None:
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


def get_token(username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_run_creation_requires_procedure_id():
    response = client.post("/runs", json={}, headers=AUTH_HEADERS)
    user_token = get_token("bob", "userpass")
    response = client.post("/runs", headers=auth_header(user_token))
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure():
    response = client.post("/runs", json={"procedure_id": "missing"}, headers=AUTH_HEADERS)
    user_token = get_token("bob", "userpass")
    response = client.post(
        "/runs",
        params={"procedure_id": "missing"},
def test_run_creation_requires_procedure_id() -> None:
    user_token = get_token("bob", "userpass")
    response = client.post("/runs", json={}, headers=auth_header(user_token))
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure() -> None:
    user_token = get_token("bob", "userpass")

def get_token(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def test_run_creation_requires_procedure_id(client: TestClient, auth_header) -> None:
    user_token = get_token(client, "bob", "userpass")
    response = client.post(
        "/runs",
        json={},
        headers=auth_header(user_token),
    )
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure(client: TestClient, auth_header) -> None:
    user_token = get_token(client, "bob", "userpass")
    response = client.post(
        "/runs",
        json={"procedure_id": "missing"},
        headers=auth_header(user_token),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def test_procedure_creation_requires_steps_structure():
    admin_token = get_token("alice", "adminpass")
def test_procedure_creation_requires_steps_structure(client: TestClient) -> None:
def test_procedure_creation_requires_steps_structure() -> None:
    admin_token = get_token("alice", "adminpass")
def test_procedure_creation_requires_steps_structure(client: TestClient, auth_header) -> None:
    admin_token = get_token(client, "alice", "adminpass")
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
    response = client.post("/procedures", json=payload, headers=auth_header(admin_token))
    assert response.status_code == 422
