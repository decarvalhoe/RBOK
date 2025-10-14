"""Integration tests covering the authorization flow with stubbed services."""
from __future__ import annotations

from typing import Dict

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import runs as runs_api
from app.auth import Token, TokenIntrospection
from app.main import app


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
    monkeypatch.setattr(runs_api, "get_opa_client", lambda: dummy_opa)

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
) -> None:
    procedure_payload = {
        "name": "Integration Procedure",
        "description": "Created via integration test",
        "steps": [
            {
                "key": "step-1",
                "title": "Step 1",
                "prompt": "Do the first thing",
                "slots": [],
                "checklist": [],
            }
        ],
    }

    create_response = configured_client.post("/procedures", json=procedure_payload, headers=admin_headers)
    assert create_response.status_code == 201
    created_procedure = create_response.json()
    procedure_id = created_procedure["id"]

    forbidden_response = configured_client.post("/procedures", json=procedure_payload, headers=user_headers)
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

    run_response_user = configured_client.post("/runs", json=run_payload, headers=user_headers)
    assert run_response_user.status_code == 201
    run_data = run_response_user.json()
    assert run_data["procedure_id"] == procedure_id

    run_response_admin = configured_client.post("/runs", json=run_payload, headers=admin_headers)
    assert run_response_admin.status_code == 201

    opa_denied = configured_client.post("/runs", json=run_payload, headers=unauthorized_headers)
    assert opa_denied.status_code == 403

    policy_denied = configured_client.post(
        "/runs",
        json={"procedure_id": "missing", "user_id": "user-42"},
        headers=user_headers,
    )
    assert policy_denied.status_code == 404
