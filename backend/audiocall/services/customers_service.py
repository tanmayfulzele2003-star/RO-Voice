"""DB-backed CRUD for `customers`, used by the dashboard API."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from audiocall.db.models import Customer
from audiocall.db.session import get_session_factory


async def list_customers(limit: int = 20, offset: int = 0) -> tuple[list[Customer], int]:
    async with get_session_factory()() as session:
        total = await session.scalar(select(func.count()).select_from(Customer)) or 0
        result = await session.execute(
            select(Customer).order_by(Customer.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total


async def get_customer(customer_id: uuid.UUID) -> Customer | None:
    async with get_session_factory()() as session:
        return await session.get(Customer, customer_id)


async def create_customer(name: str, phone: str, company: str | None = None) -> Customer:
    async with get_session_factory()() as session:
        customer = Customer(name=name, phone=phone, company=company)
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        return customer


async def update_customer(
    customer_id: uuid.UUID,
    name: str | None = None,
    phone: str | None = None,
    company: str | None = None,
) -> Customer | None:
    async with get_session_factory()() as session:
        customer = await session.get(Customer, customer_id)
        if customer is None:
            return None
        if name is not None:
            customer.name = name
        if phone is not None:
            customer.phone = phone
        if company is not None:
            customer.company = company
        await session.commit()
        await session.refresh(customer)
        return customer
