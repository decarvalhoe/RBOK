"""Database helpers for the Réalisons backend."""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

try:  # pragma: no cover - optional dependency when telemetry disabled
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
except ModuleNotFoundError:  # pragma: no cover - provide no-op fallbacks for tests
    class _NoopSpan:
        def __enter__(self) -> "_NoopSpan":  # noqa: D401 - trivial
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

        def set_attribute(self, *args, **kwargs) -> None:
            return None

        def set_status(self, *args, **kwargs) -> None:
            return None

        def record_exception(self, exc) -> None:
            return None

    class _NoopTracer:
        def start_as_current_span(self, *args, **kwargs) -> _NoopSpan:
            return _NoopSpan()

    class _NoopTracerProvider:
        def get_tracer(self, *args, **kwargs) -> _NoopTracer:
            return _NoopTracer()

    class _NoopStatusCode:
        OK = "OK"
        ERROR = "ERROR"

    class _NoopStatus:
        def __init__(self, *args, **kwargs) -> None:
            return None

    trace = _NoopTracerProvider()  # type: ignore[assignment]
    StatusCode = _NoopStatusCode  # type: ignore[assignment]
    Status = _NoopStatus  # type: ignore[assignment]


def _build_database_url() -> str:
    """Build the database URL from environment variables."""

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    driver = os.getenv("DB_DRIVER", "postgresql")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name_env = os.getenv("DB_NAME")
    name = (
        name_env if name_env is not None else ("rbok.db" if driver.startswith("sqlite") else "rbok")
    )

    if driver.startswith("sqlite"):
        if name == ":memory:":
            return "sqlite+pysqlite:///:memory:"
        if name.startswith("file:"):
            return f"sqlite+pysqlite:///{name}"
        if name.startswith("/"):
            return f"sqlite+pysqlite://{name}"
        return f"sqlite+pysqlite:///{name}"

    return f"{driver}://{user}:{password}@{host}:{port}/{name}"


SQLALCHEMY_DATABASE_URL = _build_database_url()

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, future=True, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


tracer = trace.get_tracer(__name__)


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session."""

    with tracer.start_as_current_span("database.session") as span:
        try:
            backend_name = engine.url.get_backend_name()
        except AttributeError:  # pragma: no cover - defensive when engine misconfigured
            backend_name = "unknown"
        span.set_attribute("db.system", backend_name)
        if getattr(engine.url, "database", None):
            span.set_attribute("db.name", engine.url.database)
        db = SessionLocal()
        try:
            yield db
            if hasattr(StatusCode, "OK"):
                span.set_status(Status(StatusCode.OK))  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - defensive
            if hasattr(span, "record_exception"):
                span.record_exception(exc)
            if hasattr(StatusCode, "ERROR"):
                span.set_status(Status(StatusCode.ERROR, str(exc)))  # type: ignore[arg-type]
            raise
        finally:
            db.close()


__all__ = ["Base", "SessionLocal", "engine", "get_db"]
