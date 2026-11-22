# Phase 10 Interview Q&A: Workflow Graph and Trace

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code.

---

## A. Big picture

**Q1. What did you build in Phase 10?**
The LangGraph workflow that runs the six specialists as ten nodes in a fixed order (`agents/graph.py`, `agents/nodes/`), the shared state with reducers (`agents/state.py`), a checkpointer (`agents/checkpointer.py`), a risk function (`agents/risk.py`), the `WorkflowTracer` that writes `workflow_events` (`backend/app/core/observability.py`), the workflow service and view (`services/workflow_service.py`, `workflow_view.py`), and two routes: `POST /tickets/{id}/run` and `GET /tickets/{id}/workflow`.

**Q2. Which requirements does it cover?**
F11 (ticket summary and memory update after every run), F13 (every node, tool call and LLM call inspectable with timing and tokens), the graph shape in CLAUDE.md 7.3, and the request flow in 4.1 steps 1 to 4. It also finishes the offline demo path for F14 end to end.

**Q3. Which tasks were in the phase?**
P10-1 state and checkpointer, P10-2 supervisor nodes, P10-3 investigate nodes, P10-4 resolution and risk nodes, P10-5 graph wiring and run API, P10-6 tracer and events API.

**Q4. Is Phase 10 the same as "Phase 9" in PLAN_PHASE.md?**
Yes. `TASKS.md` pulled memory forward, so from there its numbers are one ahead. TASKS Phase 10 is PLAN_PHASE Phase 9, "Workflow graph and trace". TASKS Phase 11 is the approval and escalation phase.

**Q5. What is the demo checkpoint?**
`POST /tickets/CD-1010/run` returns 202, and polling `/workflow` reaches `completed` with all ten nodes listed. `test_low_risk_ticket_runs_to_the_end`.

**Q6. Can the workflow pause for a human approval yet?**
No. That is Phase 11. In Phase 10 an approval-required action is recorded as `awaiting_approval` and not executed. I say this plainly so nobody thinks refunds are automated.

**Q7. Does a policy case create an escalation yet?**
No. `risk_check` detects it by rule, sets `escalation_required` and `route="escalation"`, and rates the risk high. Filing the escalation row and notifying the team is Phase 11. The tests only claim detection.

---

## B. Why LangGraph, and the shape of the graph

**Q8. Why a graph instead of calling the agents in a normal function?**
A graph gives three things for free that I would otherwise hand-write: a typed shared state with reducers, a checkpoint after each step, and pause and resume (`interrupt`) for the Phase 11 approval. It also makes the order explicit and testable as data (`GRAPH_NODES`, `GRAPH_EDGES`).

**Q9. Does a model decide which node runs next?**
No. The order is fixed by us. The only branch is after `risk_check`, and it reads a `route` value produced by rules (`choose_route`). A model never picks the path.

**Q10. What are the ten nodes?**
`understand_ticket`, `classify_severity`, `customer_context`, `knowledge_retrieval`, `troubleshooting`, `resolution_planning`, `risk_check`, `execute_resolution`, `ticket_summary`, `memory_update`. `test_graph_nodes_are_in_pipeline_order` pins them.

**Q11. The target design has `human_approval` and `escalation` nodes. Where are they?**
Not in Phase 10. `ROUTE_TARGETS` in `agents/graph.py` maps `low`, `approval` and `escalation` to a node. In Phase 10 all three point to `execute_resolution`. In Phase 11 two entries change; the rest of the graph does not.

**Q12. Why wire the conditional edge now if every route goes to the same node?**
So the routing logic, the `route` value and its tests exist and are proven before Phase 11 changes the targets. `test_every_route_has_a_target` and `test_policy_escalation_beats_approval_in_routing`.

**Q13. Why is that safe?**
Two layers. `execute_resolution` does not call a tool that needs approval; it records it as `awaiting_approval`. Even if it tried, `ToolRegistry.execute` refuses an approval-required tool unless `approved=True`, and nothing in Phase 10 sets that flag.

