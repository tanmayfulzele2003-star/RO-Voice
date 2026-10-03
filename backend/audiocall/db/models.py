"""SQLAlchemy 2.0 declarative models for the RO sales voice-agent platform.

Schema:
    business_profiles -> phone_numbers -> calls
    campaigns -> campaign_contacts -> customers
    business_profiles -> customers -> calls -> conversation_messages
                                            -> call_events
                                            -> requirements (1:1)
                                            -> call_summaries (1:1)

A business profile configures the agent for one business: its persona, what
it sells, the call objective, and the list of fields to collect. Every call
snapshots the profile it ran with (`calls.profile_id`), so the dashboard can
render that call's requirements with the right labels even if the customer is
later moved to a different profile.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


ROLES = ("viewer", "member", "admin", "owner")


class Organization(Base):
    """A company using the platform. Everything a business works with —
    profiles, customers, calls, numbers, campaigns, users — belongs to exactly
    one organization, and every dashboard query is filtered by it."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Phone calls this company may run at once (plan limit). NULL = only the
    # server-wide MAX_CONCURRENT_CALLS applies.
    max_concurrent_calls: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    __table_args__ = (
        # At most one default profile per organization.
        Index(
            "uq_business_profiles_one_default",
            "org_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)  # business name
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)  # what the business does
    products: Mapped[str | None] = mapped_column(Text)  # catalogue / offerings, free text
    call_objective: Mapped[str] = mapped_column(Text, nullable=False)
    greeting: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)  # None = mirror the customer
    # [{"key": "ro_capacity", "label": "RO Capacity", "description": "...",
    #   "required": true}, ...] — the agent's checklist for the call.
    fields: Mapped[list] = mapped_column(JSONB, nullable=False)
    # E.164 number of a real person the agent can hand the call to (phone
    # calls only). NULL = no transfer; the agent offers a callback instead.
    transfer_number: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)  # E.164
    company: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)  # e.g. "Product enquiry"
    product: Mapped[str | None] = mapped_column(Text)  # e.g. "Commercial RO System"
    # NULL = use the default business profile.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    calls: Mapped[list["Call"]] = relationship(back_populates="customer")
    profile: Mapped["BusinessProfile | None"] = relationship()


class PhoneNumber(Base):
    """A Twilio number the account owns. Outbound calls take their caller ID
    from this pool; inbound calls are routed by the number that was dialled."""

    __tablename__ = "phone_numbers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # E.164
    label: Mapped[str | None] = mapped_column(Text)
    # NULL = shared pool, usable by any profile.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="SET NULL"), index=True
    )
    inbound_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    outbound_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Round-robin: the least recently used number places the next call.
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    profile: Mapped["BusinessProfile | None"] = relationship()


class Campaign(Base):
    """A batch of outbound calls dialled by the background dialer (dialer.py)."""

    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL = each customer's own profile.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft", index=True
    )  # draft|running|paused|completed|cancelled
    # Why the dialer paused it on its own (e.g. Twilio credentials rejected).
    status_reason: Mapped[str | None] = mapped_column(Text)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    retry_delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    contacts: Mapped[list["CampaignContact"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignContact(Base):
    __tablename__ = "campaign_contacts"
    __table_args__ = (
        UniqueConstraint("campaign_id", "customer_id", name="uq_campaign_contacts_customer"),
        Index("ix_campaign_contacts_campaign_status", "campaign_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )  # pending|dialing|completed|failed|cancelled
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calls.id", ondelete="SET NULL")
    )
    last_outcome: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="contacts")
    customer: Mapped["Customer"] = relationship()


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        {"comment": "One row per phone call (outbound or inbound)."},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="SET NULL"), index=True
    )
    twilio_call_sid: Mapped[str | None] = mapped_column(Text, unique=True)
    direction: Mapped[str | None] = mapped_column(Text)  # outbound | inbound
    channel: Mapped[str] = mapped_column(
        Text, nullable=False, default="phone", server_default="phone"
    )  # phone (Twilio) | browser (WebRTC demo mode)
    status: Mapped[str | None] = mapped_column(
        Text, index=True
    )  # queued|ringing|in_progress|completed|failed|no_answer|disconnected
    start_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    error_reason: Mapped[str | None] = mapped_column(Text)
    # Telephony legs: our number and the customer's, whichever way the call went.
    from_number: Mapped[str | None] = mapped_column(Text)
    to_number: Mapped[str | None] = mapped_column(Text)
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("phone_numbers.id", ondelete="SET NULL"), index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    # Set when the agent handed the call to a person.
    transferred_to: Mapped[str | None] = mapped_column(Text)
    # Business result of the call, derived from status + AI analysis — see
    # services/outcome.py for the vocabulary.
    outcome: Mapped[str | None] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    customer: Mapped["Customer"] = relationship(back_populates="calls")
    profile: Mapped["BusinessProfile | None"] = relationship()
    events: Mapped[list["CallEvent"]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="CallEvent.created_at",
    )
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.timestamp",
    )
    requirements: Mapped["Requirement | None"] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    summary: Mapped["CallSummary | None"] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id"), nullable=False, index=True
    )
    speaker: Mapped[str] = mapped_column(Text, nullable=False)  # customer | ai
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    call: Mapped["Call"] = relationship(back_populates="messages")


class CallEvent(Base):
    """Notable things that happened during a call — errors, silences,
    interruptions, agent tool actions — so they're auditable afterwards."""

    __tablename__ = "call_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    call: Mapped["Call"] = relationship(back_populates="events")


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id"), nullable=False, unique=True
    )
    customer_name: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    requirement: Mapped[str | None] = mapped_column(Text)
    ro_capacity: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    budget: Mapped[str | None] = mapped_column(Text)
    timeline: Mapped[str | None] = mapped_column(Text)
    additional_requirements: Mapped[str | None] = mapped_column(Text)
    # Every collected field keyed by the profile's field key — the generic
    # store that works for any business profile. The fixed columns above are
    # also filled when a key matches, for the default RO profile.
    fields: Mapped[dict | None] = mapped_column(JSONB)

    call: Mapped["Call"] = relationship(back_populates="requirements")


class CallSummary(Base):
    __tablename__ = "call_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calls.id"), nullable=False, unique=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    customer_intent: Mapped[str | None] = mapped_column(Text)
    key_requirements: Mapped[dict | None] = mapped_column(JSONB)
    important_points: Mapped[dict | None] = mapped_column(JSONB)
    follow_up: Mapped[bool | None] = mapped_column(Boolean)
    follow_up_notes: Mapped[str | None] = mapped_column(Text)
    call_outcome: Mapped[str | None] = mapped_column(Text)  # one-sentence AI description
    lead_status: Mapped[str | None] = mapped_column(Text)  # interested | not_interested | uncertain
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    call: Mapped["Call"] = relationship(back_populates="summary")


class AppSetting(Base):
    """A setting saved from the dashboard. `scope` is "platform" (Gemini key,
    public URL, fallback Twilio account) or an organization id (that company's
    own Twilio account, setup progress). Overrides the environment; secrets
    are stored encrypted. See services/settings_service.py."""

    __tablename__ = "app_settings"

    scope: Mapped[str] = mapped_column(Text, primary_key=True, default="platform")
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, default="owner")  # see ROLES
    # Runs the platform itself: creates companies, sets the Gemini key and
    # public URL. Independent of the role inside their own company.
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship()


class Invite(Base):
    """A single-use link to join an organization with a role. Only a hash of
    the token is stored; the link itself is shown once, when created."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    note: Mapped[str | None] = mapped_column(Text)  # who it's for, e.g. an email
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
