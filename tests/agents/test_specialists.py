"""P9-2 .. P9-7: one test per specialist behaviour, offline (fake provider)."""

import pathlib

import pytest
from app.core.llm import StructuredResult
from app.schemas.common import Category, Severity
from app.schemas.workflow import (
    EscalationDecision,
    ReplyDraft,
    SeverityAssessment,
    TokenUsage,
)
from app.tools import ToolRegistry

from agents.specialists import (
    CustomerAgent,
    EscalationAgent,
    ResolutionAgent,
    SupervisorAgent,
    plan_actions,
)
from agents.specialists import escalation as escalation_module
from agents.specialists import resolution as resolution_module
from agents.specialists import supervisor as supervisor_module

# ------------------------------------------------------------------ Supervisor (F2, F3)


async def test_supervisor_classifies_with_a_one_line_summary(ticket):
    t = await ticket("CD-1002")
    result = await SupervisorAgent().understand(t.subject, t.body)
    assert result.output.category is Category.BILLING
    assert "\n" not in result.output.summary and result.output.summary
    assert result.usage.cost_usd == 0.0 and result.usage.calls == 1


async def test_supervisor_severity_has_a_reason_and_feature_request_stays_low(ticket):
    t = await ticket("CD-1010")
    cls = (await SupervisorAgent().understand(t.subject, t.body)).output
    sev = (await SupervisorAgent().assess_severity(t.subject, t.body, cls.category, t.plan)).output
    assert cls.category is Category.FEATURE_REQUEST
    assert sev.severity is Severity.LOW and sev.reason


async def test_rules_raise_the_model_severity_never_lower_it(ticket, monkeypatch):
    t = await ticket("CD-1005")  # security: policy floor is critical

    async def model_says(severity):
        async def fake_call(schema, **_):
            return StructuredResult(
                SeverityAssessment(severity=severity, reason="model view"), TokenUsage(), 0
            )

        monkeypatch.setattr(supervisor_module, "call_structured", fake_call)
        return (
            await SupervisorAgent().assess_severity(t.subject, t.body, Category.SECURITY, t.plan)
        ).output

    assert (await model_says(Severity.LOW)).severity is Severity.CRITICAL  # raised
    feature = await ticket("CD-1010")
    monkeypatch.setattr(
        supervisor_module,
        "call_structured",
        lambda schema, **_: _async_result(SeverityAssessment(severity=Severity.HIGH, reason="m")),
    )
    out = (
        await SupervisorAgent().assess_severity(
            feature.subject, feature.body, Category.FEATURE_REQUEST, feature.plan
        )
    ).output
    assert out.severity is Severity.HIGH  # the rule floor (low) did not lower the model


async def _async_result(value):
    return StructuredResult(value, TokenUsage(), 0)


async def test_injection_is_flagged_and_does_not_change_the_category(ticket):
    t = await ticket("CD-1013")
    cls = (await SupervisorAgent().understand(t.subject, t.body)).output
    sev = (await SupervisorAgent().assess_severity(t.subject, t.body, cls.category, t.plan)).output
    assert sev.injection_suspected is True
    assert "export" not in cls.summary.lower()


async def test_ticket_summary_is_scrubbed(ticket, pipeline):
    run = await pipeline("CD-1002")
    summary = await SupervisorAgent().summarize(
        run.t.subject, run.cls, "Card 4111 1111 1111 1111 on file", "waiting on approval"
    )
    assert "4111" not in summary.output.summary and "REDACTED" in summary.output.summary


# ------------------------------------------------------------------ Customer (F4)


async def test_customer_context_loads_everything_with_no_model_call(ticket, registry):
    t = await ticket("CD-1002")
    result = await CustomerAgent().run(t.customer_id, t.id, registry)
    ctx = result.output
    assert result.usage.calls == 0 and result.usage.total_tokens == 0
    assert {c.tool for c in result.tool_calls} == {
        "get_customer",
        "get_subscription",
        "get_ticket_history",
    }
    assert ctx.customer["company"] == "Brightpath Studio"
    assert ctx.subscription["seats_purchased"] == 8 and ctx.subscription["seats_used"] == 5
    assert ctx.workspaces and all("id" in w for w in ctx.workspaces)
    assert all(t.id != p["id"] for p in ctx.previous_tickets)  # the open ticket is excluded


async def test_customer_agent_rejects_an_unknown_customer(registry, maker):
    with pytest.raises(LookupError):
        await CustomerAgent().run("no-such-customer", None, registry)


# ------------------------------------------------------------------ Knowledge (F5, F6)


