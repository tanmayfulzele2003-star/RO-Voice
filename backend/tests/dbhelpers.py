"""Helpers for the Postgres-backed tests: each test works inside its own
throwaway organization, which is deleted (with everything in it) afterwards."""

import uuid

from sqlalchemy import text

from audiocall.db import session as db_session
from audiocall.services import team_service

_CALL_CHILDREN = ("call_events", "conversation_messages", "requirements", "call_summaries")


async def make_org(name: str | None = None, **extra):
    return await team_service.create_org(name or f"Test org {uuid.uuid4().hex[:6]}", **extra)


async def delete_orgs(org_ids) -> None:
    ids = [str(i) for i in org_ids]
    if not ids:
        return
    async with db_session.get_engine().begin() as conn:
        calls = "SELECT id FROM calls WHERE org_id = ANY(CAST(:ids AS uuid[]))"
        for table in _CALL_CHILDREN:
            await conn.execute(text(f"DELETE FROM {table} WHERE call_id IN ({calls})"), {"ids": ids})
        await conn.execute(text("DELETE FROM app_settings WHERE scope = ANY(:ids)"), {"ids": ids})
        # Cascades to profiles, customers, calls, numbers, campaigns, users, invites.
        await conn.execute(text("DELETE FROM organizations WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids})
