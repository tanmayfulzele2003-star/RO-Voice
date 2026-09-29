"""Aggregate stats for the dashboard overview page.

Computed as a single query with conditional aggregates (not multiple
round-trips, and not pulled into Python and summed) — one LEFT JOIN between
`calls` and `call_summaries`, one query, six aggregate expressions.
"""

from __future__ import annotations

from sqlalchemy import case, func, select

from audiocall.db.models import Call, CallSummary
from audiocall.db.session import get_session_factory


async def get_overview() -> dict:
    query = (
        select(
            func.count(Call.id).label("total_calls"),
            func.sum(case((Call.status == "completed", 1), else_=0)).label("completed_calls"),
            func.sum(case((Call.status == "failed", 1), else_=0)).label("failed_calls"),
            func.sum(
                case((CallSummary.lead_status == "interested", 1), else_=0)
            ).label("interested_leads"),
            func.sum(case((CallSummary.follow_up.is_(True), 1), else_=0)).label(
                "follow_ups_required"
            ),
            func.avg(Call.duration_seconds).label("avg_duration_seconds"),
        )
        .select_from(Call)
        .outerjoin(CallSummary, CallSummary.call_id == Call.id)
    )

    async with get_session_factory()() as session:
        row = (await session.execute(query)).one()

    return {
        "total_calls": row.total_calls or 0,
        "completed_calls": int(row.completed_calls or 0),
        "failed_calls": int(row.failed_calls or 0),
        "interested_leads": int(row.interested_leads or 0),
        "follow_ups_required": int(row.follow_ups_required or 0),
        "avg_duration_seconds": (
            float(row.avg_duration_seconds) if row.avg_duration_seconds is not None else None
        ),
    }
