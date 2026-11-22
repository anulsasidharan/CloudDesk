"""Auth request and response shapes. Mirrors ``docs/API_CONTRACT.md`` (Auth)."""

from pydantic import BaseModel

from app.schemas.common import Role


class User(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role


class DemoLoginRequest(BaseModel):
    email: str | None = None
    role: Role | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User
