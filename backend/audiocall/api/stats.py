"""Dashboard overview stats endpoint, mounted under /api/stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from audiocall.api.auth import require_user
from audiocall.api.schemas import StatsOverviewOut
from audiocall.services import stats_service
from audiocall.services.team_service import UserContext

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverviewOut)
async def stats_overview(user: UserContext = Depends(require_user)) -> StatsOverviewOut:
    return StatsOverviewOut(**await stats_service.get_overview(user.org_id))
