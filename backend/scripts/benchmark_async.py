"""Simple load test to highlight async throughput gains."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from statistics import mean
from typing import List

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure the async driver is used for benchmarks before importing the app
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./benchmark.db")

from app.database import Base, engine  # noqa: E402  (import after DATABASE_URL)
from app.main import app  # noqa: E402


async def prepare_database() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def get_token(client: httpx.AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def create_procedure(client: httpx.AsyncClient, token: str) -> str:
    payload = {
        "name": "Benchmark Procedure",
        "description": "Procedure used for async benchmark runs",
        "steps": [],
    }
    response = await client.post(
        "/procedures",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.json()["id"]


async def run_once(client: httpx.AsyncClient, token: str, procedure_id: str) -> None:
    response = await client.post(
        "/runs",
        json={"procedure_id": procedure_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()


async def sequential_benchmark(
    client: httpx.AsyncClient,
    token: str,
    procedure_id: str,
    iterations: int,
) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        await run_once(client, token, procedure_id)
    return time.perf_counter() - start


async def concurrent_benchmark(
    client: httpx.AsyncClient,
    token: str,
    procedure_id: str,
    requests: int,
    concurrency: int,
) -> float:
    sem = asyncio.Semaphore(concurrency)

    async def worker() -> None:
        async with sem:
            await run_once(client, token, procedure_id)

    start = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(requests)))
    return time.perf_counter() - start


def summarize(label: str, total_requests: int, duration: float) -> str:
    rps = total_requests / duration if duration else float("inf")
    return f"{label}: {total_requests} requests in {duration:.2f}s ({rps:.1f} req/s)"


async def main() -> None:
    await prepare_database()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        admin_token = await get_token(client, "alice", "adminpass")
        user_token = await get_token(client, "bob", "userpass")
        procedure_id = await create_procedure(client, admin_token)

        sequential_durations: List[float] = []
        concurrent_durations: List[float] = []

        # Warm-up request to populate connection pool
        await run_once(client, user_token, procedure_id)

        for _ in range(3):
            sequential_durations.append(
                await sequential_benchmark(client, user_token, procedure_id, iterations=25)
            )
            concurrent_durations.append(
                await concurrent_benchmark(
                    client,
                    user_token,
                    procedure_id,
                    requests=75,
                    concurrency=15,
                )
            )

    seq_avg = mean(sequential_durations)
    conc_avg = mean(concurrent_durations)

    print("Async session benchmark results")
    print(summarize("Sequential", 25, seq_avg))
    print(summarize("Concurrent", 75, conc_avg))


if __name__ == "__main__":
    asyncio.run(main())
