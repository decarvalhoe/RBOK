from __future__ import annotations

from typing import Any, Callable, Dict, List

import pytest

from app.services.procedures import cache as cache_module


class FakeRedisClient:
    def __init__(self) -> None:
        self._storage: Dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._storage.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._storage[key] = value
        return True

    def setnx(self, key: str, value: str) -> bool:
        if key in self._storage:
            return False
        self._storage[key] = value
        return True

    def incr(self, key: str) -> int:
        value = int(self._storage.get(key, "0")) + 1
        self._storage[key] = str(value)
        return value


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedisClient:
    client = FakeRedisClient()
    monkeypatch.setattr(cache_module, "get_redis_client", lambda: client)
    return client


def _counter_value(counter: Callable[..., Any], **labels: Any) -> float:
    return counter(**labels)._value.get()


def test_cached_procedure_list_records_hits_and_misses(fake_redis: FakeRedisClient) -> None:
    fetch_calls = {"count": 0}

    def fetcher() -> List[Dict[str, str]]:
        fetch_calls["count"] += 1
        return [{"id": "proc-1"}]

    hits_before = _counter_value(cache_module.CACHE_HITS.labels, resource="list")
    misses_before = _counter_value(cache_module.CACHE_MISSES.labels, resource="list")

    first = cache_module.cached_procedure_list(fetcher)
    second = cache_module.cached_procedure_list(fetcher)

    assert fetch_calls["count"] == 1
    assert first == second

    assert (
        _counter_value(cache_module.CACHE_MISSES.labels, resource="list")
        == misses_before + 1
    )
    assert (
        _counter_value(cache_module.CACHE_HITS.labels, resource="list")
        == hits_before + 1
    )


def test_cached_procedure_detail_records_hits_and_misses(fake_redis: FakeRedisClient) -> None:
    fetch_calls = {"count": 0}

    def fetcher() -> Dict[str, str]:
        fetch_calls["count"] += 1
        return {"id": "proc-1"}

    resource_labels = {"resource": "procedure:proc-1"}
    hits_before = _counter_value(cache_module.CACHE_HITS.labels, **resource_labels)
    misses_before = _counter_value(cache_module.CACHE_MISSES.labels, **resource_labels)

    first = cache_module.cached_procedure_detail("proc-1", fetcher)
    second = cache_module.cached_procedure_detail("proc-1", fetcher)

    assert fetch_calls["count"] == 1
    assert first == second

    assert (
        _counter_value(cache_module.CACHE_MISSES.labels, **resource_labels)
        == misses_before + 1
    )
    assert (
        _counter_value(cache_module.CACHE_HITS.labels, **resource_labels)
        == hits_before + 1
    )


def test_cached_run_detail_records_hits_and_misses(fake_redis: FakeRedisClient) -> None:
    fetch_calls = {"count": 0}

    def fetcher() -> Dict[str, str]:
        fetch_calls["count"] += 1
        return {"id": "run-1"}

    resource_labels = {"resource": "run:run-1"}
    hits_before = _counter_value(cache_module.CACHE_HITS.labels, **resource_labels)
    misses_before = _counter_value(cache_module.CACHE_MISSES.labels, **resource_labels)

    first = cache_module.cached_run_detail("run-1", fetcher)
    second = cache_module.cached_run_detail("run-1", fetcher)

    assert fetch_calls["count"] == 1
    assert first == second

    assert (
        _counter_value(cache_module.CACHE_MISSES.labels, **resource_labels)
        == misses_before + 1
    )
    assert (
        _counter_value(cache_module.CACHE_HITS.labels, **resource_labels)
        == hits_before + 1
    )