**Q14. Where is `ticket_summary` in the order, and why after execute?**
After `execute_resolution`, because the summary describes the outcome ("reply drafted for agent review", "waiting for human approval", "policy escalation needed"). It is built from our own outputs, not the raw ticket body.

**Q15. Why does `memory_update` come last?**
It records what was learned (issue summary, first three steps, resolution note) once the plan exists. It is best effort. If memory fails, the failure is appended to `errors` and the run still completes.

---

## C. State and reducers

**Q16. What is `SupportState`?**
A `TypedDict` in `agents/state.py`. It carries identity (ticket, customer, plan, subject, body), each specialist's output, the risk and route, and three reducer fields. Every node returns only the keys it owns.

**Q17. What is a reducer and which ones do you have?**
A rule for merging a node's return value into the existing value. `errors` and `completed_nodes` append (`operator.add`). `token_usage` sums through `merge_usage`. Everything else is replaced by the node that owns it.

**Q18. Why must `errors` and `completed_nodes` append, not overwrite?**
CLAUDE.md rule 9. An overwrite could erase an earlier error or the history of which steps finished. `test_state_reducers_are_declared` checks the annotations, and `test_token_usage_reducer_sums` checks the sum.

**Q19. Why plain dicts in state instead of Pydantic objects?**
State is stored by the checkpointer and in `workflow_runs.state` (JSON). Dicts serialise safely. Nodes rebuild typed models with small helpers in `agents/nodes/common.py` (`classification_of`, `plan_of`, and so on) and write back with `model_dump(mode="json")`.

**Q20. Does the state hold large documents?**
No (rule from CLAUDE.md). It holds evidence snippets and short lists, not whole articles.

**Q21. Is any other customer's data in the state?**
No, deliberately. `resolution_planning` needs other customers' names to block a reply that leaks them. It computes that list, passes it to the agent, and does not save it. State is exposed through `/workflow`, so storing it would itself be a leak.

---

## D. The checkpointer

**Q22. What does the checkpointer do?**
LangGraph saves a snapshot of the state after each step under a `thread_id`. This lets a paused run resume where it stopped. Phase 11 relies on it for approval. In Phase 10 it is wired and used, but nothing resumes yet.

**Q23. Which implementation is used when?**
`get_checkpointer()`: `InMemorySaver` when `CHECKPOINT_DB_PATH` is empty or `:memory:` (tests), otherwise `AsyncSqliteSaver` on a file. The SQLite connection is created lazily inside the running event loop and closed in the app lifespan by `close_checkpointer()`.

**Q24. Did you have to add a dependency?**
Yes, `langgraph-checkpoint-sqlite` (with `sqlite-vec` as a transitive dependency) through `uv add`, so `pyproject.toml` and `uv.lock` changed. It was missing from the environment.

**Q25. Is the SQLite saver tested?**
Only the in-memory saver runs in the test suite. I imported the SQLite saver successfully, but I have not tested a file-backed run. I would not claim that path is proven.

**Q26. Why have both `workflow_runs.state` and a checkpointer?**
Different jobs. `workflow_runs.state` is **our** table: it feeds the polling UI and the audit view in the shape of `API_CONTRACT.md`. The checkpointer is **LangGraph's** internal snapshot for pause and resume. I keep them separate so the API contract does not depend on LangGraph's storage format.

---

## E. The tracer (F13)

**Q27. What does the tracer record?**
`node_started`, `node_completed` (with duration), `tool_called` (name, status, duration), `llm_called` (token counts, cost, duration), `error`, and `workflow_completed`, all into `workflow_events`.

**Q28. What does it never record?**
Raw prompts, ticket bodies, tool arguments, secrets, and hidden reasoning. Only names, statuses, sizes and timings. `test_events_never_contain_raw_prompts_or_body` checks that the injection ticket's text and the `untrusted_content` tag do not appear in any event payload.

**Q29. What happens if the event table cannot be written?**
Nothing visible to the customer. `emit` catches every exception, logs a warning, and returns. `test_telemetry_failure_does_not_raise` forces the repository to fail and checks no exception escapes, including through the `node()` context manager.

