from fastapi.testclient import TestClient


def test_run_creation_requires_procedure_id(client: TestClient) -> None:
    response = client.post("/runs", json={})
    assert response.status_code == 422


def test_run_creation_requires_existing_procedure(client: TestClient) -> None:
    response = client.post("/runs", json={"procedure_id": "missing"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Procedure not found"


def test_procedure_creation_requires_steps_structure(client: TestClient) -> None:
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
