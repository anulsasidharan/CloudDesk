"""Database stub for Phase 1. The async engine and sessions arrive in Phase 2."""

from app.core.config import get_settings


def database_configured() -> bool:
    """True when ``DATABASE_URL`` is set. Performs no I/O."""
    return bool(get_settings().database_url.strip())
