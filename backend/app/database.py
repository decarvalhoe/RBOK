from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


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
        span.set_attribute("db.system", engine.url.get_backend_name())
        if engine.url.database:
            span.set_attribute("db.name", engine.url.database)
        db = SessionLocal()
        try:
            yield db
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:  # pragma: no cover - defensive
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            db.close()


__all__ = ["Base", "SessionLocal", "engine", "get_db"]
