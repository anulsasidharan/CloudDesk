"""Phase 1 / N3: health probes answer offline and every response carries X-Request-ID."""

import pytest


@pytest.mark.parametrize("path", ["/health", "/health/live"])
def test_probes_ok(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_offline_stack(client):
    body = client.get("/health/ready").json()
    assert body["status"] == "ok"
    assert body["checks"]["llm"] == "fake"
    assert body["checks"]["redis"] == "fake"
    assert body["checks"]["vector_store"] == "memory"


def test_request_id_generated(client):
    response = client.get("/health/live")
    assert len(response.headers["X-Request-ID"]) >= 16


def test_request_id_echoed(client):
    response = client.get("/health/live", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_unsafe_request_id_replaced(client):
    response = client.get("/health/live", headers={"X-Request-ID": "bad id\twith spaces"})
    assert response.headers["X-Request-ID"] != "bad id\twith spaces"


def test_request_id_on_404(client):
    assert "X-Request-ID" in client.get("/nope").headers


def test_request_id_exposed_through_cors(client):
    response = client.get(
        "/health/live",
        headers={"Origin": "http://localhost:3000", "X-Request-ID": "cors-1"},
    )
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()
