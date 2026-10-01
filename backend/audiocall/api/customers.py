"""Customer CRUD REST endpoints, mounted under /api/customers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from audiocall.api.auth import require_admin
from audiocall.api.schemas import CustomerCreate, CustomerOut, CustomerUpdate, Paginated
from audiocall.services import customers_service, profiles_service

router = APIRouter(
    prefix="/api/customers", tags=["customers"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=Paginated[CustomerOut])
async def list_customers(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Paginated[CustomerOut]:
    customers, total = await customers_service.list_customers(limit=limit, offset=offset)
    return Paginated(
        items=[CustomerOut.model_validate(c) for c in customers],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _check_profile(profile_id: uuid.UUID | None) -> None:
    if profile_id is not None and await profiles_service.get_profile(profile_id) is None:
        raise HTTPException(status_code=422, detail="Business profile not found")


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(payload: CustomerCreate) -> CustomerOut:
    await _check_profile(payload.profile_id)
    customer = await customers_service.create_customer(payload.model_dump())
    return CustomerOut.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(customer_id: uuid.UUID, payload: CustomerUpdate) -> CustomerOut:
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is None:
        data.pop("name", None)  # required columns can't be cleared
    if data.get("phone") is None:
        data.pop("phone", None)
    await _check_profile(data.get("profile_id"))
    customer = await customers_service.update_customer(customer_id, data)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerOut.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: uuid.UUID) -> CustomerOut:
    customer = await customers_service.get_customer(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerOut.model_validate(customer)
