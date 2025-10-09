from fastapi.testclient import TestClient


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

    update_response = client.patch(
        f"/runs/{run_data['id']}",
        json={"state": "completed"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["state"] == "completed"

    commit_response = client.post(
        f"/runs/{run_data['id']}/steps/step-1/commit",
        json={"payload": {"answer": "done"}},
    )
    assert commit_response.status_code == 201
    commit_data = commit_response.json()
    assert commit_data["step_key"] == "step-1"
    assert commit_data["payload"] == {"answer": "done"}

    get_response = client.get(f"/runs/{run_data['id']}")
    assert get_response.status_code == 200
    fetched_run = get_response.json()
    assert fetched_run["id"] == run_data["id"]
    assert fetched_run["procedure_id"] == procedure_id
