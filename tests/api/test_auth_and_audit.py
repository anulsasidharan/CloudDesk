"""N1/N6 end to end: login, bad tokens, 403 for viewers, audit rows, middleware order."""

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import AuthUser, require_role
from app.main import create_app
from app.repositories.audit import AuditRepository
from fastapi import Depends
from fastapi.testclient import TestClient


def _app_with_probe_routes():
    app = create_app()

    @app.post("/__mutate")
    def mutate(user: AuthUser = Depends(require_role("agent"))):
        return {"by": user.email}

    @app.get("/__admin")
    def admin_only(user: AuthUser = Depends(require_role("admin"))):
        return {"by": user.email}

    @app.get("/__audit")
    async def audit(session=Depends(get_session)):
        rows = await AuditRepository(session).recent(limit=500)
        return [
            {
                "method": r.method,
                "path": r.path,
                "status": r.status_code,
                "email": r.actor_email,
                "request_id": r.request_id,
                "detail": r.detail,
            }
            for r in rows
        ]

    return app


def test_demo_login_issues_8_hour_tokens_for_the_three_demo_users(client):
    expected = {
        "admin@clouddesk.demo": "admin",
        "sam.agent@clouddesk.demo": "agent",
        "vic.viewer@clouddesk.demo": "viewer",
    }
    for email, role in expected.items():
        response = client.post("/api/v1/auth/demo-login", json={"email": email})
        body = response.json()
        assert response.status_code == 200
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 8 * 3600
        assert body["user"]["role"] == role
        assert body["user"]["email"] == email


def test_demo_login_by_role_and_default_and_unknown(client):
    by_role = client.post("/api/v1/auth/demo-login", json={"role": "viewer"}).json()
    assert by_role["user"]["email"] == "vic.viewer@clouddesk.demo"
    default = client.post("/api/v1/auth/demo-login").json()
    assert default["user"]["role"] == "agent"
    assert client.post("/api/v1/auth/demo-login", json={"email": "nobody@x.io"}).status_code == 404
    assert client.post("/api/v1/auth/demo-login", json={"role": "root"}).status_code == 422


def test_login_response_never_contains_the_signing_secret(client):
    secret = get_settings().effective_jwt_secret
    response = client.post("/api/v1/auth/demo-login", json={"role": "admin"})
    assert secret and secret not in response.text


def test_me_requires_a_valid_token(client, agent_headers):
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    assert bad.headers["www-authenticate"] == "Bearer"
    ok = client.get("/api/v1/auth/me", headers=agent_headers)
    assert ok.status_code == 200
    assert ok.json()["email"] == "sam.agent@clouddesk.demo"


def test_demo_login_is_hidden_when_demo_mode_is_off(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as other:
            assert other.post("/api/v1/auth/demo-login").status_code == 404
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_missing_and_bad_tokens_are_rejected_on_protected_routes():
    with TestClient(_app_with_probe_routes()) as c:
        assert c.post("/__mutate").status_code == 401
        assert c.post("/__mutate", headers={"Authorization": "Bearer junk"}).status_code == 401
        assert c.post("/__mutate", headers={"Authorization": "Basic abc"}).status_code == 401


def test_viewer_gets_403_agent_and_admin_are_accepted():
    with TestClient(_app_with_probe_routes()) as c:
        tokens = {
            role: {"Authorization": f"Bearer {c.post('/api/v1/auth/demo-login', json={'role': role}).json()['access_token']}"}
            for role in ("viewer", "agent", "admin")
        }
        assert c.post("/__mutate", headers=tokens["viewer"]).status_code == 403
        agent = c.post("/__mutate", headers=tokens["agent"])
        assert agent.status_code == 200 and agent.json() == {"by": "sam.agent@clouddesk.demo"}
        assert c.post("/__mutate", headers=tokens["admin"]).status_code == 200
        assert c.get("/__admin", headers=tokens["agent"]).status_code == 403
        assert c.get("/__admin", headers=tokens["admin"]).status_code == 200


def test_non_get_requests_write_audit_rows_and_get_requests_do_not():
    with TestClient(_app_with_probe_routes()) as c:
        agent = {
            "Authorization": "Bearer "
            + c.post("/api/v1/auth/demo-login", json={"role": "agent"}).json()["access_token"]
        }
        c.get("/health/live")
        c.post("/__mutate", headers={**agent, "X-Request-ID": "audit-ok-1"})
        c.post("/__mutate", headers={"X-Request-ID": "audit-401-1"})
        rows = {r["request_id"]: r for r in c.get("/__audit").json() if r["request_id"]}

    ok = rows["audit-ok-1"]
    assert (ok["method"], ok["path"], ok["status"]) == ("POST", "/__mutate", 200)
    assert ok["email"] == "sam.agent@clouddesk.demo"
    assert ok["detail"] == {"actor_role": "agent"}
    denied = rows["audit-401-1"]
    assert denied["status"] == 401 and denied["email"] is None
    assert not any(r["method"] == "GET" for r in rows.values())


def test_middleware_order_is_cors_requestid_ratelimit_audit():
    names = [m.cls.__name__ for m in create_app().user_middleware]
    # Starlette lists user middleware outermost first.
    assert names == [
        "CORSMiddleware",
        "RequestIdMiddleware",
        "RateLimitMiddleware",
        "AuditMiddleware",
    ]
