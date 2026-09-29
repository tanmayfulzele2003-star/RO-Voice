"""Async database engine and session factory.

Connects to whatever Postgres instance `DATABASE_URL` points at — a managed
instance (Neon/Render Postgres) in every environment, dev included. There is
no local Docker Postgres.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at your managed Postgres instance, "
            "e.g. postgresql+asyncpg://user:password@host:5432/dbname"
        )
    return create_async_engine(database_url, pool_pre_ping=True)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a request-scoped session."""
    async with get_session_factory()() as session:
        yield session


async def check_connectivity() -> None:
    """Raise immediately if the database is unreachable. Call at app startup."""
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
