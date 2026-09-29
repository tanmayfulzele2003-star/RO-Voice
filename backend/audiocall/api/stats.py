"""Dashboard overview stats endpoint, mounted under /api/stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from audiocall.api.auth import require_admin
from audiocall.api.schemas import StatsOverviewOut
from audiocall.services import stats_service

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(require_admin)])


@router.get("/overview", response_model=StatsOverviewOut)
async def stats_overview() -> StatsOverviewOut:
    data = await stats_service.get_overview()
    return StatsOverviewOut(**data)
