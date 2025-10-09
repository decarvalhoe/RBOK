import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app, procedures_db, runs_db


client = TestClient(app)


def setup_function():
    procedures_db.clear()
    runs_db.clear()


def test_run_creation_requires_procedure_id():
    response = client.post("/runs", json={})
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure():
    response = client.post("/runs", json={"procedure_id": "missing"})
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
    response = client.post("/procedures", json=payload)
    assert response.status_code == 422
