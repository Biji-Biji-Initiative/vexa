"""One-shot schema runner uses the same admin-owned convergence path as startup."""
from __future__ import annotations

import asyncio

import pytest
from conftest import requires_docker
from sqlalchemy import create_engine, inspect

from admin_api import schema_runner


class _Engine:
    def __init__(self):
        self.disposed = False

    async def dispose(self):
        self.disposed = True


def test_schema_runner_converges_admin_schema_and_disposes_engine(monkeypatch):
    engine = _Engine()
    seen = {}

    monkeypatch.setattr(schema_runner, "_database_url", lambda: "postgresql+asyncpg://test")
    monkeypatch.setattr(
        schema_runner.app_db,
        "configure",
        lambda url, **kwargs: seen.update(url=url, **kwargs),
    )
    monkeypatch.setattr(schema_runner.app_db, "get_engine", lambda: engine)

    async def converge(actual_engine, base):
        seen["converged"] = (actual_engine, base)

    async def without_backoff(connect):
        return await connect()

    monkeypatch.setattr(schema_runner, "ensure_schema", converge)
    monkeypatch.setattr(schema_runner, "_connect_with_retry", without_backoff)

    asyncio.run(schema_runner.run_schema_sync())

    assert seen["url"] == "postgresql+asyncpg://test"
    assert seen["pool_size"] == 1
    assert seen["max_overflow"] == 0
    assert seen["converged"] == (engine, schema_runner.Base)
    assert engine.disposed


def test_schema_runner_disposes_engine_when_convergence_fails(monkeypatch):
    engine = _Engine()
    monkeypatch.setattr(schema_runner, "_database_url", lambda: "postgresql+asyncpg://test")
    monkeypatch.setattr(schema_runner.app_db, "configure", lambda *args, **kwargs: None)
    monkeypatch.setattr(schema_runner.app_db, "get_engine", lambda: engine)

    async def fail_convergence(*_args):
        raise RuntimeError("schema convergence failed")

    async def without_backoff(connect):
        return await connect()

    monkeypatch.setattr(schema_runner, "ensure_schema", fail_convergence)
    monkeypatch.setattr(schema_runner, "_connect_with_retry", without_backoff)

    with pytest.raises(RuntimeError, match="schema convergence failed"):
        asyncio.run(schema_runner.run_schema_sync())

    assert engine.disposed


@requires_docker
def test_schema_runner_converges_an_empty_postgres(pg_async_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_async_url)

    asyncio.run(schema_runner.run_schema_sync())

    sync_url = pg_async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {"users", "api_tokens", "meetings", "transcriptions", "meeting_sessions"} <= tables
