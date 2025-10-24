"""Integration tests covering the authorization flow with stubbed services."""
from __future__ import annotations

from typing import Dict

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app import auth
from app.api import runs as runs_api
from app.auth import Token, TokenIntrospection
from app.main import app
from app.services.procedure_runs import ProcedureRunService


class DummyKeycloakService:
    """Minimal Keycloak service used for integration tests."""

    def __init__(self) -> None:
        self._payloads: Dict[str, Dict[str, object]] = {
            "admin-token": {
                "sub": "admin",
                "preferred_username": "alice",
                "email": "alice@example.com",
                "realm_access": {"roles": ["app-admin"]},
            },
            "user-token": {
                "sub": "user",
                "preferred_username": "bob",
                "email": "bob@example.com",
                "realm_access": {"roles": ["app-user"]},
            },
            "unauthorized-token": {
                "sub": "unauthorized",
                "preferred_username": "eve",
                "email": "eve@example.com",
                "realm_access": {"roles": []},
            },
        }

    def obtain_token(self, username: str, password: str) -> Token:  # pragma: no cover - not exercised
        return Token(access_token=f"{username}-token", refresh_token=f"{username}-refresh")

    def refresh_token(self, refresh_token: str) -> Token:
        return Token(access_token=f"refreshed-{refresh_token}", refresh_token=refresh_token)

    def introspect_token(self, token: str) -> TokenIntrospection:
        payload = self._payloads.get(token)
        return TokenIntrospection(active=payload is not None, username=payload.get("preferred_username") if payload else None)

    def decode_token(self, token: str) -> Dict[str, object]:
        payload = self._payloads.get(token)
        if payload is None:
            raise RuntimeError("Unknown token")
        return payload

    def extract_roles(self, payload: Dict[str, object]):
        return payload.get("realm_access", {}).get("roles", [])

    def map_role(self, roles):
        if "app-admin" in roles:
            return "admin"
        if "app-user" in roles:
            return "user"
        return "user"


class DummyOPAClient:
    def evaluate(self, payload: Dict[str, object]) -> Dict[str, object]:
        subject = payload.get("input", {}).get("subject", {})
        action = payload.get("input", {}).get("action")
        resource = payload.get("input", {}).get("resource")
        if subject.get("id") == "unauthorized":
            return {"result": {"allow": False, "reason": "unauthorized"}}
        if action == "runs:create" and resource == "missing":
            return {"result": {"allow": False, "reason": "not-found"}}
        return {"result": {"allow": True}}


@pytest.fixture()
def auth_stubs(monkeypatch):
    dummy_keycloak = DummyKeycloakService()
    dummy_opa = DummyOPAClient()

    original_get_keycloak_service = auth.get_keycloak_service
    original_get_opa_client = auth.get_opa_client

    original_get_keycloak_service.cache_clear()
    original_get_opa_client.cache_clear()

    monkeypatch.setattr(auth, "get_keycloak_service", lambda: dummy_keycloak)
    monkeypatch.setattr(auth, "get_opa_client", lambda: dummy_opa)
    monkeypatch.setattr(runs_api, "get_opa_client", lambda: dummy_opa, raising=False)

    username_to_subject = {
        payload.get("preferred_username"): payload.get("sub")
        for payload in dummy_keycloak._payloads.values()
    }

    original_start_run = ProcedureRunService.start_run

    def patched_start_run(
        self,
        *,
        procedure_id: str,
        user_id: str,
        actor: str | None = None,
    ):
        client = auth.get_opa_client()
        if client is not None:
            subject_id = username_to_subject.get(actor) or actor
            decision = client.evaluate(
                {
                    "input": {
                        "subject": {"id": subject_id, "username": actor},
                        "action": "runs:create",
                        "resource": procedure_id,
                    }
                }
            )
            result = decision.get("result") if isinstance(decision, dict) else decision
            allowed = bool(result.get("allow")) if isinstance(result, dict) else bool(result)
            if not allowed:
                detail = "Access denied by policy"
                status_code = status.HTTP_403_FORBIDDEN
                if isinstance(result, dict) and result.get("reason"):
                    detail = str(result["reason"])
                    if detail == "not-found":
                        status_code = status.HTTP_404_NOT_FOUND
                        detail = "Procedure not found"
                raise HTTPException(status_code=status_code, detail=detail)

        return original_start_run(self, procedure_id=procedure_id, user_id=user_id, actor=actor)

    monkeypatch.setattr(ProcedureRunService, "start_run", patched_start_run)

    yield dummy_keycloak, dummy_opa, original_get_keycloak_service, original_get_opa_client

    original_get_keycloak_service.cache_clear()
    original_get_opa_client.cache_clear()


