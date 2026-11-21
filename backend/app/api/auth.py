"""``/auth`` routes. Demo login exists only while ``DEMO_MODE=true``."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import AuthUser, SecretNotConfiguredError, get_current_user
from app.repositories.people import ProfileRepository
from app.schemas.auth import DemoLoginRequest, TokenResponse, User
from app.schemas.common import Role
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(
    body: DemoLoginRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    if not get_settings().demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    body = body or DemoLoginRequest()
    try:
        return await auth_service.demo_login(session, email=body.email, role=body.role)
    except auth_service.UnknownDemoUserError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo user") from exc
    except SecretNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth is not configured") from exc


@router.get("/me", response_model=User)
async def me(
    caller: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    profile = await ProfileRepository(session).get(caller.id)
    if profile is None:
        # Valid token for a user that is not in our table (e.g. a Supabase user): trust the token.
        return User(id=caller.id, email=caller.email, full_name=caller.email, role=Role(caller.role))
    return auth_service.to_user(profile)
