from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("REALISONS_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("RBOK_SKIP_MAIN_IMPORT", "1")

try:  # pragma: no cover - optional dependency during tests
    from app.cache import set_redis_client  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - fallback when optional deps missing
    def set_redis_client(_client):  # type: ignore[override]
        return None

from app.database import Base  # noqa: E402


@pytest.fixture()
def test_session(tmp_path) -> Generator[Session, None, None]:
    database_url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
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
def redis_client():
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    set_redis_client(client)
    try:
        yield client
    finally:
        client.flushall()
        set_redis_client(None)


@pytest.fixture()
def client(test_session: Session, redis_client):
    from fastapi.testclient import TestClient

    from app.database import get_db  # noqa: E402
    from app.main import app  # noqa: E402

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_session
        finally:
            test_session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_header():
    def _build(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _build