async def test_knowledge_returns_cited_evidence_and_similar_cases(pipeline):
    run = await pipeline("CD-1002")
    titles = [e.title for e in run.know.evidence]
    assert any("Refund" in x or "Seat" in x for x in titles)
    assert all(e.source.startswith("kb://") and e.score > 0 for e in run.know.evidence)
    assert "prev_seat_refund" in [c.key for c in run.know.previous_cases]
    assert len(run.know.evidence) <= 3 and len(run.know.previous_cases) <= 3


async def test_knowledge_finds_the_sso_article_for_the_sso_ticket(pipeline):
    run = await pipeline("CD-1001")
    assert any("SSO" in e.title for e in run.know.evidence)


# ------------------------------------------------------------------ Troubleshooting (F7)


async def test_diagnosis_has_causes_and_numbered_steps(pipeline):
    run = await pipeline("CD-1004")
    assert run.diag.probable_causes and run.diag.steps
    assert run.diag.numbered()[0].startswith("1. ")
    assert any("Storage" in c for c in run.diag.probable_causes)  # from the customer's own numbers


async def test_active_incident_becomes_a_probable_cause_via_the_tool(pipeline, ticket, registry):
    from agents.specialists import TroubleshootingAgent

    run = await pipeline("CD-1001")
    assert any("Active incident" in c for c in run.diag.probable_causes)
    assert run.diag.service_status["operational"] is False
    t = await ticket("CD-1001")
    result = await TroubleshootingAgent().run(
        t.subject, t.body, run.cls.category, run.ctx, run.know.evidence, run.know.previous_cases, registry
    )
    assert [c.tool for c in result.tool_calls] == ["check_service_status"]


# ------------------------------------------------------------------ Resolution (F8)


async def test_refund_ticket_plans_a_refund_that_needs_approval(pipeline):
    run = await pipeline("CD-1002")
    refund = [a for a in run.plan.actions if a.tool == "create_refund_request"]
    assert len(refund) == 1
    assert refund[0].requires_approval is True
    assert refund[0].args["amount"] == 45.0  # 3 unused seats x 15.00
    assert run.plan.validation_ok and run.plan.citations
    assert "refund of 45.00" in run.plan.customer_reply


async def test_low_risk_feature_request_only_updates_the_ticket(pipeline):
    run = await pipeline("CD-1010")
    assert [a.tool for a in run.plan.actions] == ["update_ticket"]
    assert not run.plan.actions[0].requires_approval


@pytest.mark.parametrize("number", ["CD-1005", "CD-1006", "CD-1009", "CD-1011", "CD-1013"])
async def test_no_money_or_account_action_on_policy_or_injection_tickets(pipeline, number):
    run = await pipeline(number)
    assert {a.tool for a in run.plan.actions} == {"update_ticket"}


async def test_injected_ticket_is_noted_and_never_exports(pipeline):
    run = await pipeline("CD-1013")
    assert "instruction-like" in run.plan.internal_notes
    assert "export" not in run.plan.customer_reply.lower()


async def test_reply_contains_every_step_and_no_internal_references(pipeline):
    run = await pipeline("CD-1003")
    for step in run.diag.steps:
        assert step.lower() in run.plan.customer_reply.lower()
    assert "kb://" not in run.plan.customer_reply and "/api/" not in run.plan.customer_reply


async def test_missing_steps_are_added_to_a_model_reply(pipeline, monkeypatch):
    run = await pipeline("CD-1003")

    monkeypatch.setattr(
        resolution_module,
        "call_structured",
        lambda schema, **_: _async_result(
            ReplyDraft(summary="s", customer_reply="Hi, we are looking into it.")
        ),
    )
    plan = (
        await ResolutionAgent().run(
            ticket_id=run.t.id,
            subject=run.t.subject,
            body=run.t.body,
            classification=run.cls,
            severity=run.sev.severity,
            context=run.ctx,
            diagnosis=run.diag,
            evidence=run.know.evidence,
        )
    ).output
    assert all(s in plan.customer_reply for s in run.diag.steps)


@pytest.mark.parametrize(
    "leak,kind",
    [
        ("See http://localhost:8000/admin for details.", "internal_url"),
        ("Your key is sk-abcdefghijklmnop1234567890.", "secret"),
        ("Also Priya Nair had the same issue.", "other_customer_data"),
    ],
)
async def test_a_leaking_reply_is_withheld_and_marked_invalid(pipeline, monkeypatch, leak, kind):
    run = await pipeline("CD-1003")
    monkeypatch.setattr(
        resolution_module,
        "call_structured",
        lambda schema, **_: _async_result(ReplyDraft(summary="s", customer_reply=f"Hi. {leak}")),
    )
    plan = (
        await ResolutionAgent().run(
            ticket_id=run.t.id,
            subject=run.t.subject,
            body=run.t.body,
            classification=run.cls,
            severity=run.sev.severity,
            context=run.ctx,
            diagnosis=run.diag,
            evidence=run.know.evidence,
            other_customer_markers=["Priya Nair"],
        )
    ).output
    assert plan.validation_ok is False and kind in plan.validation_issues
    assert plan.customer_reply == resolution_module.WITHHELD_REPLY


