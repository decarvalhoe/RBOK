"""Integration tests covering Keycloak OIDC validation and OPA policies."""
from __future__ import annotations

import json
import os
import shutil
import pytest

pytest.skip(
    "Legacy authorization integration suite requires external services and the previous API.",
    allow_module_level=True,
)

import subprocess
import time
from pathlib import Path
from typing import Generator

import httpx
from fastapi.testclient import TestClient
from keycloak import KeycloakOpenID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth import get_keycloak_service, get_opa_client, get_settings
from app.database import Base, get_db
from app.main import app

COMPOSE_FILE = Path(__file__).with_name("docker-compose.yml")
KEYCLOAK_URL = "http://localhost:8081"
OPA_URL = "http://localhost:8181/v1/data/realison/authz"


def _wait_for(url: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code < 500:
                return
        except httpx.HTTPError:
            time.sleep(2)
        else:
            time.sleep(2)
    raise RuntimeError(f"Service at {url} did not become ready in time")


@pytest.fixture(scope="session")
def docker_environment() -> Generator[None, None, None]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is required for integration tests")

    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"], check=False)
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"], check=True)

    try:
        _wait_for(f"{KEYCLOAK_URL}/realms/realison/.well-known/openid-configuration")
        _wait_for("http://localhost:8181/health")
        yield
    finally:
        subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"], check=False)


@pytest.fixture(scope="session")
def configured_client(docker_environment: None, tmp_path_factory) -> Generator[TestClient, None, None]:
    db_dir = tmp_path_factory.mktemp("db")
    database_url = f"sqlite:///{db_dir}/integration.db"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    os.environ["KEYCLOAK_SERVER_URL"] = KEYCLOAK_URL
    os.environ["KEYCLOAK_REALM"] = "realison"
    os.environ["KEYCLOAK_CLIENT_ID"] = "realison-backend"
    os.environ["KEYCLOAK_CLIENT_SECRET"] = "backend-secret"
    os.environ["KEYCLOAK_ROLE_MAPPING"] = json.dumps({"app-admin": "admin", "app-user": "user"})
    os.environ["OPA_URL"] = OPA_URL

    get_settings.cache_clear()
    get_keycloak_service.cache_clear()
    get_opa_client.cache_clear()

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.rollback()
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    get_keycloak_service.cache_clear()
    get_opa_client.cache_clear()


@pytest.fixture(scope="session")
def keycloak_openid(docker_environment: None) -> KeycloakOpenID:
    return KeycloakOpenID(
        server_url=KEYCLOAK_URL,
        realm_name="realison",
        client_id="realison-backend",
        client_secret_key="backend-secret",
    )


def test_end_to_end_authorization(configured_client: TestClient, keycloak_openid: KeycloakOpenID) -> None:
    admin_tokens = keycloak_openid.token(username="alice", password="adminpass")
    user_tokens = keycloak_openid.token(username="bob", password="userpass")
    unauthorized_tokens = keycloak_openid.token(username="eve", password="noroles")

    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    user_headers = {"Authorization": f"Bearer {user_tokens['access_token']}"}
    unauthorized_headers = {"Authorization": f"Bearer {unauthorized_tokens['access_token']}"}

    procedure_payload = {
        "name": "Integration Procedure",
        "description": "Created via integration test",
        "steps": [
            {
                "key": "step-1",
                "title": "Step 1",
                "prompt": "Do the first thing",
                "slots": [],
            }
        ],
    }

    create_response = configured_client.post("/procedures", json=procedure_payload, headers=admin_headers)
    assert create_response.status_code in (200, 201)
    created_procedure = create_response.json()
    procedure_id = created_procedure["id"]

    forbidden_response = configured_client.post("/procedures", json=procedure_payload, headers=user_headers)
    assert forbidden_response.status_code == 403

    introspect_response = configured_client.post(
        "/auth/introspect",
        json={"token": admin_tokens["access_token"]},
    )
    introspect_response.raise_for_status()
    assert introspect_response.json()["active"] is True

    refresh_response = configured_client.post(
        "/auth/refresh",
        json={"token": admin_tokens["refresh_token"]},
    )
    refresh_response.raise_for_status()
    assert "access_token" in refresh_response.json()

    run_payload = {"procedure_id": procedure_id}

    run_response_user = configured_client.post("/runs", json=run_payload, headers=user_headers)
    assert run_response_user.status_code in (200, 201)
    run_data = run_response_user.json()
    assert run_data["procedure_id"] == procedure_id

    run_response_admin = configured_client.post("/runs", json=run_payload, headers=admin_headers)
    assert run_response_admin.status_code in (200, 201)

    opa_denied = configured_client.post("/runs", json=run_payload, headers=unauthorized_headers)
    assert opa_denied.status_code == 403

    policy_denied = configured_client.post(
        "/runs",
        json={"procedure_id": "missing"},
        headers=user_headers,
    )
    assert policy_denied.status_code == 404
