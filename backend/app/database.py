"""Database configuration for the Réalisons backend."""
from __future__ import annotations

import os
from typing import AsyncGenerator, Dict

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, StaticPool


def _ensure_async_driver(url: str) -> str:
    sa_url = make_url(url)
    drivername = sa_url.drivername
    if drivername.startswith("postgresql") and "asyncpg" not in drivername:
        drivername = "postgresql+asyncpg"
    elif drivername.startswith("sqlite") and "aiosqlite" not in drivername:
        drivername = "sqlite+aiosqlite"
    elif drivername.startswith("mysql") and "aiomysql" not in drivername:
        drivername = "mysql+aiomysql"
    return str(sa_url.set(drivername=drivername))


def _build_database_url() -> str:
    """Build the database URL from environment variables."""

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return _ensure_async_driver(database_url)

    driver = os.getenv("DB_DRIVER", "postgresql+asyncpg")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name_env = os.getenv("DB_NAME")
    name = name_env if name_env is not None else ("rbok.db" if driver.startswith("sqlite") else "rbok")

    if driver.startswith("sqlite"):
        if name == ":memory:":
            return "sqlite+aiosqlite:///:memory:"
        if name.startswith("file:"):
            return f"sqlite+aiosqlite:///{name}"
        if name.startswith("/"):
            return f"sqlite+aiosqlite://{name}"
        return f"sqlite+aiosqlite:///{name}"

    if "+" not in driver:
        driver = f"{driver}+asyncpg" if driver.startswith("postgresql") else driver

    return f"{driver}://{user}:{password}@{host}:{port}/{name}"


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer") from None


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


SQLALCHEMY_DATABASE_URL = _build_database_url()


def _engine_config(url: str) -> Dict[str, object]:
    """Build keyword arguments for ``create_async_engine`` based on the URL."""

    kwargs: Dict[str, object] = {"echo": _get_bool_env("DB_ECHO", False)}

    if url.startswith("sqlite+aiosqlite"):
        kwargs["poolclass"] = StaticPool if url.endswith(":memory:") else NullPool
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(
            {
                "pool_size": _get_int_env("DB_POOL_SIZE", 10),
                "max_overflow": _get_int_env("DB_MAX_OVERFLOW", 20),
                "pool_timeout": _get_int_env("DB_POOL_TIMEOUT", 30),
                "pool_recycle": _get_int_env("DB_POOL_RECYCLE", 1800),
                "pool_pre_ping": _get_bool_env("DB_POOL_PRE_PING", True),
            }
        )

    return kwargs


engine: AsyncEngine = create_async_engine(SQLALCHEMY_DATABASE_URL, **_engine_config(SQLALCHEMY_DATABASE_URL))

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an ``AsyncSession``."""

    async with AsyncSessionLocal() as session:
        yield session
