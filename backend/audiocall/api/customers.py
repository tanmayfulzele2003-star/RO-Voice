"""Customer CRUD REST endpoints, mounted under /api/customers.

Scoped to the signed-in user's organization. Viewers read; members and up
add and edit.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from audiocall.api.auth import require_role, require_user
from audiocall.api.schemas import CustomerCreate, CustomerOut, CustomerUpdate, Paginated
from audiocall.services import customers_service, profiles_service
from audiocall.services.team_service import UserContext

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=Paginated[CustomerOut])
async def list_customers(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserContext = Depends(require_user),
) -> Paginated[CustomerOut]:
    customers, total = await customers_service.list_customers(user.org_id, limit=limit, offset=offset)
    return Paginated(
        items=[CustomerOut.model_validate(c) for c in customers],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _check_profile(profile_id: uuid.UUID | None, org_id: uuid.UUID) -> None:
    if profile_id is not None and await profiles_service.get_profile(profile_id, org_id) is None:
        raise HTTPException(status_code=422, detail="Business profile not found")


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(
    payload: CustomerCreate, user: UserContext = Depends(require_role("member"))
) -> CustomerOut:
    await _check_profile(payload.profile_id, user.org_id)
    customer = await customers_service.create_customer(user.org_id, payload.model_dump())
    return CustomerOut.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    user: UserContext = Depends(require_role("member")),
) -> CustomerOut:
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is None:
        data.pop("name", None)  # required columns can't be cleared
    if data.get("phone") is None:
        data.pop("phone", None)
    await _check_profile(data.get("profile_id"), user.org_id)
    customer = await customers_service.update_customer(customer_id, user.org_id, data)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerOut.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: uuid.UUID, user: UserContext = Depends(require_user)
) -> CustomerOut:
    customer = await customers_service.get_customer(customer_id, user.org_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerOut.model_validate(customer)