**Q30. Why does the tracer use its own database session?**
So an event write is its own small transaction. A failed event cannot roll back real work such as a ticket update, and a failed node's error event is still saved even though the node raised.

**Q31. What does a failing node produce in the trace?**
`node_started`, then an `error` event with the node name and the **exception type only**, then the exception continues up and the run is marked `failed`. `test_failed_node_marks_run_failed`.

**Q32. How does the specialist's tool-call record reach the trace?**
Phase 9 made each specialist return `AgentResult` with a list of `ToolCallRecord`s. The node passes them to `tracer.tool_calls`. Specialists know nothing about tracing, which keeps them testable alone.

**Q33. Where do events show up for the user?**
`GET /api/v1/tickets/{id}/events` (built in Phase 4, empty until now). It reads `payload["tool"]` and `payload["message"]` from each row, which is why the tracer puts those keys in the payload.

**Q34. What about cost?**
Each LLM event stores input tokens, output tokens and estimated cost. With the fake provider cost is `0.0`. Pricing is not tracked for real providers in v1, so cost is an estimate field only.

**Q35. Is LangSmith wired?**
No. Our own `workflow_events` are the trace. LangSmith is optional in CLAUDE.md and not built.

**Q36. Could event order be ambiguous?**
Events are sorted by `created_at` then `id`. Within one run steps are sequential, so timestamps normally separate them. The id is a random UUID, so two events in the same instant could swap. If that appeared, I would add a sequence column.

---

## F. The run API and background execution

**Q37. Why return 202 instead of waiting for the result?**
The workflow can take seconds with a real model. A 202 returns immediately and the UI polls `/workflow` every two seconds. This is the flow in CLAUDE.md 4.1.

**Q38. How does the background run actually start?**
The route calls `workflow_service.create_run`, then `BackgroundTasks.add_task(start_workflow, run.id)`. FastAPI runs the task after the response is sent.

**Q39. What did you have to be careful about with the database commit?**
The background task opens its own session. If the run row were not committed first, the task could not find it. `create_run` calls `session.commit()` before returning so the row is visible.

**Q40. When do you return 409?**
When the ticket's status is `waiting_on_approval` ("Ticket is waiting on approval"), or the latest run is still `running` ("A workflow is already running for this ticket"). `test_run_is_409_while_waiting_on_approval` covers the first.

**Q41. Is the "already running" 409 tested?**
Not directly. The test client finishes background tasks before returning, so a run is never still active when the next request arrives. The branch is simple code, but I have not proven it with a test, and I would say so.

**Q42. What if the server restarts mid-run?**
The run row stays `running`, so the ticket returns 409 on the next `/run`. I have not built a timeout or a startup sweep. It is listed as a known gap.

**Q43. Who may call these routes?**
`/run` needs `agent` or `admin` (a viewer gets 403, `test_viewer_cannot_run_but_can_read`). `/workflow` and `/events` need `viewer` or above. Unknown tickets return 404.

**Q44. What does `/workflow` return?**
The `WorkflowState` JSON in `API_CONTRACT.md`, built by `workflow_view.build_view` from the latest run plus its `resolution_actions`. If the ticket never ran, 404 "No workflow has run for this ticket". The same object is embedded in `TicketDetail.workflow`.

**Q45. Why a separate `workflow_view` module?**
`ticket_service` needs to embed the latest run in `TicketDetail`, and `workflow_service` needs `ticket_service` to find tickets. A third module that both import avoids a circular import.

**Q46. Does the status match the contract?**
The database uses `RunStatus` (`pending`, `running`, `waiting_on_approval`, `completed`, `failed`). `workflow_view` maps those to the contract's `running`, `waiting_for_approval`, `completed`, `failed`. The contract's `escalated` is never produced yet.

**Q47. How is state saved after every node?**
`start_workflow` streams the graph with `stream_mode="values"`, which yields the full state after each step, and `_save` writes it to `workflow_runs.state` each time. That is why a poll in the middle of a run shows partial progress.

**Q48. What happens when something throws?**
`start_workflow` never raises. It logs, sets the run to `failed`, and stores the exception **type** in `error`. The server keeps serving. The type, not the message, avoids leaking data.

