import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base


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
    name = name_env if name_env is not None else ("rbok.db" if driver.startswith("sqlite") else "rbok")

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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
