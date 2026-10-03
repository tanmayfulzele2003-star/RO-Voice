"""Aggregates all /api/* routers for mounting into the main FastAPI app."""

from fastapi import APIRouter

from audiocall.api import (
    auth,
    calls,
    campaigns,
    customers,
    numbers,
    platform,
    profiles,
    settings,
    setup,
    stats,
    team,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(profiles.router)
api_router.include_router(calls.router)
api_router.include_router(numbers.router)
api_router.include_router(campaigns.router)
api_router.include_router(settings.router)
api_router.include_router(settings.platform_router)
api_router.include_router(platform.router)
api_router.include_router(team.router)
api_router.include_router(setup.router)
api_router.include_router(stats.router)
