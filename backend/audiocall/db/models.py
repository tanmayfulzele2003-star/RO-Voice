"""SQLAlchemy 2.0 declarative models for the RO sales voice-agent platform.

Schema:
    customers -> calls -> conversation_messages
                       -> requirements (1:1)
                       -> call_summaries (1:1)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)  # E.164
    company: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    calls: Mapped[list["Call"]] = relationship(back_populates="customer")


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        {"comment": "One row per phone call (outbound or inbound)."},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id"), nullable=False, index=True
    )
    twilio_call_sid: Mapped[str | None] = mapped_column(Text, unique=True)
    direction: Mapped[str | None] = mapped_column(Text)  # outbound | inbound
    status: Mapped[str | None] = mapped_column(
        Text, index=True
    )  # queued|ringing|in_progress|completed|failed|no_answer|disconnected
    start_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    error_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    customer: Mapped["Customer"] = relationship(back_populates="calls")
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
    lead_status: Mapped[str | None] = mapped_column(Text)  # interested | not_interested | uncertain
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    call: Mapped["Call"] = relationship(back_populates="summary")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
