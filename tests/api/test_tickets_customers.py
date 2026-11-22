"""Phase 4 (F1, F4 read side): ticket and customer routes against the seeded demo data."""

import pytest

API = "/api/v1"


def _customer_id(client, headers, search):
    items = client.get(f"{API}/customers", params={"search": search}, headers=headers).json()["items"]
    assert items, search
    return items[0]["id"]


def test_routes_require_a_token(client):
    for path in ("/tickets", "/tickets/CD-1001", "/customers", "/tickets/CD-1001/events"):
        assert client.get(API + path).status_code == 401


def test_list_has_all_13_seeded_tickets_and_paginates(client, viewer_headers):
    body = client.get(f"{API}/tickets", params={"page_size": 100}, headers=viewer_headers).json()
    numbers = {t["ticket_number"] for t in body["items"]}
    assert {f"CD-{n}" for n in range(1001, 1014)} <= numbers
    assert body["total"] >= 13
    page = client.get(f"{API}/tickets", params={"page_size": 5, "page": 2}, headers=viewer_headers)
    assert len(page.json()["items"]) == 5
    assert page.json()["page"] == 2


def test_list_filters_and_search(client, viewer_headers):
    found = client.get(f"{API}/tickets", params={"search": "refund"}, headers=viewer_headers).json()
    assert any(t["ticket_number"] == "CD-1002" for t in found["items"])
    by_number = client.get(f"{API}/tickets", params={"search": "cd-1005"}, headers=viewer_headers)
    assert [t["ticket_number"] for t in by_number.json()["items"]] == ["CD-1005"]
    none = client.get(f"{API}/tickets", params={"status": "closed"}, headers=viewer_headers).json()
    assert none["total"] == 0


def test_list_rejects_bad_paging_and_enums(client, viewer_headers):
    for params in ({"page": 0}, {"page_size": 101}, {"status": "bogus"}, {"severity": "bogus"}):
        assert client.get(f"{API}/tickets", params=params, headers=viewer_headers).status_code == 422