---

## G. Risk and routing

**Q49. When is the risk "high"?**
Any of: a planned action needs approval, a policy escalation rule matched, severity is critical, injection was suspected, or output validation failed. `medium` for high severity, otherwise `low`. `assess_risk` in `agents/risk.py`, tested case by case in `test_risk_high_triggers`.

**Q50. Is risk decided by the model?**
No. Pure rules, no model call. The escalation agent's policy decision feeds into it, and that is also rules-first.

**Q51. What is the difference between risk and route?**
Risk is a label for people ("how worried should we be"). Route is the machine decision ("where does the graph go next"). Route order: policy escalation beats approval, approval beats low (`choose_route`).

**Q52. Why does policy escalation win over approval?**
A hacked-account ticket should go to a specialist team, not wait on a refund click. Rules first, CLAUDE.md 7.2.

**Q53. What does `risk_check` do with the Escalation agent?**
It calls `EscalationAgent.run` with the subject, body, plan name and severity. Policy rules always win. The model can only add a judgement in grey areas, and a vague model escalation is distrusted.

---

## H. Safety and the demo tickets

**Q54. What happens to the refund ticket (CD-1002)?**
All ten nodes run. The plan has `create_refund_request` with `requires_approval=True`. `execute_resolution` stores it as `awaiting_approval`, never runs it, the API shows `pending_approval` with `result: null`, and risk is high. `test_refund_is_held_not_executed`.

**Q55. How do you prove the refund did not run?**
The action row has no result and status `pending_approval`. The tool also would have been refused by the registry. I check the API output; I do not yet query the mock billing adapter's call log.

**Q56. And the suspected breach (CD-1005)?**
`escalation_required` is true, risk is high, and no refund action is planned. `test_policy_ticket_is_high_risk_and_flagged`. No escalation row is filed in Phase 10.

**Q57. And the prompt injection (CD-1013)?**
The ticket text is wrapped as data, the injection flag is set, risk is high, and only `update_ticket` can be planned: no export, no refund. `test_injection_ticket_plans_no_money_or_export_action`.

**Q58. Does a flagged ticket still get processed?**
Yes. A customer with a real problem and a pasted attack still gets the real problem handled. Flagging suppresses risky actions and raises risk to high.

**Q59. Which actions do auto-run?**
Only `update_ticket` (category, severity, summary, status `in_progress`). It needs no approval by policy. The action goes through `ToolRegistry.execute`, the same path Phase 11 will use for approved actions.

**Q60. Is `execute_resolution` safe to run twice for one run?**
Yes. It lists the run's recorded actions and skips any tool already recorded. That protects against double execution if a step re-runs.

**Q61. And running a ticket twice (two separate runs)?**
Each run has its own id and its own action rows, so `update_ticket` runs again. That is harmless. A refund would be held again as a new pending request, which Phase 11 should de-duplicate. Not handled yet.

**Q62. Does a failing tool crash the run?**
No. The registry turns exceptions and timeouts into `ToolResult(ok=False)`. `execute_resolution` marks that action `failed` with the error text and continues.

---

## I. Memory and the loop

**Q63. How does a run use long-term memory?**
`customer_context` recalls up to ten notes through the Customer agent. `memory_update` writes a past issue, up to three steps and a resolution note via `MemoryService.record_resolution`, scrubbed and de-duplicated.

**Q64. Is that proven?**
`test_second_run_recalls_memory_written_by_the_first`: a second run's `customer_context` contains notes written by the first, with no errors.

**Q65. Could memory hold the raw ticket?**
No. The node passes only the classification's one-line summary, diagnosis steps and plan summary, never the body.

---

## J. Testing

**Q66. What tests did you add?**
26 new tests in `tests/workflow/`: `test_graph_and_risk.py` (graph shape, route targets, risk triggers, routing order, reducers, serialisation) and `test_run_api.py` (run, poll, events, held refund, policy, injection, 409, 403, 404, telemetry failure, failed node). Total suite: 380 passing, all offline.

