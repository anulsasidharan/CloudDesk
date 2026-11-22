# Phase 11 Interview Q&A: Approval and Escalation

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code.

---

## A. Big picture

**Q1. What did you build in Phase 11?**
The human-in-the-loop part of the workflow. A `human_approval` node that pauses the graph with `interrupt()`, an `escalation` node, graph routing for both (`agents/graph.py`, `agents/nodes/approval.py`), pause and resume handling in `workflow_service`, an approval service and four `/approvals` routes (`approval_service.py`, `api/approvals.py`), a rewritten `execute_resolution` that runs approved actions on the shared tool path, and a terminal demo (`scripts/demo.py`, `make demo`).

**Q2. Which requirements does it cover?**
F9 (consequential actions need human approval), F10 (policy cases escalate to a named team), N4 on the live path (injected text cannot trigger an action), and the 409 behaviour in CLAUDE.md section 10. It finishes the request flow in 4.1 steps 5 to 8.

**Q3. Which tasks were in the phase?**
P11-1 human approval interrupt, P11-2 approval decide and resume API, P11-3 escalation routing, P11-4 execute resolution on the shared tool path, P11-5 demo script for CD-1002 and CD-1005.

**Q4. Is this "Phase 10" in `PLAN_PHASE.md`?**
Yes. `TASKS.md` pulled memory forward, so its numbers are one ahead. TASKS Phase 11 is PLAN_PHASE Phase 10, "Approval and escalation".

**Q5. What is the demo checkpoint?**
`make demo` pauses on CD-1002 and, once approved, runs the refund. `make demo TICKET=CD-1005` escalates with no pause. I ran `scripts/demo.py` directly for both because `make` is not installed on my Windows machine, so the Makefile target itself is unrun.

**Q6. What changed from Phase 10 in one sentence?**
Phase 10 sent all three routes to `execute_resolution` and only recorded risky actions; Phase 11 sends `approval` to a pausing node and `escalation` to a node that files a real escalation, and lets an approved action actually run.

**Q7. What can a non-technical person understand from it?**
The AI prepares a refund but cannot release it. A person must say yes. After a yes it runs once. Dangerous cases (breach, data loss, privacy, payment dispute) skip the queue and go to a specialist team.

---

## B. The pause: `interrupt()`

**Q8. How does the workflow pause?**
`human_approval` calls `interrupt(payload)` from `langgraph.types`. LangGraph stops the graph and stores the state in the checkpointer under the run's `thread_id`. The background task ends. Nothing is waiting in memory.

**Q9. How does the service know the graph paused?**
After streaming, `_drive` in `workflow_service.py` calls `graph.aget_state(config)`. If `snapshot.next` is not empty, the graph stopped before END, so it is waiting. LangGraph also emits an extra `__interrupt__` chunk in values mode, which I filter out so it is never saved as state.

**Q10. What happens when the graph pauses?**
`_handle_interrupt` writes an `approval_requests` row, creates `resolution_actions` rows as `awaiting_approval` linked to it, sets the ticket to `waiting_on_approval`, saves the run as `waiting_on_approval`, and emits an `approval_requested` event. Test: `test_refund_ticket_pauses_with_a_pending_approval_and_waiting_ticket`.

**Q11. Why not write the approval row inside the node, before `interrupt()`?**
When a graph resumes, the node runs again **from the top**. Anything before `interrupt()` would run twice. CLAUDE.md rule 8 says interrupts must be small and idempotent. So the node only reads the plan, and the service writes the records once.

**Q12. Is the recording of the pause itself safe to run twice?**
Yes. `_handle_interrupt` reuses a pending approval and checks `for_workflow_tool` before adding an action row. `test_handling_the_same_pause_twice_does_not_duplicate_the_request` calls it twice and asserts one request and one refund row.

**Q13. Why do you need a checkpointer for this?**
The pause has to survive between two separate HTTP requests: the run request and the approve request. The checkpointer stores the graph state by `thread_id`. `workflow_runs.thread_id` is the link between our table and the checkpoint.

