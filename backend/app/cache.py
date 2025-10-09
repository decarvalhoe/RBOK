"""Redis cache helper utilities for the Réalisons backend."""
from __future__ import annotations

import os
from typing import Optional

import redis
from redis import Redis

__all__ = ["get_redis_client", "set_redis_client", "reset_redis_client"]


_redis_client: Optional[Redis] = None


def _build_redis_url() -> str:
    """Build the Redis connection URL from environment variables."""

    url = os.getenv("REDIS_URL")
    if url:
        return url

    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    db = os.getenv("REDIS_DB", "0")
    password = os.getenv("REDIS_PASSWORD")
    use_tls = os.getenv("REDIS_TLS", "false").lower() in {"1", "true", "yes"}

    scheme = "rediss" if use_tls else "redis"
    if password:
        return f"{scheme}://:{password}@{host}:{port}/{db}"
    return f"{scheme}://{host}:{port}/{db}"


def _create_client() -> Redis:
    """Instantiate a Redis client using the resolved configuration."""

    return redis.Redis.from_url(_build_redis_url(), decode_responses=True)


def get_redis_client() -> Redis:
    """Return a singleton Redis client instance."""

    global _redis_client
    if _redis_client is None:
        _redis_client = _create_client()
    return _redis_client


def set_redis_client(client: Optional[Redis]) -> None:
    """Override the global Redis client (useful for tests)."""

    global _redis_client
    _redis_client = client


def reset_redis_client() -> None:
    """Reset the cached Redis client forcing a fresh connection on next access."""

    set_redis_client(None)
