"""Pydantic request/response models for the dashboard REST API (`/api/*`)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ── Customers ────────────────────────────────────────────────────────────────
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=32)
    company: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    company: str | None = None


class CustomerOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    phone: str
    company: str | None
    created_at: datetime


# ── Calls ────────────────────────────────────────────────────────────────────
class CallStartRequest(BaseModel):
    customer_id: uuid.UUID


class CallStartResponse(BaseModel):
    call_id: uuid.UUID
    call_sid: str | None
    status: str


class CallListItem(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    direction: str
    status: str
    lead_status: str | None
    start_time: datetime | None
    end_time: datetime | None
    duration_seconds: int | None
    error_reason: str | None
    created_at: datetime


class ConversationMessageOut(BaseModel):
    model_config = {"from_attributes": True}

    speaker: str
    message: str
    timestamp: datetime | None


class RequirementsOut(BaseModel):
    model_config = {"from_attributes": True}

    customer_name: str | None
    company_name: str | None
    requirement: str | None
    ro_capacity: str | None
    location: str | None
    budget: str | None
    timeline: str | None
    additional_requirements: str | None


class CallSummaryOut(BaseModel):
    model_config = {"from_attributes": True}

    summary: str | None
    customer_intent: str | None
    key_requirements: list[str] | None
    important_points: list[str] | None
    follow_up: bool | None
    lead_status: str | None


class CallDetailOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    customer_phone: str
    twilio_call_sid: str | None
    direction: str
    status: str
    start_time: datetime | None
    end_time: datetime | None
    duration_seconds: int | None
    error_reason: str | None
    created_at: datetime
    messages: list[ConversationMessageOut]
    requirements: RequirementsOut | None
    summary: CallSummaryOut | None


# ── Stats ────────────────────────────────────────────────────────────────────
class StatsOverviewOut(BaseModel):
    total_calls: int
    completed_calls: int
    failed_calls: int
    interested_leads: int
    follow_ups_required: int
    avg_duration_seconds: float | None
