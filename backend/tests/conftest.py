from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from fakeredis import FakeStrictRedis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure a deterministic but non-default secret key is available during tests so that
# the configuration validation passes.
os.environ.setdefault("REALISONS_SECRET_KEY", "test-secret-key")

# Import the application only after the environment is prepared.
from app.cache import reset_redis_client, set_redis_client
from app.database import Base, get_db
from app.main import app


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
