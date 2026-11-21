"""N2: fixed-window limiter on fakeredis."""

import fakeredis
from app.middleware.rate_limit import RateLimitMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app(limit: int, redis, clock=lambda: 1_000_000.0) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit=limit, redis_factory=lambda: redis, clock=clock)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/health/live")
    def live():
        return {"status": "alive"}

    return app


def test_requests_over_the_limit_get_429_with_retry_after():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    with TestClient(_app(3, redis)) as client:
        codes = [client.get("/ping").status_code for _ in range(5)]
        blocked = client.get("/ping")
    assert codes == [200, 200, 200, 429, 429]
    assert blocked.json() == {"detail": "Rate limit exceeded"}
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-remaining"] == "0"


def test_allowed_responses_report_remaining_budget():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    with TestClient(_app(3, redis)) as client:
        first = client.get("/ping")
    assert first.headers["x-ratelimit-limit"] == "3"
    assert first.headers["x-ratelimit-remaining"] == "2"


def test_a_new_window_resets_the_counter():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    now = {"t": 1_000_000.0}
    with TestClient(_app(1, redis, clock=lambda: now["t"])) as client:
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 429
        now["t"] += 60
        assert client.get("/ping").status_code == 200


def test_clients_are_counted_separately_and_health_is_exempt():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    with TestClient(_app(1, redis)) as client:
        assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
        assert all(client.get("/health/live").status_code == 200 for _ in range(5))


def test_redis_outage_fails_open():
    class Broken:
        async def incr(self, *_a):
            raise ConnectionError("down")

    with TestClient(_app(1, Broken())) as client:
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 200
