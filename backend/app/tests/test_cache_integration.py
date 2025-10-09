from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.main import (
    PROCEDURE_LIST_CACHE_KEY,
    procedure_meta_cache_key,
    procedure_steps_cache_key,
    run_cache_key,
)


def get_token(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def test_procedure_list_cache_hit_and_invalidation(
    client: TestClient, redis_client, auth_header, test_session: Session
) -> None:
    admin_token = get_token(client, "alice", "adminpass")
    create_payload = {
        "name": "Procédure cache",
        "description": "Description initiale",
        "steps": [
            {
                "key": "collect",
                "title": "Collect",
                "prompt": "Collect the item",
                "slots": [{"name": "code"}],
            }
        ],
    }
    create_response = client.post(
        "/procedures",
        json=create_payload,
        headers=auth_header(admin_token),
    )
    create_response.raise_for_status()
    procedure_id = create_response.json()["id"]

    redis_client.flushall()

    first_response = client.get("/procedures")
    assert first_response.status_code == 200
    body = first_response.json()
    assert body[0]["id"] == procedure_id
    assert redis_client.exists(PROCEDURE_LIST_CACHE_KEY)
    assert redis_client.exists(procedure_meta_cache_key(procedure_id))
    assert redis_client.exists(procedure_steps_cache_key(procedure_id))
    assert redis_client.ttl(procedure_steps_cache_key(procedure_id)) > 0

    db_procedure = test_session.get(models.Procedure, procedure_id)
    assert db_procedure is not None
    db_procedure.description = "Description mise à jour"
    test_session.commit()

    cached_response = client.get("/procedures")
    assert cached_response.json()[0]["description"] == "Description initiale"

    second_payload = {
        "name": "Nouvelle procédure",
        "description": "Nouvelle description",
        "steps": [],
    }
    client.post(
        "/procedures",
        json=second_payload,
        headers=auth_header(admin_token),
    )

    assert not redis_client.exists(PROCEDURE_LIST_CACHE_KEY)

    refreshed_response = client.get("/procedures")
    refreshed = refreshed_response.json()
    descriptions = {item["id"]: item["description"] for item in refreshed}
    assert descriptions[procedure_id] == "Description mise à jour"


def test_get_run_uses_cache(client: TestClient, redis_client, auth_header, test_session: Session) -> None:
    admin_token = get_token(client, "alice", "adminpass")
    procedure_response = client.post(
        "/procedures",
        json={
            "name": "Procédure run",
            "description": "Pour les tests", 
            "steps": [],
        },
        headers=auth_header(admin_token),
    )
    procedure_response.raise_for_status()
    procedure_id = procedure_response.json()["id"]

    user_token = get_token(client, "bob", "userpass")
    run_response = client.post(
        "/runs",
        json={"procedure_id": procedure_id},
        headers=auth_header(user_token),
    )
    run_response.raise_for_status()
    run_id = run_response.json()["id"]
    assert redis_client.exists(run_cache_key(run_id))

    db_run = test_session.get(models.ProcedureRun, run_id)
    assert db_run is not None
    db_run.state = "manually-updated"
    test_session.commit()

    cached_response = client.get(f"/runs/{run_id}")
    assert cached_response.status_code == 200
    assert cached_response.json()["state"] == "started"

    redis_client.delete(run_cache_key(run_id))
    refreshed_response = client.get(f"/runs/{run_id}")
    assert refreshed_response.json()["state"] == "manually-updated"