**Q14. What if the server restarts while a run is paused?**
With the SQLite checkpointer file the state should still be there, and the run row says `waiting_on_approval`. With `CHECKPOINT_DB_PATH=:memory:` (tests) it is lost. **I have not tested restart-resume**, so I would not claim it. It is on the gap list.

**Q15. What does the user see while the run is paused?**
`GET /tickets/{id}/workflow` returns status `waiting_for_approval`, `approval_status: "pending"`, an `approval_request_id`, `current_node: "human_approval"`, and the refund action as `pending_approval` with `result: null`.

**Q16. What stops a second run on a paused ticket?**
`create_run` raises `WorkflowConflictError("Ticket is waiting on approval")`, which the route turns into 409. Test: `test_a_second_run_while_paused_is_409`.

**Q17. Why does `route_after_approval` send everything except `"approved"` to escalation?**
It fails safe. A missing, odd or `pending` value must never run a refund. `test_only_an_explicit_approval_runs_the_actions` checks `rejected`, `pending`, `not_required`, empty and missing.

**Q18. How is the decision passed into the resumed graph?**
`resume_workflow` streams `Command(resume={"approved": bool, "note": str})` on the same `thread_id`. `interrupt()` returns that value inside `human_approval`, which writes `approval_status` and `approval_note` into the state.

---

## C. Approve, reject and the API

