"""Caching utilities for procedure listings, details, and run details."""
from __future__ import annotations

import json
import time
from typing import Callable, Optional, TypeVar

import structlog
from prometheus_client import Counter, Histogram
from redis.exceptions import RedisError

from ...cache import get_redis_client

logger = structlog.get_logger(__name__)

T = TypeVar("T")

DEFAULT_TTL_SECONDS = 300

_CACHE_NAMESPACE = "procedures"

_PROCEDURE_LIST_VERSION_KEY = f"{_CACHE_NAMESPACE}:list:version"
_PROCEDURE_VERSION_TEMPLATE = f"{_CACHE_NAMESPACE}:procedure:%s:version"
_RUN_VERSION_TEMPLATE = f"{_CACHE_NAMESPACE}:run:%s:version"

CACHE_HITS = Counter(
    "backend_procedure_cache_hits_total",
    "Number of cache hits for procedure-related resources.",
    labelnames=("resource",),
)
CACHE_MISSES = Counter(
    "backend_procedure_cache_misses_total",
    "Number of cache misses for procedure-related resources.",
    labelnames=("resource",),
)
CACHE_STORE = Counter(
    "backend_procedure_cache_store_total",
    "Number of times a payload was stored in the cache.",
    labelnames=("resource",),
)
CACHE_INVALIDATIONS = Counter(
    "backend_procedure_cache_invalidations_total",
    "Number of cache invalidations triggered for a resource.",
    labelnames=("resource",),
)
CACHE_FETCH_LATENCY = Histogram(
    "backend_procedure_cache_fetch_seconds",
    "Latency to obtain data for procedure-related resources.",
    labelnames=("resource", "source"),
)


def _load_json(raw: Optional[str]) -> Optional[T]:
    if raw is None:
        return None
    return json.loads(raw)


def _dump_json(data: T) -> str:
    return json.dumps(data, separators=(",", ":"))


def _ensure_version_key(version_key: str) -> str:
    client = get_redis_client()
    version = client.get(version_key)
    if version is not None:
        return str(version)
    if client.setnx(version_key, "1"):
        return "1"
    version = client.get(version_key)
    return str(version) if version is not None else "1"


def _build_cache_key(resource: str, version: str) -> str:
    return f"{_CACHE_NAMESPACE}:{resource}:v{version}"


def _fetch_with_cache(
    resource: str,
    version_key: str,
    fetcher: Callable[[], T],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> T:
    start = time.perf_counter()
    try:
        client = get_redis_client()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("procedure_cache_unavailable", resource=resource, exc_info=exc)
        CACHE_FETCH_LATENCY.labels(resource=resource, source="fallback").observe(
            time.perf_counter() - start
        )
        return fetcher()

    try:
        version = _ensure_version_key(version_key)
        cache_key = _build_cache_key(resource, version)
        cached = client.get(cache_key)
    except RedisError as exc:
        logger.warning("procedure_cache_error", resource=resource, error=str(exc))
        CACHE_FETCH_LATENCY.labels(resource=resource, source="fallback").observe(
            time.perf_counter() - start
        )
        return fetcher()

    if cached is not None:
        CACHE_HITS.labels(resource=resource).inc()
        CACHE_FETCH_LATENCY.labels(resource=resource, source="cache").observe(
            time.perf_counter() - start
        )
        logger.debug(
            "procedure_cache_hit",
            resource=resource,
            cache_key=cache_key,
            version=version,
        )
        return _load_json(cached)  # type: ignore[return-value]

    CACHE_MISSES.labels(resource=resource).inc()
    data = fetcher()
    duration = time.perf_counter() - start
    CACHE_FETCH_LATENCY.labels(resource=resource, source="origin").observe(duration)
    logger.debug(
        "procedure_cache_miss",
        resource=resource,
        cache_key=cache_key,
        version=version,
        duration=duration,
    )

    try:
        client.set(cache_key, _dump_json(data), ex=ttl_seconds)
        CACHE_STORE.labels(resource=resource).inc()
    except RedisError as exc:
        logger.warning("procedure_cache_store_failed", resource=resource, error=str(exc))

    return data


def _bump_version(version_key: str, resource: str) -> None:
    try:
        client = get_redis_client()
        client.incr(version_key)
        CACHE_INVALIDATIONS.labels(resource=resource).inc()
        logger.info("procedure_cache_invalidated", resource=resource, version_key=version_key)
    except Exception as exc:  # pragma: no cover - defensive invalidation path
        logger.warning(
            "procedure_cache_invalidation_failed",
            resource=resource,
            version_key=version_key,
            exc_info=exc,
        )


def cached_procedure_list(fetcher: Callable[[], T], ttl_seconds: int = DEFAULT_TTL_SECONDS) -> T:
    """Return the cached list of procedures or refresh it via ``fetcher``."""

    return _fetch_with_cache(
        resource="list",
        version_key=_PROCEDURE_LIST_VERSION_KEY,
        fetcher=fetcher,
        ttl_seconds=ttl_seconds,
    )


def cached_procedure_detail(
    procedure_id: str, fetcher: Callable[[], T], ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> T:
    """Return cached details for a specific procedure, keyed by its version."""

    version_key = _PROCEDURE_VERSION_TEMPLATE % procedure_id
    resource = f"procedure:{procedure_id}"
    return _fetch_with_cache(resource, version_key, fetcher, ttl_seconds=ttl_seconds)


def cached_run_detail(run_id: str, fetcher: Callable[[], T], ttl_seconds: int = DEFAULT_TTL_SECONDS) -> T:
    """Return cached details for a specific run, keyed by its version."""

    version_key = _RUN_VERSION_TEMPLATE % run_id
    resource = f"run:{run_id}"
    return _fetch_with_cache(resource, version_key, fetcher, ttl_seconds=ttl_seconds)


def invalidate_procedure_list() -> None:
    """Invalidate the cached list of procedures."""

    _bump_version(_PROCEDURE_LIST_VERSION_KEY, "list")


def invalidate_procedure_cache(procedure_id: str) -> None:
    """Invalidate entries dependent on a procedure (list + detail)."""

    _bump_version(_PROCEDURE_LIST_VERSION_KEY, "list")
    _bump_version(_PROCEDURE_VERSION_TEMPLATE % procedure_id, f"procedure:{procedure_id}")


def invalidate_run_cache(run_id: str) -> None:
    """Invalidate the cached details of a procedure run."""

    _bump_version(_RUN_VERSION_TEMPLATE % run_id, f"run:{run_id}")


__all__ = [
    "cached_procedure_list",
    "cached_procedure_detail",
    "cached_run_detail",
    "invalidate_procedure_cache",
    "invalidate_procedure_list",
    "invalidate_run_cache",
]