**Q67. How do the API tests get a finished run immediately?**
The Starlette test client waits for background tasks before returning, so the workflow is complete when `POST /run` returns. The tests still read the result through `/workflow`, as the UI would.

**Q68. Do tests need an API key or Docker?**
No. Fake LLM provider, in-memory vector store, fakeredis, a temp SQLite file and an in-memory checkpointer.

**Q69. What is not tested?**
A file-backed SQLite checkpointer, the "already running" 409, a real LLM provider, and pause/resume (Phase 11). Concurrent runs on different tickets are not exercised either.

**Q70. How did you test the failure path without breaking real code?**
I replaced `TroubleshootingAgent.run` with a function that raises, using `monkeypatch`. The real node and tracer run, so I can assert the run is `failed`, the node is not in `completed_nodes`, and an `error` event names the node.

---

## K. Architecture and trade-offs

**Q71. How did you keep the layering rules?**
`core/observability.py` does not import `agents/`; nodes import it. Nodes use repositories and the tool registry, never raw SQL. The service layer starts the graph; the API layer only does HTTP, auth and scheduling.

**Q72. Why is the tracer in `core` and not in `agents`?**
It writes to the database through repositories and is useful beyond agents (approvals in Phase 11 also emit events). `core` may be used by `agents`, but not the reverse.

**Q73. Why run workflows in-process with `BackgroundTasks`?**
It is the v1 design in CLAUDE.md: simple, no queue to operate. The cost is that a restart cuts running work and replicas do not share runs. A worker is the production extension.

**Q74. How would you scale this?**
Move `start_workflow` to a worker consuming a queue, switch to a Postgres checkpointer so any worker can resume any thread, add a run lease or heartbeat so crashed runs are detected, and keep the API stateless.

**Q75. What would you improve first?**
Three things. A stale-run timeout so a crash cannot block a ticket. A sequence number on events for strict ordering. A test for the file-backed checkpointer.

**Q76. Why not let the model choose tools and loop (a ReAct agent)?**
For policy, money and accounts I want a fixed, auditable path with a known worst case. The model fills in wording and grey-area judgement. Predictability beats flexibility here.

**Q77. What is the biggest risk in this phase?**
Overclaiming. The graph is complete for a low-risk ticket, but approvals and escalation are only detected, not acted on. The honest status is in `design_evolution` and in the contract notes.

**Q78. How would you explain the whole phase in one sentence?**
Phase 10 turns six isolated specialists into one ten-step workflow that saves its state after every step, records a private audit trail of everything it does, rates risk by rules, and holds back any money or account action until Phase 11 adds the human.

---

## L. Likely follow-ups and tricky questions

**Q79. "If risky actions are recorded but not executed, doesn't the ticket end up in limbo?"**
Yes, in Phase 10 the run completes with the action shown as `pending_approval` and nothing moves it forward. That is the intended stopping point; Phase 11 adds `human_approval`, the approvals API and resume so a person can release it.

**Q80. "Why does the ticket status become `in_progress` even for a held ticket?"**
Because `update_ticket` is a harmless planned action that always runs. The `waiting_on_approval` status is owned by the workflow in Phase 11, which is why `/run` already checks for it.

**Q81. "Could two people press Run at once?"**
The second is rejected with 409 if the first run is already recorded as running. There is a small window between the check and the insert; I do not take a database lock. A unique constraint on an active run per ticket would close it. Not built.

**Q82. "What stops the AI reading someone else's customer?"**
The Customer agent is scoped to this customer's id, the leak check uses other customers' names, and that list is never stored. Tools are the only data path, through the registry.

**Q83. "How do you know the trace is complete?"**
Every node uses the same `async with tracer.node(...)` pattern, so start and end are guaranteed events, and tool and LLM events come from the specialists' own records. The test checks the event kinds and that every completed node has a duration.

**Q84. "What did the checkpointer cost in complexity?"**
One module, one dependency and one shutdown hook. The cost is repaid in Phase 11 when pause and resume are needed.

**Q85. "Does the response to `/run` contain the result?"**
No, only `{workflow_id, status: "running"}`. The result is read from `/workflow`.
