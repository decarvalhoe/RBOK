from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any, Dict

import pytest

os.environ.setdefault("REALISONS_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("RBOK_SKIP_MAIN_IMPORT", "1")

if os.getenv("BACKEND_SKIP_APP_CONFTEST") == "1":
    pytest_plugins: list[str] = []
else:
    from fastapi.testclient import TestClient
    from fakeredis import FakeStrictRedis
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    try:  # pragma: no cover - optional dependency during tests
        from app.cache import reset_redis_client, set_redis_client  # noqa: E402
    except ModuleNotFoundError:  # pragma: no cover - fallback when optional deps missing
        def set_redis_client(_client):  # type: ignore[override]
            return None

        def reset_redis_client():  # type: ignore[override]
            return None

    from app.database import Base, get_db  # noqa: E402
    from app.main import app  # noqa: E402

    @pytest.fixture()
    def patch_opa(monkeypatch: pytest.MonkeyPatch):
        """Stub the OPA client with a controllable in-memory implementation."""

        import app.auth as auth
        from app.api import runs as runs_api
        from app.services.procedure_runs import ProcedureRunService
        from fastapi import HTTPException, status

        class DummyOPAClient:
            def __init__(self) -> None:
                self.denied_resources: set[str] = set()

            def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
                resource = payload.get("input", {}).get("resource")
                allowed = resource not in self.denied_resources
                return {"result": {"allow": allowed}}

        dummy = DummyOPAClient()

        def _get_dummy_client() -> DummyOPAClient:
            return dummy

        setattr(_get_dummy_client, "cache_clear", lambda: None)  # type: ignore[attr-defined]

        monkeypatch.setattr(auth, "get_opa_client", _get_dummy_client)
        monkeypatch.setattr(runs_api, "get_opa_client", _get_dummy_client, raising=False)

        original_start_run = ProcedureRunService.start_run

        def patched_start_run(
            self,
            *,
            procedure_id: str,
            user_id: str,
            actor: str | None = None,
        ) -> Any:
            client = auth.get_opa_client()
            if client is not None:
                decision = client.evaluate({"input": {"resource": procedure_id}})
                result = decision.get("result")
                if isinstance(result, dict):
                    allowed = bool(result.get("allow"))
                else:
                    allowed = bool(result)
                if not allowed:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied by policy",
                    )

            return original_start_run(
                self, procedure_id=procedure_id, user_id=user_id, actor=actor
            )

        monkeypatch.setattr(ProcedureRunService, "start_run", patched_start_run)

        return dummy

    @pytest.fixture()
    def test_session(tmp_path) -> Generator[Session, None, None]:
        """Provide an isolated SQLite database session for each test run."""

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
            engine.dispose()

    @pytest.fixture()
    def redis_client() -> Generator[FakeStrictRedis, None, None]:
        """Provide a fake Redis client wired into the cache helpers."""

        client = FakeStrictRedis(decode_responses=True)
        set_redis_client(client)
        try:
            yield client
        finally:
            reset_redis_client()

    @pytest.fixture()
    def client(test_session: Session, redis_client: FakeStrictRedis) -> Generator[TestClient, None, None]:
        """Return a FastAPI test client with database and cache dependencies patched."""

        def override_get_db() -> Generator[Session, None, None]:
            try:
                yield test_session
            finally:
                test_session.rollback()

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as test_client:
            yield test_client
        app.dependency_overrides.clear()
