"""Aggregates all /api/* routers for mounting into the main FastAPI app."""

from fastapi import APIRouter

from audiocall.api import auth, calls, customers, stats

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(calls.router)
api_router.include_router(stats.router)
