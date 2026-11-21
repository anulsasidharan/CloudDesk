"""``/customers`` routes (read-only). HTTP, auth and RBAC only."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import AuthUser, require_role
from app.schemas.common import Role
from app.schemas.customers import CustomerDetail, CustomerPage
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])
VIEWER = Depends(require_role(Role.VIEWER))


@router.get("", response_model=CustomerPage)
async def list_customers(
    search: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> CustomerPage:
    return await customer_service.list_customers(
        session, search=search, page=page, page_size=page_size
    )


@router.get("/{customer_id}", response_model=CustomerDetail)
async def get_customer(
    customer_id: str,
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> CustomerDetail:
    try:
        return await customer_service.get_customer(session, customer_id)
    except customer_service.CustomerNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found") from exc
