"""One-shot, idempotent schema convergence for the Helm migrations Job.

The durable Vexa schema is owned by ``admin_api.schema``.  This module exposes
that same convergence path without starting the HTTP server, so an operator can
run it as a short-lived Job before a rollout.
"""
from __future__ import annotations

import asyncio

from .__main__ import _connect_with_retry, _database_url
from .app import db as app_db
from .schema.models import Base
from .schema.sync import ensure_schema


async def run_schema_sync() -> None:
    """Converge the admin-owned schema once, then release the DB engine."""
    app_db.configure(_database_url(), pool_size=1, max_overflow=0)
    engine = app_db.get_engine()
    try:
        await _connect_with_retry(lambda: ensure_schema(engine, Base))
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_schema_sync())


if __name__ == "__main__":
    main()
