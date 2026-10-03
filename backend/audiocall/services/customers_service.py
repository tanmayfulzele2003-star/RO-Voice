"""DB-backed CRUD for `customers`, scoped to one organization."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from audiocall.db.models import Customer
from audiocall.db.session import get_session_factory


async def list_customers(
    org_id: uuid.UUID, limit: int = 20, offset: int = 0
) -> tuple[list[Customer], int]:
    in_org = Customer.org_id == org_id
    async with get_session_factory()() as session:
        total = await session.scalar(select(func.count()).select_from(Customer).where(in_org)) or 0
        result = await session.execute(
            select(Customer).where(in_org).order_by(Customer.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total


async def get_customer(customer_id: uuid.UUID, org_id: uuid.UUID) -> Customer | None:
    async with get_session_factory()() as session:
        customer = await session.get(Customer, customer_id)
        return customer if customer is not None and customer.org_id == org_id else None


async def create_customer(org_id: uuid.UUID, data: dict[str, Any]) -> Customer:
    async with get_session_factory()() as session:
        customer = Customer(org_id=org_id, **data)
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        return customer


async def update_customer(
    customer_id: uuid.UUID, org_id: uuid.UUID, data: dict[str, Any]
) -> Customer | None:
    """Apply only the fields present in `data` (PATCH semantics — an explicit
    null clears an optional field)."""
    async with get_session_factory()() as session:
        customer = await session.get(Customer, customer_id)
        if customer is None or customer.org_id != org_id:
            return None
        for key, value in data.items():
            setattr(customer, key, value)
        await session.commit()
        await session.refresh(customer)
        return customer
