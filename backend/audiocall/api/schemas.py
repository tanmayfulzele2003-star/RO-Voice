"""Pydantic request/response models for the dashboard REST API (`/api/*`)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from audiocall.phone import is_valid_e164, normalize_phone
from audiocall.profiles import is_valid_field_key, slugify_field_key

T = TypeVar("T")

_PHONE_HELP = "Use E.164 format: + country code + number, e.g. +919876543210"


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    phone = normalize_phone(value)
    if not is_valid_e164(phone):
        raise ValueError(f"Invalid phone number. {_PHONE_HELP}")
    return phone


def _validate_optional_phone(value: str | None) -> str | None:
    """Like _validate_phone, but a blank value clears the field."""
    if value is None or not value.strip():
        return None
    return _validate_phone(value)


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ── Business profiles ────────────────────────────────────────────────────────
class ProfileField(BaseModel):
    key: str = Field(default="", max_length=50)
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    required: bool = True

    @model_validator(mode="after")
    def _key_from_label(self) -> "ProfileField":
        self.key = (self.key or "").strip() or slugify_field_key(self.label)
        if not is_valid_field_key(self.key):
            raise ValueError(
                f"Invalid field key '{self.key}': use lowercase letters, digits and underscores"
            )
        return self


def _check_fields(fields: list[ProfileField] | None) -> list[ProfileField] | None:
    if fields is None:
        return None
    if not fields:
        raise ValueError("A profile needs at least one field to collect")
    keys = [f.key for f in fields]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValueError(f"Duplicate field keys: {', '.join(duplicates)}")
    return fields


class ProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Business name")
    agent_name: str = Field(min_length=1, max_length=100)
    industry: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    products: str | None = Field(default=None, max_length=4000)
    call_objective: str = Field(min_length=1, max_length=2000)
    greeting: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=50)
    fields: list[ProfileField] = Field(min_length=1, max_length=30)
    transfer_number: str | None = Field(
        default=None, max_length=32, description=f"Human hand-off number. {_PHONE_HELP}"
    )
    is_default: bool = False

    _validate_fields = field_validator("fields")(_check_fields)
    _transfer = field_validator("transfer_number")(_validate_optional_phone)


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    agent_name: str | None = Field(default=None, min_length=1, max_length=100)
    industry: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    products: str | None = Field(default=None, max_length=4000)
    call_objective: str | None = Field(default=None, min_length=1, max_length=2000)
    greeting: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=50)
    fields: list[ProfileField] | None = Field(default=None, min_length=1, max_length=30)
    transfer_number: str | None = Field(default=None, max_length=32)
    is_default: bool | None = None

    _validate_fields = field_validator("fields")(_check_fields)
    _transfer = field_validator("transfer_number")(_validate_optional_phone)


class ProfileOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    agent_name: str
    industry: str | None
    description: str | None
    products: str | None
    call_objective: str
    greeting: str | None
    language: str | None
    fields: list[ProfileField]
    transfer_number: str | None
    is_default: bool
    created_at: datetime


# ── Customers ────────────────────────────────────────────────────────────────
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=32, description=_PHONE_HELP)
    company: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=200)
    product: str | None = Field(default=None, max_length=200)
    profile_id: uuid.UUID | None = None

    _phone = field_validator("phone")(_validate_phone)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=1, max_length=32, description=_PHONE_HELP)
    company: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=200)
    product: str | None = Field(default=None, max_length=200)
    profile_id: uuid.UUID | None = None

    _phone = field_validator("phone")(_validate_phone)


class CustomerOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    phone: str
    company: str | None
    purpose: str | None
    product: str | None
    profile_id: uuid.UUID | None
    created_at: datetime


# ── Calls ────────────────────────────────────────────────────────────────────
class CallStartRequest(BaseModel):
    customer_id: uuid.UUID


class CallStartResponse(BaseModel):
    call_id: uuid.UUID
    call_sid: str | None
    status: str


class BrowserCallStartResponse(BaseModel):
    call_id: uuid.UUID
    token: str = Field(description="Short-lived token for /browser-stream")
    stream_url: str = Field(description="WebSocket URL to open from the browser")


class CallListItem(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    customer_phone: str
    profile_name: str | None
    direction: str
    channel: str
    from_number: str | None
    to_number: str | None
    campaign_id: uuid.UUID | None
    transferred_to: str | None
    status: str
    outcome: str | None
    lead_status: str | None
    follow_up: bool | None
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
    fields: dict[str, str] | None


class CallEventOut(BaseModel):
    model_config = {"from_attributes": True}

    event_type: str
    detail: str | None
    created_at: datetime


class CallSummaryOut(BaseModel):
    model_config = {"from_attributes": True}

    summary: str | None
    customer_intent: str | None
    key_requirements: list[str] | None
    important_points: list[str] | None
    follow_up: bool | None
    follow_up_notes: str | None
    call_outcome: str | None
    lead_status: str | None


class CallDetailOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    customer_phone: str
    customer_company: str | None
    customer_purpose: str | None
    customer_product: str | None
    profile_id: uuid.UUID | None
    profile_name: str | None
    profile_fields: list[ProfileField]
    twilio_call_sid: str | None
    direction: str
    channel: str
    from_number: str | None
    to_number: str | None
    campaign_id: uuid.UUID | None
    transferred_to: str | None
    status: str
    outcome: str | None
    start_time: datetime | None
    end_time: datetime | None
    duration_seconds: int | None
    error_reason: str | None
    created_at: datetime
    messages: list[ConversationMessageOut]
    events: list[CallEventOut]
    requirements: RequirementsOut | None
    summary: CallSummaryOut | None


# ── Phone numbers ────────────────────────────────────────────────────────────
class PhoneNumberCreate(BaseModel):
    number: str = Field(min_length=1, max_length=32, description=_PHONE_HELP)
    label: str | None = Field(default=None, max_length=100)
    profile_id: uuid.UUID | None = Field(default=None, description="null = shared pool")
    inbound_enabled: bool = True
    outbound_enabled: bool = True
    is_active: bool = True

    _phone = field_validator("number")(_validate_phone)


class PhoneNumberUpdate(BaseModel):
    number: str | None = Field(default=None, min_length=1, max_length=32)
    label: str | None = Field(default=None, max_length=100)
    profile_id: uuid.UUID | None = None
    inbound_enabled: bool | None = None
    outbound_enabled: bool | None = None
    is_active: bool | None = None

    _phone = field_validator("number")(_validate_phone)


class PhoneNumberOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    number: str
    label: str | None
    profile_id: uuid.UUID | None
    inbound_enabled: bool
    outbound_enabled: bool
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


# ── Campaigns ────────────────────────────────────────────────────────────────
class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    profile_id: uuid.UUID | None = Field(
        default=None, description="null = each customer's own profile"
    )
    customer_ids: list[uuid.UUID] = Field(min_length=1, max_length=5000)
    max_concurrent: int = Field(default=3, ge=1, le=50)
    max_attempts: int = Field(default=2, ge=1, le=5)
    retry_delay_minutes: int = Field(default=30, ge=1, le=1440)


class CampaignCounts(BaseModel):
    pending: int = 0
    dialing: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    total: int = 0


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    profile_id: uuid.UUID | None
    status: str
    max_concurrent: int
    max_attempts: int
    retry_delay_minutes: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    counts: CampaignCounts


class CampaignContactOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    customer_phone: str
    status: str
    attempts: int
    last_call_id: uuid.UUID | None
    last_outcome: str | None
    next_attempt_at: datetime | None


class CampaignDetailOut(CampaignOut):
    contacts: list[CampaignContactOut]


# ── Stats ────────────────────────────────────────────────────────────────────
class StatsOverviewOut(BaseModel):
    total_calls: int
    completed_calls: int
    failed_calls: int
    interested_leads: int
    follow_ups_required: int
    avg_duration_seconds: float | None
