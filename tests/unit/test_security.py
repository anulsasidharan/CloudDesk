"""N1: JWT issue/verify and the role ladder."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.config import get_settings
from app.core.security import (
    ALGORITHM,
    AUDIENCE,
    ROLE_LEVEL,
    TokenError,
    bearer_token,
    create_access_token,
    decode_token,
)


def _token(role="agent", **kwargs):
    return create_access_token(user_id="u1", email="Sam@Example.com", role=role, **kwargs)


def test_round_trip_keeps_identity_and_role():
    user = decode_token(_token("agent"))
    assert (user.id, user.email, user.role) == ("u1", "sam@example.com", "agent")


def test_role_ladder_is_viewer_agent_admin():
    assert ROLE_LEVEL == {"viewer": 1, "agent": 2, "admin": 3}
    viewer, agent, admin = (decode_token(_token(r)) for r in ("viewer", "agent", "admin"))
    assert viewer.has_role("viewer") and not viewer.has_role("agent")
    assert agent.has_role("viewer") and agent.has_role("agent") and not agent.has_role("admin")
    assert admin.has_role("admin")


def test_unknown_role_cannot_be_issued():
    with pytest.raises(ValueError):
        _token("superuser")


def test_expired_token_is_rejected():
    old = datetime.now(UTC) - timedelta(hours=9)
    with pytest.raises(TokenError):
        decode_token(_token(now=old))  # default ttl 8h -> expired an hour ago


def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode(
        {"sub": "u1", "aud": AUDIENCE, "role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "some-other-secret-key-of-32-bytes!!",
        algorithm=ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_token(forged)


def test_garbage_and_wrong_audience_are_rejected():
    with pytest.raises(TokenError):
        decode_token("not.a.jwt")
    secret = get_settings().effective_jwt_secret
    wrong_aud = jwt.encode(
        {"sub": "u1", "aud": "someone-else", "exp": datetime.now(UTC) + timedelta(hours=1)},
        secret,
        algorithm=ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_token(wrong_aud)


def test_supabase_style_token_maps_app_metadata_role_else_viewer():
    secret = get_settings().effective_jwt_secret
    exp = datetime.now(UTC) + timedelta(hours=1)
    base = {"sub": "s1", "aud": AUDIENCE, "exp": exp, "role": "authenticated"}
    as_agent = jwt.encode({**base, "app_metadata": {"role": "agent"}}, secret, algorithm=ALGORITHM)
    plain = jwt.encode(base, secret, algorithm=ALGORITHM)
    assert decode_token(as_agent).role == "agent"
    assert decode_token(plain).role == "viewer"


def test_bearer_token_parsing():
    assert bearer_token("Bearer abc") == "abc"
    assert bearer_token("bearer abc") == "abc"
    assert bearer_token("Basic abc") is None
    assert bearer_token("Bearer ") is None
    assert bearer_token(None) is None


def test_token_does_not_embed_any_secret():
    claims = jwt.decode(_token(), options={"verify_signature": False})
    assert set(claims) == {"sub", "email", "role", "aud", "iat", "exp"}