async def test_external_sharing_reset_only_for_paid_plans_and_needs_approval(pipeline):
    from app.schemas.workflow import Classification, CustomerContext

    cls = Classification(category=Category.WORKSPACE_PERMISSIONS, summary="cannot share")
    paid = CustomerContext(
        customer={"id": "c1", "plan": "business"},
        workspaces=[{"id": "w1", "external_sharing": False}],
    )
    free = CustomerContext(
        customer={"id": "c2", "plan": "free"}, workspaces=[{"id": "w2", "external_sharing": False}]
    )
    text = "I cannot share a folder externally"
    paid_tools = plan_actions(ticket_id="t", text=text, classification=cls, severity=Severity.LOW, context=paid)
    free_tools = plan_actions(ticket_id="t", text=text, classification=cls, severity=Severity.LOW, context=free)
    reset = [a for a in paid_tools if a.tool == "reset_demo_setting"]
    assert len(reset) == 1 and reset[0].requires_approval
    assert [a.tool for a in free_tools] == ["update_ticket"]


# ------------------------------------------------------------------ Escalation (F10)


@pytest.mark.parametrize(
    "number,team",
    [
        ("CD-1005", "security_response"),
        ("CD-1006", "data_integrity"),
        ("CD-1009", "privacy_compliance"),
        ("CD-1011", "billing_disputes"),
    ],
)
async def test_policy_cases_escalate_to_the_named_team_without_a_model_vote(pipeline, number, team):
    run = await pipeline(number)
    assert run.esc.escalation_required and run.esc.policy_matched
    assert run.esc.team == team and run.esc.rule_ids


async def test_ordinary_ticket_is_not_escalated(pipeline):
    run = await pipeline("CD-1010")
    assert run.esc.escalation_required is False and run.esc.team is None


async def _decide(monkeypatch, subject, body, model, severity):
    monkeypatch.setattr(
        escalation_module, "call_structured", lambda schema, **_: _async_result(model)
    )
    return (await EscalationAgent().run(subject, body, "pro", severity)).output


async def test_vague_model_escalation_is_distrusted(monkeypatch):
    vague = EscalationDecision(escalation_required=True, team="x", confidence=0.9)
    out = await _decide(monkeypatch, "Hello", "Something odd", vague, Severity.MEDIUM)
    assert out.escalation_required is False


async def test_unsure_model_on_a_serious_ticket_escalates_to_a_person(monkeypatch):
    unsure = EscalationDecision(escalation_required=True, confidence=0.3)
    out = await _decide(monkeypatch, "Hello", "Something odd", unsure, Severity.HIGH)
    assert out.escalation_required and out.team == "support_leads" and not out.policy_matched


async def test_policy_wins_even_when_the_model_says_no(monkeypatch):
    no = EscalationDecision(escalation_required=False, confidence=1.0)
    out = await _decide(
        monkeypatch, "Breach", "We think our account was compromised", no, Severity.LOW
    )
    assert out.escalation_required and out.team == "security_response"


async def test_filing_an_escalation_goes_through_the_registry(pipeline, registry, maker):
    from app.repositories import EscalationRepository

    run = await pipeline("CD-1005")
    result = await EscalationAgent().file(run.esc, run.t.id, registry=registry)
    assert result.tool_calls[0].tool == "create_escalation" and result.tool_calls[0].ok
    async with maker() as db:
        rows = await EscalationRepository(db).list_for_ticket(run.t.id)
    assert [r.team for r in rows] == ["security_response"]


async def test_not_escalating_files_nothing(pipeline, registry):
    run = await pipeline("CD-1010")
    result = await EscalationAgent().file(run.esc, run.t.id, registry=registry)
    assert result.tool_calls == []


# ------------------------------------------------------------------ Layering and demo checkpoint


def test_specialists_write_no_sql_and_never_call_a_tool_directly():
    folder = pathlib.Path(__file__).resolve().parents[2] / "agents" / "specialists"
    for file in folder.glob("*.py"):
        source = file.read_text(encoding="utf-8")
        assert "sqlalchemy" not in source, file.name
        assert ".ainvoke(" not in source and "write_tool" not in source, file.name
    assert isinstance(ToolRegistry, type)


@pytest.mark.parametrize("number", ["CD-1002", "CD-1010"])
async def test_every_specialist_runs_offline_on_the_demo_tickets(pipeline, number):
    run = await pipeline(number)
    assert run.cls and run.sev and run.ctx and run.know and run.diag and run.plan and run.esc
    assert run.plan.validation_ok
    if number == "CD-1010":
        assert run.sev.severity is Severity.LOW
