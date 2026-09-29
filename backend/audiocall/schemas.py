"""Pydantic models shared across services (not tied to the DB layer)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CallAnalysis(BaseModel):
    """Structured extraction + summary produced from a call transcript.

    Field-for-field contract for `summary_service.analyze_call`.
    """

    customer_name: str | None = None
    company_name: str | None = None
    requirement: str | None = None
    ro_capacity: str | None = None
    location: str | None = None
    budget: str | None = None
    timeline: str | None = None
    additional_requirements: str | None = None

    summary: str
    customer_intent: str
    key_requirements: list[str] = Field(default_factory=list)
    important_points: list[str] = Field(default_factory=list)
    lead_status: Literal["interested", "not_interested", "uncertain"]
    follow_up_required: bool
