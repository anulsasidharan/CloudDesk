"""``/approvals`` routes. HTTP, auth and RBAC only; ``approval_service`` does the work.

A ``viewer`` may read approvals but receives 403 on approve and reject (CLAUDE.md 18.1).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import AuthUser, require_role
from app.schemas.approvals import ApprovalOut, DecisionRequest, DecisionResult
from app.schemas.common import ApprovalStatus, Role
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])
VIEWER = Depends(require_role(Role.VIEWER))
AGENT = Depends(require_role(Role.AGENT))
STATUS_QUERY = Query(None, alias="status")


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found")


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status_: ApprovalStatus | None = STATUS_QUERY,
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> list[ApprovalOut]:
    return await approval_service.list_approvals(session, status_)


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: str,
    _: AuthUser = VIEWER,
    session: AsyncSession = Depends(get_session),
) -> ApprovalOut:
    try:
        return await approval_service.get_approval(session, approval_id)
    except approval_service.ApprovalNotFoundError as exc:
        raise _not_found() from exc


async def _decide(
    approval_id: str,
    body: DecisionRequest,
    caller: AuthUser,
    session: AsyncSession,
    *,
    approved: bool,
) -> DecisionResult:
    try:
        return await approval_service.decide(
            session, approval_id, approved=approved, note=body.note, caller=caller
        )
    except approval_service.ApprovalNotFoundError as exc:
        raise _not_found() from exc
    except approval_service.ApprovalConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{approval_id}/approve", response_model=DecisionResult)
async def approve(
    approval_id: str,
    body: DecisionRequest | None = None,
    caller: AuthUser = AGENT,
    session: AsyncSession = Depends(get_session),
) -> DecisionResult:
    return await _decide(approval_id, body or DecisionRequest(), caller, session, approved=True)


@router.post("/{approval_id}/reject", response_model=DecisionResult)
async def reject(
    approval_id: str,
    body: DecisionRequest | None = None,
    caller: AuthUser = AGENT,
    session: AsyncSession = Depends(get_session),
) -> DecisionResult:
    return await _decide(approval_id, body or DecisionRequest(), caller, session, approved=False)
