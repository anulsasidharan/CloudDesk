"""Demo login: pick one of the seeded profiles and sign an 8-hour token for it."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import DEMO_TOKEN_TTL, create_access_token
from app.models.entities import Profile
from app.repositories.people import ProfileRepository
from app.schemas.auth import TokenResponse, User
from app.schemas.common import Role

DEFAULT_DEMO_ROLE = Role.AGENT


class UnknownDemoUserError(LookupError):
    """No seeded profile matches the requested email or role."""


def to_user(profile: Profile) -> User:
    return User(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        role=Role(profile.role),
    )


async def demo_login(
    session: AsyncSession, *, email: str | None = None, role: Role | None = None
) -> TokenResponse:
    """Email wins over role; with neither, sign in as the demo agent."""
    profiles = ProfileRepository(session)
    if email:
        profile = await profiles.get_by_email(email)
    else:
        profile = await profiles.first_with_role((role or DEFAULT_DEMO_ROLE).value)
    if profile is None:
        raise UnknownDemoUserError(email or (role or DEFAULT_DEMO_ROLE).value)
    token = create_access_token(user_id=profile.id, email=profile.email, role=profile.role)
    return TokenResponse(
        access_token=token,
        expires_in=int(DEMO_TOKEN_TTL.total_seconds()),
        user=to_user(profile),
    )