**Q19. What routes did you add?**
`GET /approvals?status=`, `GET /approvals/{id}`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`. Documented in `docs/API_CONTRACT.md`.

**Q20. Who can call them?**
Reading needs `viewer` or above. Approve and reject need `agent` or `admin`, enforced by `require_role(Role.AGENT)`. A viewer gets 403 and the request stays pending. Tests: `test_viewer_can_read_approvals_but_not_decide`, `test_admin_can_approve`.

**Q21. Walk me through an approve call.**
Load the approval, check it is pending, check the run is `waiting_on_approval`, claim it with one conditional UPDATE, set the run to `running` and the ticket to `in_progress`, commit, emit `approval_resolved`, resume the graph, then return `{approval, workflow}`.

**Q22. What is the claim and why one UPDATE?**
`ApprovalRepository.claim` runs `UPDATE approval_requests SET status=... WHERE id=? AND status='pending'` and returns whether one row changed. The database serialises it, so two simultaneous clicks cannot both succeed. The loser gets 409 and no second refund runs.

**Q23. What are the 409 cases?**
`Approval has already been decided` for a second click or a lost race, and `Workflow is not waiting for approval` when the run is not paused. Tests: `test_deciding_twice_is_409_and_does_not_run_the_refund_again`, `test_resuming_a_run_that_is_not_paused_is_409`.

**Q24. And 404?**
An unknown approval id returns `Approval not found` on GET, approve and reject. `test_unknown_approval_is_404`.

**Q25. Why commit before resuming?**
The resumed graph opens its own database sessions. If the decision were still in an open transaction they would not see it, and on SQLite they could hit a lock. `decide` calls `session.commit()` first.

**Q26. Why `session.expire_all()` after the resume?**
The graph wrote through other sessions. The request session had already cached the run as `running`, so without expiring it the response said `running` for a finished run. A test caught exactly that.

**Q27. Why does approve run the resume inside the request, not in a background task?**
The contract says approve returns the workflow state, so the response needs the finished result. The trade-off is the request lasts as long as the remaining nodes (execute, summary, memory). It is quick offline, but with a real model it adds the summary call. A worker would remove that. I list it as a gap.

**Q28. Can approve be called without a body?**
Yes. `body: DecisionRequest | None = None`. The note is optional, max 1000 characters. `test_approve_works_without_a_request_body`.

**Q29. What does the approval request contain?**
Ticket, workflow, the first action (`action`), all actions (`actions`), `risk_level`, `reason` (from the risk check), `requested_by: "ai"`, status, who decided, the note and timestamps. One request covers every approval-required action of a run.

**Q30. Why one approval per run and not one per action?**
A reviewer makes one decision about the plan. It also matches the contract's single `action` field, which I kept as the first action while adding `actions` for the full list. If we ever need per-action decisions that is a contract change.

**Q31. How do you record who decided?**
`decided_by` is the caller's profile id from the JWT, `decided_at` is the server time, and the note is stored. The audit middleware also writes an `audit_logs` row for the POST, and the trace gets an `approval_resolved` event.

**Q32. Are list results filtered?**
`?status=pending|approved|rejected`. Any other value is 422 because it is typed as the `ApprovalStatus` enum. `test_list_filters_by_status`.

---

## D. Executing the approved action

**Q33. How does an approved refund actually run?**
After approval the graph goes to `execute_resolution`. For each planned action it finds the row the pause created, and for an approval-required action it checks the database for an approved request. Then it calls `run_tool(..., approved=True)`, which calls `ToolRegistry.execute`, which runs `create_refund_request` against the mock billing adapter.

**Q34. Why does `execute_resolution` read the database instead of the state field `approval_status`?**
"Never run a refund without a recorded approval" (CLAUDE.md 18.1) must be a durable fact, not a variable that could be wrong. `_approval_recorded(workflow_id)` asks `ApprovalRepository.latest_for_workflow` for an `approved` row. `test_an_approval_needing_action_never_runs_without_a_recorded_approval` checks the negative.

**Q35. So there are two locks?**
Yes. First `execute_resolution` will not try without a recorded approval. Second, `ToolRegistry.execute` refuses an approval-required tool unless `approved=True`. Either alone stops an unapproved refund.

**Q36. Does an approved action take a different path from an automatic one?**
No, and that is the point (CLAUDE.md 7.4, "the same code path runs for auto-resolved and human-approved actions"). Both go through `run_tool` and `ToolRegistry.execute`, with the same policy check, timeout and error capture. Only the `approved` argument differs.

**Q37. How do you guarantee the refund runs exactly once?**
An action row already `executed`, `failed` or `skipped` is not run again, and a second approve is 409. `test_approve_resumes_and_runs_the_refund_exactly_once` and `test_deciding_twice_is_409_and_does_not_run_the_refund_again` assert one refund row and one execution.

**Q38. What if the tool fails after approval?**
The registry returns `ToolResult(ok=False)`, never an exception. The action is marked `failed` with the error, the graph continues, and the failure is visible in the trace. There is no retry route yet.

**Q39. What does the refund amount come from?**
`ResolutionAgent.plan_actions` computes it deterministically: unused seats times seat price. For CD-1002 it is 3 times 15.00, which is 45.00. The model does not invent actions or amounts.

**Q40. Is the approved refund linked to its approval?**
Yes. The pause creates the action row with `approval_id`. `test_approved_refund_is_a_database_record_with_the_approval_linked` checks the link.

**Q41. What do the approval settings do?**
`APPROVAL_REQUIRED_FOR_REFUNDS` and `MAX_REFUND_WITHOUT_APPROVAL` feed `ToolPolicy.requires_approval`. With defaults (true and 0) every refund needs approval. `reset_demo_setting` always does.

---

## E. Rejection

**Q42. What happens on reject?**
The decision is stored, the graph resumes, `route_after_approval` sends it to `escalation`, the waiting refund is set to `skipped` (shown as `rejected`), an escalation to `support_leads` is filed with the approver's note in the reason, and the ticket becomes `escalated`. `test_reject_escalates_and_never_runs_the_refund`.

**Q43. Why escalate on rejection instead of just closing it?**
A rejected plan means the AI's proposal was wrong or unsafe, but the customer still has a problem. A person must own it. Escalation is the safe path and needs no approval.

**Q44. Could a rejected refund run later?**
Not through this run. Its action is `skipped` and the approval is `rejected`. A new run would plan a new action and need a new approval.

---

## F. Escalation

**Q45. Which tickets escalate and why?**
Policy cases decided by `agents/rules.py`: CD-1005 (security), CD-1006 (data loss), CD-1009 (account deletion, GDPR) and CD-1011 (payment dispute). `test_policy_tickets_escalate_without_waiting_for_approval` runs all four.

**Q46. Who decides: the rules or the model?**
The rules (CLAUDE.md 7.2). `EscalationAgent.run` always lets a matched rule win. The model only judges grey areas, and a vague model escalation is distrusted. Offline, the model never volunteers one.

**Q47. What does the `escalation` node do?**
It builds the decision (policy or rejection), checks whether an escalation was already filed for this run, files it with `EscalationAgent.file` (the `create_escalation` tool through `ToolRegistry`, which also notifies the team through the mock adapter), then sets the ticket to `escalated` with `update_ticket`, also through the registry.

**Q48. Why is escalation not approval-gated?**
CLAUDE.md 7.4 calls `create_escalation` "the safe path". It moves work to people and never spends money or changes an account.

**Q49. Why does policy beat approval in routing?**
`choose_route` checks `escalation_required` first. A suspected breach should reach the security team immediately, not wait in an approval queue. `test_policy_escalation_beats_approval_in_routing` (from Phase 10) still pins it.

**Q50. Why does escalation skip `execute_resolution`?**
No actions should run on a case a person must own. Escalation goes straight to `ticket_summary`. The only change the node makes itself is the ticket status.

**Q51. What if the escalation node runs twice?**
It looks up `EscalationRepository.for_workflow` and reuses the existing row. `test_escalation_is_filed_once_per_run`.

**Q52. How does an escalated run show up in the API?**
`workflow_view` reports a completed run that filed an escalation as `escalated`, which is in the contract's status list. The ticket detail embeds the escalation.

**Q53. Is anyone really notified?**
No. `notify_team` is a mock in `integrations/`. v1 has no real email by design. A real adapter would sit behind the same Protocol.

---

## G. Safety and security

**Q54. Can the AI approve its own refund?**
No. An approval is created `pending` by the service and can become `approved` only through the approve route, which needs an `agent` or `admin` token. Nothing in the graph writes an approved row.

**Q55. What stops a prompt-injected ticket?**
Three layers from earlier phases still apply: `wrap_untrusted` and the security preamble, the injection scan, and deterministic action planning. `plan_actions` plans no money or export action when injection is detected. CD-1013 therefore has nothing to approve and no export tool exists. `test_prompt_injection_ticket_neither_exports_nor_waits`. It is still rated high risk.

**Q56. Can a viewer approve?**
No, 403, and the request stays pending. An unauthenticated call is refused too (`test_approvals_need_a_token`).

**Q57. Is the approval trail auditable?**
Yes, three ways: the `approval_requests` row (who, when, note), the trace events `approval_requested` and `approval_resolved` plus the traced tool call, and the audit log for the POST. `test_approve_records_the_decision_in_the_trace`.

**Q58. Does the trace leak private data?**
The trace stores names, statuses, timings and token counts, never prompts or ticket bodies. The approval payload does contain the planned action's arguments (customer id, amount), because the reviewer needs to see them. That is in the database and the approvals API, not in the event log.

**Q59. Could the decision note be abused?**
It is free text from an authenticated agent, capped at 1000 characters, stored on the approval and copied into the escalation reason on rejection. It is not sent to the model, not stored in customer memory, and not shown to customers. It is not scrubbed for secrets, which is a small gap if an agent pastes one.

**Q60. What happens to risk levels in this phase?**
Unchanged: `high` for an approval-required plan, a policy escalation, critical severity, injection, or failed output validation. Those are exactly the cases that now pause or escalate.

---

## H. Testing

**Q61. What tests did you add?**
28 new tests, 408 in total, all offline. 26 are in `tests/workflow/test_approval_escalation.py` (pause, resume, 409s, 403, 404, reject, four policy tickets, idempotency, trace, the database link) and 2 are in `test_graph_and_risk.py` (route targets and the fail-safe approval route). I also updated the Phase 10 tests whose expectations changed: the refund ticket now pauses and the policy ticket now escalates.

**Q62. Why does each pause test create its own refund ticket?**
The test database is shared for the whole session. A paused ticket returns 409 to a second run, so each test copies CD-1002's customer and text into a **new** ticket (`_new_refund_ticket`).

**Q63. How do you test database state from a sync test?**
The app's engine lives on the test client's event loop, so tests call `client.portal.call(coroutine)` to run database code on that same loop. Plain async tests would use a different loop than the engine.

**Q64. How do you test "not paused" 409?**
`test_resuming_a_run_that_is_not_paused_is_409` forces the run to `completed` through the repository while the approval is still pending, then approves and expects `Workflow is not waiting for approval`.

**Q65. Did the tests catch a real bug?**
Yes. Approve first returned `workflow.status: "running"` for a finished run, because the request session had a stale cached row. `expire_all()` fixed it.

**Q66. Is anything untested?**
Restart-resume from the SQLite checkpoint, a crash mid-resume, true concurrent double clicks (the claim logic is tested by a sequential double click), a real LLM provider, and the `make` target itself.

---

## I. Design trade-offs and honest answers

**Q67. Why LangGraph `interrupt()` and not a status column plus a second workflow?**
`interrupt()` resumes at the exact node with the whole state, so I do not hand-write "which step was I on" logic. The cost is learning the replay rule (code before it runs again), and relying on a checkpointer.

**Q68. Why record the approval in the service rather than the graph?**
It keeps the node pure (replay-safe) and puts run and ticket status changes next to each other in one transaction.

**Q69. Why store both a checkpoint and `workflow_runs.state`?**
Different jobs. The checkpoint is LangGraph's own snapshot for resuming. `workflow_runs.state` is the JSON the screen polls and the audit record. They are linked by `thread_id`.

**Q70. What is the weakest part of Phase 11?**
Operational resilience: no restart test, no retry if a resume crashes after an approval, resume running inside the request, and a SQLite checkpointer that cannot be shared by replicas. The logic of "no money without an approval" is the strongest part and the most tested.

**Q71. What would you do for multiple replicas?**
Use a shared checkpointer (a Postgres saver), move runs and resumes to a worker with a queue, and make `create_run` take a database-level lock or unique constraint on active runs.

**Q72. What would you add next for approvals?**
Expiry of stale requests, a retry route for a failed resume, several approvers or an amount threshold, notification of the reviewer, and the console buttons in Phases 12 and 13.

**Q73. Is the system deployed?**
No. Nothing is deployed and no cloud credentials were used. Docker, Compose and Terraform come in Phase 13. Everything here is validated locally and offline.

**Q74. What is the one thing you want the board to remember?**
No refund or account change can run without a recorded human approval, and the policy cases never wait in a queue: both are decided by written rules and proven by tests.

---

## J. Quick-fire

| Question | Answer |
|---|---|
| Node that pauses | `human_approval` |
| Node that files escalations | `escalation` |
| How many graph nodes now | 12 |
| Approval statuses | `pending`, `approved`, `rejected` |
| Run status while paused | `waiting_on_approval` (shown as `waiting_for_approval`) |
| Ticket status while paused | `waiting_on_approval` |
| Default escalation team after a rejection | `support_leads` |
| Who may approve | `agent`, `admin` |
| 403 for | `viewer` on approve and reject |
| 409 for | second run while paused, second decision, run not paused |
| Tool for escalation | `create_escalation` through `ToolRegistry` |
| Demo command | `make demo` or `python scripts/demo.py CD-1002` |
| CD-1002 refund amount | 45.00 |
| Tests | 28 new, 408 total, offline |
