"""Phase 11: human approval pause/resume, rejection, escalation routing, shared tool path.

Every test that pauses a run makes its OWN refund ticket, because the demo database is shared by
the whole session and a paused ticket answers 409 to a second run.
"""

import pytest
from app.core import database
from app.repositories import ApprovalRepository, EscalationRepository, ResolutionActionRepository
from app.schemas.common import ApprovalStatus

API = "/api/v1"
REFUND_TOOL = "create_refund_request"


def _new_refund_ticket(client, headers) -> str:
    """A fresh copy of CD-1002 (refund for unused seats). Returns its ticket number."""
    source = client.get(f"{API}/tickets/CD-1002", headers=headers).json()
    created = client.post(
        f"{API}/tickets",
        json={
            "customer_id": source["customer_id"],
            "subject": source["subject"],
            "body": source["body"],
            "channel": "web",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["ticket_number"]


def _run(client, headers, number):
    response = client.post(f"{API}/tickets/{number}/run", headers=headers)
    assert response.status_code == 202, response.text


def _workflow(client, headers, number):
    return client.get(f"{API}/tickets/{number}/workflow", headers=headers).json()


def _paused(client, headers):
    """Make a refund ticket, run it to the approval pause, return (number, approval_id)."""
    number = _new_refund_ticket(client, headers)
    _run(client, headers, number)
    state = _workflow(client, headers, number)
    assert state["status"] == "waiting_for_approval", state
    return number, state["approval_request_id"]


def _ticket(client, headers, number):
    return client.get(f"{API}/tickets/{number}", headers=headers).json()


def _refund_rows(state):
    return [a for a in state["actions"] if a["tool"] == REFUND_TOOL]


# ---- P11-1 human approval interrupt --------------------------------------------------------


def test_refund_ticket_pauses_with_a_pending_approval_and_waiting_ticket(client, agent_headers):
    number, approval_id = _paused(client, agent_headers)
    approval = client.get(f"{API}/approvals/{approval_id}", headers=agent_headers).json()
    assert approval["status"] == "pending"
    assert approval["ticket_number"] == number
    assert approval["action"]["tool"] == REFUND_TOOL
    assert approval["requested_by"] == "ai" and approval["risk_level"] == "high"
    assert _ticket(client, agent_headers, number)["status"] == "waiting_on_approval"
    state = _workflow(client, agent_headers, number)
    assert state["current_node"] == "human_approval"
    assert _refund_rows(state)[0]["status"] == "pending_approval"
    assert _refund_rows(state)[0]["result"] is None  # nothing ran


def test_pausing_writes_exactly_one_approval_request(client, agent_headers):
    number, _ = _paused(client, agent_headers)
    pending = client.get(f"{API}/approvals?status=pending", headers=agent_headers).json()
    assert [a["ticket_number"] for a in pending].count(number) == 1
    events = client.get(f"{API}/tickets/{number}/events", headers=agent_headers).json()
    kinds = [e["event_type"] for e in events]
    assert kinds.count("approval_requested") == 1
    assert "workflow_completed" not in kinds  # a paused run is not a finished run
    assert not any(e["event_type"] == "error" for e in events)


def test_a_second_run_while_paused_is_409(client, agent_headers):
    number, _ = _paused(client, agent_headers)
    response = client.post(f"{API}/tickets/{number}/run", headers=agent_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Ticket is waiting on approval"


def test_handling_the_same_pause_twice_does_not_duplicate_the_request(client, agent_headers):
    """The code that records a pause must be safe to run again (CLAUDE.md 18, rule 8)."""
    from app.core.observability import WorkflowTracer
    from app.services import workflow_service

    number, approval_id = _paused(client, agent_headers)
    state = _workflow(client, agent_headers, number)

    async def again():
        async with database.session_scope() as session:
            approval = await ApprovalRepository(session).get(approval_id)
            run_id, ticket_id = approval.workflow_id, approval.ticket_id
        await workflow_service._handle_interrupt(run_id, state, WorkflowTracer(run_id, ticket_id))
        async with database.session_scope() as session:
            pending = await ApprovalRepository(session).list_filtered("pending")
            actions = await ResolutionActionRepository(session).list_for_workflow(run_id)
        return [p for p in pending if p.workflow_id == run_id], actions

    pending, actions = client.portal.call(again)
    assert len(pending) == 1
    assert [a.tool for a in actions].count(REFUND_TOOL) == 1


# ---- P11-2 + P11-4 approve and resume, shared tool path ------------------------------------


def test_approve_resumes_and_runs_the_refund_exactly_once(client, agent_headers):
    number, approval_id = _paused(client, agent_headers)
    response = client.post(
        f"{API}/approvals/{approval_id}/approve", json={"note": "Verified seats"}, headers=agent_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["approval"]["status"] == "approved"
    assert body["approval"]["decision_note"] == "Verified seats"
    assert body["approval"]["decided_by"] and body["approval"]["decided_at"]
    workflow = body["workflow"]
    assert workflow["status"] == "completed"
    assert workflow["approval_status"] == "approved"
    refunds = _refund_rows(workflow)
    assert len(refunds) == 1
    assert refunds[0]["status"] == "executed"
    assert refunds[0]["result"]["amount"] > 0
    assert workflow["completed_nodes"][-4:] == [
        "human_approval",
        "execute_resolution",
        "ticket_summary",
        "memory_update",
    ]
    assert _ticket(client, agent_headers, number)["status"] == "in_progress"


def test_approve_records_the_decision_in_the_trace(client, agent_headers):
    number, approval_id = _paused(client, agent_headers)
    client.post(f"{API}/approvals/{approval_id}/approve", json={}, headers=agent_headers)
    events = client.get(f"{API}/tickets/{number}/events", headers=agent_headers).json()
    kinds = [e["event_type"] for e in events]
    assert kinds.count("approval_requested") == 1 and kinds.count("approval_resolved") == 1
    assert kinds.index("approval_requested") < kinds.index("approval_resolved")
    assert kinds[-1] == "workflow_completed"
    assert any(e["tool"] == REFUND_TOOL for e in events)  # the tool call is traced


def test_approve_works_without_a_request_body(client, agent_headers):
    _, approval_id = _paused(client, agent_headers)
    response = client.post(f"{API}/approvals/{approval_id}/approve", headers=agent_headers)
    assert response.status_code == 200
    assert response.json()["workflow"]["status"] == "completed"


def test_deciding_twice_is_409_and_does_not_run_the_refund_again(client, agent_headers):
    number, approval_id = _paused(client, agent_headers)
    first = client.post(f"{API}/approvals/{approval_id}/approve", json={}, headers=agent_headers)
    assert first.status_code == 200
    for action in ("approve", "reject"):
        again = client.post(f"{API}/approvals/{approval_id}/{action}", json={}, headers=agent_headers)
        assert again.status_code == 409
    assert len(_refund_rows(_workflow(client, agent_headers, number))) == 1


def test_resuming_a_run_that_is_not_paused_is_409(client, agent_headers):
    """The approval is still pending but its run is no longer waiting."""
    number, approval_id = _paused(client, agent_headers)
    state = _workflow(client, agent_headers, number)

    async def finish_the_run():
        from app.repositories import WorkflowRunRepository
        from app.schemas.common import RunStatus

        async with database.session_scope() as session:
            repo = WorkflowRunRepository(session)
            await repo.set_status(await repo.get(state["workflow_id"]), RunStatus.COMPLETED)

    client.portal.call(finish_the_run)
    response = client.post(f"{API}/approvals/{approval_id}/approve", json={}, headers=agent_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Workflow is not waiting for approval"


def test_unknown_approval_is_404(client, agent_headers):
    for path in ("", "/approve", "/reject"):
        method = client.get if path == "" else client.post
        response = method(f"{API}/approvals/does-not-exist{path}", headers=agent_headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Approval not found"


def test_viewer_can_read_approvals_but_not_decide(client, agent_headers, viewer_headers):
    _, approval_id = _paused(client, agent_headers)
    assert client.get(f"{API}/approvals", headers=viewer_headers).status_code == 200
    assert client.get(f"{API}/approvals/{approval_id}", headers=viewer_headers).status_code == 200
    for action in ("approve", "reject"):
        response = client.post(f"{API}/approvals/{approval_id}/{action}", json={}, headers=viewer_headers)
        assert response.status_code == 403
    still = client.get(f"{API}/approvals/{approval_id}", headers=agent_headers).json()
    assert still["status"] == "pending"


def test_approvals_need_a_token(client):
    assert client.get(f"{API}/approvals").status_code in (401, 403)
    assert client.post(f"{API}/approvals/x/approve").status_code in (401, 403)


def test_admin_can_approve(client, agent_headers, admin_headers):
    _, approval_id = _paused(client, agent_headers)
    response = client.post(f"{API}/approvals/{approval_id}/approve", json={}, headers=admin_headers)
    assert response.status_code == 200


def test_list_filters_by_status(client, agent_headers):
    _, approval_id = _paused(client, agent_headers)
    client.post(f"{API}/approvals/{approval_id}/approve", json={}, headers=agent_headers)
    approved = client.get(f"{API}/approvals?status=approved", headers=agent_headers).json()
    pending = client.get(f"{API}/approvals?status=pending", headers=agent_headers).json()
    assert approval_id in [a["id"] for a in approved]
    assert approval_id not in [a["id"] for a in pending]
    assert client.get(f"{API}/approvals?status=bogus", headers=agent_headers).status_code == 422


def test_an_approval_needing_action_never_runs_without_a_recorded_approval(client):
    """``execute_resolution`` asks the database, not the graph state (CLAUDE.md 18.1)."""
    from agents.nodes.resolution import _approval_recorded

    assert client.portal.call(_approval_recorded, "no-such-workflow") is False


# ---- P11-1 + P11-3 rejection routes to escalation ------------------------------------------


def test_reject_escalates_and_never_runs_the_refund(client, agent_headers):
    number, approval_id = _paused(client, agent_headers)
    response = client.post(
        f"{API}/approvals/{approval_id}/reject",
        json={"note": "Seats still in use"},
        headers=agent_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["approval"]["status"] == "rejected"
    workflow = body["workflow"]
    assert workflow["status"] == "escalated"
    assert workflow["approval_status"] == "rejected"
    assert "escalation" in workflow["completed_nodes"]
    assert "execute_resolution" not in workflow["completed_nodes"]
    refund = _refund_rows(workflow)[0]
    assert refund["status"] == "rejected"
    assert "amount" not in (refund["result"] or {})  # no refund was issued
    detail = _ticket(client, agent_headers, number)
    assert detail["status"] == "escalated"
    assert detail["escalation"]["team"] == "support_leads"
    assert "Seats still in use" in detail["escalation"]["reason"]


# ---- P11-3 policy escalation ---------------------------------------------------------------


@pytest.mark.parametrize("number", ["CD-1005", "CD-1006", "CD-1009", "CD-1011"])
def test_policy_tickets_escalate_without_waiting_for_approval(client, agent_headers, number):
    _run(client, agent_headers, number)
    state = _workflow(client, agent_headers, number)
    assert state["status"] == "escalated", state
    assert state["escalation_required"] is True
    assert state["approval_status"] == "not_required"
    assert "human_approval" not in state["completed_nodes"]
    assert state["completed_nodes"][-3:] == ["escalation", "ticket_summary", "memory_update"]
    detail = _ticket(client, agent_headers, number)
    assert detail["status"] == "escalated"
    assert detail["escalation"] is not None and detail["escalation"]["status"] == "open"
    pending = client.get(f"{API}/approvals?status=pending", headers=agent_headers).json()
    assert number not in [a["ticket_number"] for a in pending]


def test_security_ticket_goes_to_the_security_team(client, agent_headers):
    _run(client, agent_headers, "CD-1005")
    detail = _ticket(client, agent_headers, "CD-1005")
    assert detail["escalation"]["team"] != ""
    assert detail["escalation"]["severity"] in ("high", "critical")


def test_escalation_is_filed_through_the_registry_and_traced(client, agent_headers):
    _run(client, agent_headers, "CD-1011")
    events = client.get(f"{API}/tickets/CD-1011/events", headers=agent_headers).json()
    tools = [e["tool"] for e in events if e["event_type"] == "tool_called" and e["node"] == "escalation"]
    assert "create_escalation" in tools and "update_ticket" in tools


def test_escalation_is_filed_once_per_run(client, agent_headers):
    from agents.nodes.approval import escalation

    _run(client, agent_headers, "CD-1009")
    state = _workflow(client, agent_headers, "CD-1009")

    async def rerun():
        async with database.session_scope() as session:
            filed = await EscalationRepository(session).for_workflow(state["workflow_id"])
        again = await escalation(
            {
                "workflow_id": state["workflow_id"],
                "ticket_id": filed.ticket_id,
                "severity": "high",
                "escalation_team": filed.team,
                "escalation_reason": filed.reason,
                "resolution_plan": {"summary": "s", "customer_reply": "r"},
            }
        )
        async with database.session_scope() as session:
            total = [
                e
                for e in await EscalationRepository(session).list_for_ticket(filed.ticket_id)
                if e.workflow_id == state["workflow_id"]
            ]
        return filed, again, total

    filed, again, total = client.portal.call(rerun)
    assert again["escalation_id"] == filed.id
    assert len(total) == 1


def test_prompt_injection_ticket_neither_exports_nor_waits(client, agent_headers):
    _run(client, agent_headers, "CD-1013")
    state = _workflow(client, agent_headers, "CD-1013")
    assert state["status"] in ("completed", "escalated")
    assert state["approval_status"] == "not_required"
    assert {a["tool"] for a in state["actions"]} <= {"update_ticket"}


def test_low_risk_ticket_still_completes_without_a_pause(client, agent_headers):
    _run(client, agent_headers, "CD-1004")
    state = _workflow(client, agent_headers, "CD-1004")
    assert state["status"] == "completed" and state["approval_status"] == "not_required"
    assert "human_approval" not in state["completed_nodes"]
    assert "escalation" not in state["completed_nodes"]


def test_approved_refund_is_a_database_record_with_the_approval_linked(client, agent_headers):
    number, approval_id = _paused(client, agent_headers)
    client.post(f"{API}/approvals/{approval_id}/approve", json={}, headers=agent_headers)
    state = _workflow(client, agent_headers, number)

    async def load():
        async with database.session_scope() as session:
            rows = await ResolutionActionRepository(session).list_for_workflow(state["workflow_id"])
            approval = await ApprovalRepository(session).get(approval_id)
            return rows, approval

    rows, approval = client.portal.call(load)
    refund = next(r for r in rows if r.tool == REFUND_TOOL)
    assert refund.approval_id == approval_id
    assert approval.status == ApprovalStatus.APPROVED.value