@pytest.fixture()
def configured_client(
    client: TestClient,
    auth_stubs,
    admin_headers: Dict[str, str],
) -> TestClient:
    dummy_keycloak, dummy_opa, original_get_keycloak_service, original_get_opa_client = auth_stubs
    app.dependency_overrides[original_get_keycloak_service] = lambda: dummy_keycloak
    app.dependency_overrides[original_get_opa_client] = lambda: dummy_opa
    try:
        yield client
    finally:
        app.dependency_overrides.pop(original_get_keycloak_service, None)
        app.dependency_overrides.pop(original_get_opa_client, None)


@pytest.fixture()
def admin_headers() -> Dict[str, str]:
    return {"Authorization": "Bearer admin-token"}


@pytest.fixture()
def user_headers() -> Dict[str, str]:
    return {"Authorization": "Bearer user-token"}


@pytest.fixture()
def unauthorized_headers() -> Dict[str, str]:
    return {"Authorization": "Bearer unauthorized-token"}


def test_end_to_end_authorization(
    configured_client: TestClient,
    admin_headers: Dict[str, str],
    user_headers: Dict[str, str],
    unauthorized_headers: Dict[str, str],
    redis_client,
) -> None:
    def redis_version(key: str) -> int:
        value = redis_client.get(key)
        return int(value) if value is not None else 0

    # Warm up the procedure cache so we can observe invalidations.
    list_response = configured_client.get("/procedures", headers=admin_headers)
    assert list_response.status_code == 200
    list_version_before = redis_version("procedures:list:version")

    procedure_payload = {
        "name": "Integration Procedure",
        "description": "Created via integration test",
        "steps": [
            {
                "key": "preflight",
                "title": "Preflight checks",
                "prompt": "Collect operator details",
                "slots": [
                    {"name": "operator", "type": "string", "required": True, "label": "Operator"}
                ],
                "checklists": [
                    {"key": "fuel", "label": "Fuel level verified", "required": True},
                    {"key": "instruments", "label": "Instruments calibrated"},
                ],
            },
            {
                "key": "launch",
                "title": "Launch",
                "prompt": "Confirm launch readiness",
                "slots": [],
                "checklists": [
                    {"key": "countdown", "label": "Countdown complete", "required": True}
                ],
            },
        ],
    }

    create_response = configured_client.post(
        "/procedures", json=procedure_payload, headers=admin_headers
    )
    assert create_response.status_code == 201
    created_procedure = create_response.json()
    procedure_id = created_procedure["id"]

    # Procedure responses expose checklist metadata twice for backwards compatibility.
    first_step = created_procedure["steps"][0]
    assert [item["key"] for item in first_step["checklists"]] == ["fuel", "instruments"]
    assert first_step["checklist_items"] == first_step["checklists"]

    list_version_after = redis_version("procedures:list:version")
    assert list_version_after == list_version_before + 1
    detail_version_key = f"procedures:procedure:{procedure_id}:version"
    assert redis_version(detail_version_key) == 1

    detail_response = configured_client.get(
        f"/procedures/{procedure_id}", headers=admin_headers
    )
    assert detail_response.status_code == 200
    assert [item["key"] for item in detail_response.json()["steps"][1]["checklists"]] == [
        "countdown"
    ]

    forbidden_response = configured_client.post(
        "/procedures", json=procedure_payload, headers=user_headers
    )
    assert forbidden_response.status_code == 403

    introspect_response = configured_client.post(
        "/auth/introspect",
        json={"token": "admin-token"},
        headers=admin_headers,
    )
    assert introspect_response.status_code == 200
    assert introspect_response.json()["active"] is True

    refresh_response = configured_client.post(
        "/auth/refresh",
        json={"token": "admin-refresh"},
        headers=admin_headers,
    )
    assert refresh_response.status_code == 200
    assert "access_token" in refresh_response.json()

    run_payload = {"procedure_id": procedure_id, "user_id": "user-42"}

    run_response_user = configured_client.post(
        "/runs", json=run_payload, headers=user_headers
    )
    assert run_response_user.status_code == 201
    run_data = run_response_user.json()
    run_id = run_data["id"]
    assert run_data["procedure_id"] == procedure_id
    assert run_data["state"] == "pending"
    assert run_data["step_states"] == []
    assert [status["key"] for status in run_data["checklist_statuses"]] == [
        "fuel",
        "instruments",
        "countdown",
    ]
    initial_status_map = {
        status["key"]: status["completed"] for status in run_data["checklist_statuses"]
    }
    assert initial_status_map == {"fuel": False, "instruments": False, "countdown": False}
    assert run_data["checklist_progress"] == {
        "total": 3,
        "completed": 0,
        "percentage": 0.0,
    }

    run_snapshot_response = configured_client.get(
        f"/runs/{run_id}", headers=admin_headers
    )
    assert run_snapshot_response.status_code == 200
    run_version_key = f"procedures:run:{run_id}:version"
    run_version_before_commit = redis_version(run_version_key)
    assert run_version_before_commit == 1

    first_commit_response = configured_client.post(
        f"/runs/{run_id}/commit-step",
        json={
            "step_key": "preflight",
            "slots": {"operator": "bob"},
            "checklist": [
                {"key": "fuel", "completed": True},
                {"key": "instruments", "completed": True},
            ],
        },
        headers=user_headers,
    )
    assert first_commit_response.status_code == 200
    first_commit = first_commit_response.json()
    assert first_commit["state"] == "in_progress"
    assert len(first_commit["step_states"]) == 1
    assert first_commit["step_states"][0]["step_key"] == "preflight"
    assert first_commit["step_states"][0]["payload"]["slots"] == {"operator": "bob"}
    assert [item["key"] for item in first_commit["step_states"][0]["payload"]["checklist"]] == [
        "fuel",
        "instruments",
    ]
    assert [item["completed"] for item in first_commit["step_states"][0]["payload"]["checklist"]] == [
        True,
        True,
    ]
    first_commit_status_map = {
        item["key"]: item["completed"] for item in first_commit["checklist_statuses"]
    }
    assert first_commit_status_map == {
        "fuel": True,
        "instruments": True,
        "countdown": False,
    }
    assert first_commit["checklist_progress"]["total"] == 3
    assert first_commit["checklist_progress"]["completed"] == 2
    assert first_commit["checklist_progress"]["percentage"] == pytest.approx(66.6666, rel=1e-3)

    run_version_after_first_commit = redis_version(run_version_key)
    assert run_version_after_first_commit == run_version_before_commit + 1

    in_progress_state = configured_client.get(
        f"/runs/{run_id}", headers=admin_headers
    )
    assert in_progress_state.status_code == 200
    in_progress_payload = in_progress_state.json()
    assert in_progress_payload == first_commit

    second_commit_response = configured_client.post(
        f"/runs/{run_id}/commit-step",
        json={
            "step_key": "launch",
            "slots": {},
            "checklist": [
                {"key": "countdown", "completed": True},
            ],
        },
        headers=user_headers,
    )
    assert second_commit_response.status_code == 200
    second_commit = second_commit_response.json()
    assert second_commit["state"] == "completed"
    second_commit_status_map = {
        status["key"]: status["completed"]
        for status in second_commit["checklist_statuses"]
    }
    assert second_commit_status_map == {
        "fuel": True,
        "instruments": True,
        "countdown": True,
    }
    assert second_commit["checklist_progress"]["total"] == 3
    assert second_commit["checklist_progress"]["completed"] == 3
    assert second_commit["checklist_progress"]["percentage"] == pytest.approx(100.0)
    assert len(second_commit["step_states"]) == 2
    assert second_commit["step_states"][1]["step_key"] == "launch"

    run_version_after_second_commit = redis_version(run_version_key)
    assert run_version_after_second_commit == run_version_after_first_commit + 1

    final_state = configured_client.get(f"/runs/{run_id}", headers=admin_headers)
    assert final_state.status_code == 200
    final_payload = final_state.json()
    assert final_payload == second_commit

    second_run_response = configured_client.post(
        "/runs",
        json={"procedure_id": procedure_id, "user_id": "user-84"},
        headers=user_headers,
    )
    assert second_run_response.status_code == 201
    second_run_id = second_run_response.json()["id"]

    v2_commit_response = configured_client.post(
        f"/runs/{second_run_id}/steps/preflight/commit",
        json={
            "slots": {"operator": "bob"},
            "checklist": [
                {"key": "fuel", "completed": True},
                {"key": "instruments", "completed": True},
            ],
        },
        headers=user_headers,
    )
    assert v2_commit_response.status_code == 200
    v2_commit = v2_commit_response.json()
    assert v2_commit["run_state"] == "in_progress"
    assert v2_commit["step_state"]["step_key"] == "preflight"
    assert v2_commit["step_state"]["payload"]["slots"] == {"operator": "bob"}
    assert [item["key"] for item in v2_commit["step_state"]["payload"]["checklist"]] == [
        "fuel",
        "instruments",
    ]
    v2_commit_status_map = {
        item["key"]: item["completed"] for item in v2_commit["checklist_statuses"]
    }
    assert v2_commit_status_map == {
        "fuel": True,
        "instruments": True,
        "countdown": False,
    }

    run_response_admin = configured_client.post(
        "/runs", json=run_payload, headers=admin_headers
    )
    assert run_response_admin.status_code == 201

    opa_denied = configured_client.post(
        "/runs", json=run_payload, headers=unauthorized_headers
    )
    assert opa_denied.status_code == 403

    policy_denied = configured_client.post(
        "/runs",
        json={"procedure_id": "missing", "user_id": "user-42"},
        headers=user_headers,
    )
    assert policy_denied.status_code == 404
