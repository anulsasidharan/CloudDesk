"""Run -> poll -> events through the real API, offline (P10-5, P10-6)."""

from app.core import observability
from app.repositories import workflows as workflow_repos
from app.schemas.common import EventType

ALL_NODES = [
    "understand_ticket",
    "classify_severity",
    "customer_context",
    "knowledge_retrieval",
    "troubleshooting",
    "resolution_planning",
    "risk_check",
    "execute_resolution",
    "ticket_summary",
    "memory_update",
]


def _run(client, headers, number):
    response = client.post(f"/api/v1/tickets/{number}/run", headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def _workflow(client, headers, number):
    response = client.get(f"/api/v1/tickets/{number}/workflow", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_workflow_before_any_run_is_404(client, agent_headers):
    response = client.get("/api/v1/tickets/CD-1012/workflow", headers=agent_headers)
    assert response.status_code == 404


def test_low_risk_ticket_runs_to_the_end(client, agent_headers):
    accepted = _run(client, agent_headers, "CD-1010")
    assert accepted["status"] == "running" and accepted["workflow_id"]
    state = _workflow(client, agent_headers, "CD-1010")
    assert state["status"] == "completed"
    assert state["completed_nodes"] == ALL_NODES
    assert state["severity"] == "low"
    assert state["classification"]["category"] == "feature_request"
    assert state["risk"]["level"] == "low"
    assert state["final_response"] and state["ticket_summary"]
    assert state["token_usage"]["estimated_cost_usd"] == 0.0
    assert [a["tool"] for a in state["actions"]] == ["update_ticket"]
    assert state["actions"][0]["status"] == "executed"


def test_events_have_nodes_tools_llm_and_durations(client, agent_headers):
    _run(client, agent_headers, "CD-1010")
    events = client.get("/api/v1/tickets/CD-1010/events", headers=agent_headers).json()
    kinds = {e["event_type"] for e in events}
    assert {"node_started", "node_completed", "tool_called", "llm_called"} <= kinds
    assert "workflow_completed" in kinds
    completed = [e for e in events if e["event_type"] == "node_completed"]
    assert all(e["duration_ms"] is not None for e in completed)
    assert any(e["tool"] == "get_customer" for e in events)


def test_events_never_contain_raw_prompts_or_body(client, agent_headers):
    _run(client, agent_headers, "CD-1013")
    ticket = client.get("/api/v1/tickets/CD-1013", headers=agent_headers).json()
    events = client.get("/api/v1/tickets/CD-1013/events", headers=agent_headers).json()
    assert events
    blob = str([e["payload"] for e in events])
    assert ticket["body"][:40] not in blob
    assert "untrusted_content" not in blob


def test_refund_is_held_not_executed(client, agent_headers):
    _run(client, agent_headers, "CD-1002")
    state = _workflow(client, agent_headers, "CD-1002")
    assert state["status"] == "completed"
    assert state["risk"]["level"] == "high"
    refund = next(a for a in state["actions"] if a["tool"] == "create_refund_request")
    assert refund["status"] == "pending_approval" and refund["result"] is None
    assert refund["requires_approval"] is True


def test_policy_ticket_is_high_risk_and_flagged(client, agent_headers):
    _run(client, agent_headers, "CD-1005")
    state = _workflow(client, agent_headers, "CD-1005")
    assert state["escalation_required"] is True
    assert state["risk"]["level"] == "high"
    assert all(a["tool"] != "create_refund_request" for a in state["actions"])


def test_injection_ticket_plans_no_money_or_export_action(client, agent_headers):
    _run(client, agent_headers, "CD-1013")
    state = _workflow(client, agent_headers, "CD-1013")
    assert state["risk"]["level"] == "high"
    assert {a["tool"] for a in state["actions"]} <= {"update_ticket"}


def test_ticket_detail_embeds_latest_workflow(client, agent_headers):
    _run(client, agent_headers, "CD-1010")
    detail = client.get("/api/v1/tickets/CD-1010", headers=agent_headers).json()
    assert detail["workflow"]["status"] == "completed"


def test_run_is_409_while_waiting_on_approval(client, agent_headers):
    client.patch(
        "/api/v1/tickets/CD-1008", json={"status": "waiting_on_approval"}, headers=agent_headers
    )
    response = client.post("/api/v1/tickets/CD-1008/run", headers=agent_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Ticket is waiting on approval"


def test_viewer_cannot_run_but_can_read(client, agent_headers, viewer_headers):
    assert client.post("/api/v1/tickets/CD-1010/run", headers=viewer_headers).status_code == 403
    _run(client, agent_headers, "CD-1010")
    assert client.get("/api/v1/tickets/CD-1010/workflow", headers=viewer_headers).status_code == 200


def test_unknown_ticket_is_404(client, agent_headers):
    assert client.post("/api/v1/tickets/CD-9999/run", headers=agent_headers).status_code == 404
    assert client.get("/api/v1/tickets/CD-9999/workflow", headers=agent_headers).status_code == 404


def test_second_run_recalls_memory_written_by_the_first(client, agent_headers):
    _run(client, agent_headers, "CD-1007")
    _run(client, agent_headers, "CD-1007")
    state = _workflow(client, agent_headers, "CD-1007")
    assert state["errors"] == []
    assert state["customer_context"]["memory_notes"]


async def test_telemetry_failure_does_not_raise(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(workflow_repos.WorkflowEventRepository, "add", boom)
    tracer = observability.WorkflowTracer("w", "t")
    await tracer.emit(EventType.NODE_STARTED, node="x")
    async with tracer.node("x"):
        pass


def test_failed_node_marks_run_failed(client, agent_headers, monkeypatch):
    from agents.specialists import TroubleshootingAgent

    async def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(TroubleshootingAgent, "run", broken)
    _run(client, agent_headers, "CD-1003")
    state = _workflow(client, agent_headers, "CD-1003")
    assert state["status"] == "failed"
    assert "RuntimeError" in state["errors"][-1]
    assert "troubleshooting" not in state["completed_nodes"]
    events = client.get("/api/v1/tickets/CD-1003/events", headers=agent_headers).json()
    assert any(e["event_type"] == "error" and e["node"] == "troubleshooting" for e in events)