@pytest.mark.parametrize("number", [f"CD-{n}" for n in range(1001, 1014)])
def test_every_demo_ticket_is_fetchable_by_number(client, viewer_headers, number):
    response = client.get(f"{API}/tickets/{number}", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_number"] == number
    assert body["messages"][0]["role"] == "customer"
    assert body["customer"]["id"] == body["customer_id"]
    assert body["workflow"] is None
    assert body["approval_status"] == "not_required"


def test_ticket_detail_loads_customer_context(client, viewer_headers):
    detail = client.get(f"{API}/tickets/CD-1001", headers=viewer_headers).json()
    assert detail["customer"]["plan"] == "enterprise"
    assert detail["subscription"]["plan"] == "enterprise"
    assert detail["workspaces"]
    # fetchable by id as well as by number
    assert client.get(f"{API}/tickets/{detail['id']}", headers=viewer_headers).status_code == 200
    ids = {h["id"] for h in detail["history"]}
    assert detail["id"] not in ids


def test_unknown_ticket_is_404_everywhere(client, agent_headers):
    for method, path, kwargs in (
        ("get", "/tickets/nope", {}),
        ("get", "/tickets/nope/events", {}),
        ("patch", "/tickets/nope", {"json": {"status": "closed"}}),
        ("post", "/tickets/nope/reply", {"json": {"body": "hi"}}),
        ("post", "/tickets/nope/request-info", {"json": {"questions": ["a?"]}}),
        ("post", "/tickets/nope/escalate", {"json": {"reason": "x"}}),
    ):
        response = getattr(client, method)(API + path, headers=agent_headers, **kwargs)
        assert response.status_code == 404, path
        assert response.json() == {"detail": "Ticket not found"}


@pytest.mark.parametrize("channel", ["email", "chat", "web", "api"])
def test_create_ticket_accepts_every_channel(client, agent_headers, channel):
    customer_id = _customer_id(client, agent_headers, "northwind")
    response = client.post(
        f"{API}/tickets",
        json={"customer_id": customer_id, "subject": f"Via {channel}", "body": "Help", "channel": channel},
        headers=agent_headers,
    )
    assert response.status_code == 201, response.text
    ticket = response.json()
    assert ticket["status"] == "new"
    assert ticket["channel"] == channel
    assert ticket["ticket_number"].startswith("CD-")
    assert ticket["category"] is None  # the workflow classifies, not the API
    detail = client.get(f"{API}/tickets/{ticket['id']}", headers=agent_headers).json()
    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["author_name"] == detail["customer"]["name"]


def test_ticket_numbers_do_not_repeat(client, agent_headers):
    customer_id = _customer_id(client, agent_headers, "kestrel")
    numbers = [
        client.post(
            f"{API}/tickets",
            json={"customer_id": customer_id, "subject": "s", "body": "b"},
            headers=agent_headers,
        ).json()["ticket_number"]
        for _ in range(3)
    ]
    assert len(set(numbers)) == 3


def test_create_ticket_validation(client, agent_headers):
    customer_id = _customer_id(client, agent_headers, "northwind")
    good = {"customer_id": customer_id, "subject": "s", "body": "b"}
    assert client.post(f"{API}/tickets", json={**good, "channel": "fax"}, headers=agent_headers).status_code == 422
    assert client.post(f"{API}/tickets", json={**good, "subject": "   "}, headers=agent_headers).status_code == 422
    assert client.post(f"{API}/tickets", json={**good, "body": ""}, headers=agent_headers).status_code == 422
    missing = client.post(f"{API}/tickets", json={**good, "customer_id": "nope"}, headers=agent_headers)
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Customer not found"}


def test_viewer_cannot_mutate(client, viewer_headers):
    for method, path, body in (
        ("post", "/tickets", {"customer_id": "x", "subject": "s", "body": "b"}),
        ("patch", "/tickets/CD-1001", {"status": "closed"}),
        ("post", "/tickets/CD-1001/reply", {"body": "hi"}),
        ("post", "/tickets/CD-1001/request-info", {"questions": ["q?"]}),
        ("post", "/tickets/CD-1001/escalate", {"reason": "r"}),
    ):
        assert getattr(client, method)(API + path, json=body, headers=viewer_headers).status_code == 403


def _new_ticket(client, headers, search="lumen"):
    return client.post(
        f"{API}/tickets",
        json={"customer_id": _customer_id(client, headers, search), "subject": "s", "body": "b"},
        headers=headers,
    ).json()


def test_patch_status_severity_assignee(client, agent_headers):
    ticket = _new_ticket(client, agent_headers)
    me = client.get(f"{API}/auth/me", headers=agent_headers).json()["id"]
    patched = client.patch(
        f"{API}/tickets/{ticket['id']}",
        json={"status": "resolved", "severity": "high", "assigned_to": me},
        headers=agent_headers,
    ).json()
    assert patched["status"] == "resolved"
    assert patched["severity"] == "high"
    assert patched["assigned_to"] == me
    assert patched["resolved_at"] is not None
    unassigned = client.patch(
        f"{API}/tickets/{ticket['id']}", json={"assigned_to": None}, headers=agent_headers
    ).json()
    assert unassigned["assigned_to"] is None
    assert unassigned["status"] == "resolved"  # untouched fields stay


def test_patch_rejects_empty_unknown_assignee_and_bad_values(client, agent_headers):
    ticket = _new_ticket(client, agent_headers)
    url = f"{API}/tickets/{ticket['id']}"
    assert client.patch(url, json={}, headers=agent_headers).status_code == 422
    assert client.patch(url, json={"status": "bogus"}, headers=agent_headers).status_code == 422
    assert client.patch(url, json={"assigned_to": "nobody"}, headers=agent_headers).status_code == 404


def test_reply_internal_note_and_closed_ticket(client, agent_headers):
    ticket = _new_ticket(client, agent_headers)
    url = f"{API}/tickets/{ticket['id']}"
    note = client.post(f"{url}/reply", json={"body": "private", "internal": True}, headers=agent_headers)
    assert note.status_code == 201
    assert note.json()["internal"] is True
    assert client.get(url, headers=agent_headers).json()["status"] == "new"
    sent = client.post(f"{url}/reply", json={"body": "  Hello  "}, headers=agent_headers).json()
    assert sent["role"] == "agent"
    assert sent["body"] == "Hello"
    assert sent["author_name"] == "Sam Agent"
    assert client.get(url, headers=agent_headers).json()["status"] == "in_progress"
    assert client.post(f"{url}/reply", json={"body": " "}, headers=agent_headers).status_code == 422
    client.patch(url, json={"status": "closed"}, headers=agent_headers)
    assert client.post(f"{url}/reply", json={"body": "late"}, headers=agent_headers).status_code == 409
    assert client.post(f"{url}/reply", json={"body": "n", "internal": True}, headers=agent_headers).status_code == 201


def test_request_info_sets_waiting_on_customer(client, agent_headers):
    ticket = _new_ticket(client, agent_headers)
    url = f"{API}/tickets/{ticket['id']}"
    response = client.post(f"{url}/request-info", json={"questions": ["Which browser?", " ", "When?"]}, headers=agent_headers)
    assert response.status_code == 201
    assert "1. Which browser?" in response.json()["body"]
    assert "2. When?" in response.json()["body"]
    assert client.get(url, headers=agent_headers).json()["status"] == "waiting_on_customer"
    assert client.post(f"{url}/request-info", json={"questions": []}, headers=agent_headers).status_code == 422
    assert client.post(f"{url}/request-info", json={"questions": ["  "]}, headers=agent_headers).status_code == 422


def test_escalate_creates_escalation_and_flags_ticket(client, agent_headers):
    ticket = _new_ticket(client, agent_headers)
    url = f"{API}/tickets/{ticket['id']}"
    response = client.post(f"{url}/escalate", json={"reason": "Possible breach", "priority": "urgent"}, headers=agent_headers)
    assert response.status_code == 201
    assert response.json()["severity"] == "critical"
    assert response.json()["status"] == "open"
    detail = client.get(url, headers=agent_headers).json()
    assert detail["status"] == "escalated"
    assert detail["escalation_required"] is True
    assert detail["escalation"]["reason"] == "Possible breach"
    assert client.post(f"{url}/escalate", json={"reason": "r", "priority": "meh"}, headers=agent_headers).status_code == 422


def test_events_empty_before_a_workflow_runs(client, viewer_headers):
    assert client.get(f"{API}/tickets/CD-1002/events", headers=viewer_headers).json() == []


def test_customers_list_search_and_paging(client, viewer_headers):
    body = client.get(f"{API}/customers", params={"page_size": 100}, headers=viewer_headers).json()
    assert body["total"] == len(body["items"]) >= 8
    names = [c["name"] for c in body["items"]]
    assert names == sorted(names)
    hit = client.get(f"{API}/customers", params={"search": "KESTREL"}, headers=viewer_headers).json()
    assert [c["company"] for c in hit["items"]] == ["Kestrel Analytics"]
    page = client.get(f"{API}/customers", params={"page_size": 3, "page": 3}, headers=viewer_headers).json()
    assert len(page["items"]) == 2 and page["total"] == body["total"]
    assert client.get(f"{API}/customers", params={"page_size": 0}, headers=viewer_headers).status_code == 422


def test_customer_detail_loads_subscription_workspace_and_tickets(client, viewer_headers):
    customer_id = _customer_id(client, viewer_headers, "kestrel")
    detail = client.get(f"{API}/customers/{customer_id}", headers=viewer_headers).json()
    assert detail["subscription"]["plan"] == "pro"
    assert detail["workspaces"]
    numbers = {t["ticket_number"] for t in detail["tickets"]}
    assert {"CD-1003", "CD-1008"} <= numbers
    assert detail["memory"] == []
    assert all(t["customer_name"] == detail["name"] for t in detail["tickets"])


def test_unknown_customer_is_404(client, viewer_headers):
    response = client.get(f"{API}/customers/nope", headers=viewer_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Customer not found"}


def test_mutations_are_audited(client, agent_headers):
    import os
    import sqlite3

    ticket = _new_ticket(client, agent_headers)
    client.post(f"{API}/tickets/{ticket['id']}/reply", json={"body": "hi"}, headers=agent_headers)
    db_path = os.environ["DATABASE_URL"].split("///", 1)[1]
    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            "SELECT method, path, status_code FROM audit_logs WHERE path LIKE ?",
            (f"%{ticket['id']}%",),
        ).fetchall()
    assert ("POST", f"/api/v1/tickets/{ticket['id']}/reply", 201) in rows
