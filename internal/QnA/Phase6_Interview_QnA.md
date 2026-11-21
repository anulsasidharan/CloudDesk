# Phase 6 Interview Q&A: Tools and Policy

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code.

---

## A. Big picture

**Q1. What did you build in Phase 6?**
The toolbox the agents will use and the gate in front of it. Nine registered tools, a `ToolPolicy` that says which need human approval, a `ToolRegistry` that is the only way to run them, and mock integrations for billing, email, notifications and workspace admin.

**Q2. Which requirement does it cover?**
F9, the policy half: consequential actions need human approval. The approval screen and pause/resume are Phase 10. Phase 6 guarantees the tool layer refuses until told a human approved.

**Q3. Why not let the agent call functions directly?**
Then every agent would need its own safety checks, and one forgotten check is a refund nobody approved. A single registry means one place to enforce policy, timeouts and error handling. It is the "one service window" idea. See `backend/app/tools/registry.py`.

**Q4. Is the AI using the tools yet?**
No. Agents come in Phase 8 and the workflow in Phase 9. Phase 6 is built and tested on its own. I say that plainly to avoid overclaiming.

**Q5. What is the demo checkpoint?**
A direct registry call to `create_refund_request` without `approved=True` writes no refund. A test checks that the billing mock's call log is empty.

---

## B. Policy

**Q6. Who decides whether a tool needs approval?**
Code, not the model. `ToolPolicy.requires_approval(name, args)` in `policy.py`. This follows the project rule "rules first, LLM second": policy cases are deterministic and tested, never left to model probability.

**Q7. Which tools need approval?**
`create_refund_request` (money) and `reset_demo_setting` (account change). The five read tools, `update_ticket` and `create_escalation` do not.

**Q8. Why does escalation not need approval?**
It is the safe path. Handing a case to a human team is the cautious choice, so we make it frictionless.

**Q9. What happens to a tool name nobody registered?**
Unknown tools always require approval. Without approval the result is `approval_required`; with approval it is `unknown_tool`. This is deny-by-default.

**Q10. The refund policy reads settings. How?**
If `APPROVAL_REQUIRED_FOR_REFUNDS` is true (default), every refund is gated. If it is false, a refund is gated when the amount exceeds `MAX_REFUND_WITHOUT_APPROVAL`, which defaults to 0, so any positive amount is still gated. A bad or missing amount is treated as needing approval.

**Q11. Could a prompt-injected ticket make the AI skip approval?**
The model does not control the `approved` flag. Only the workflow sets it after a recorded human decision (Phase 10). Ticket text cannot flip it. The injection defences themselves arrive in Phase 7.

**Q12. Is the approval check the only safeguard on refunds?**
No, it is defence in depth: role check on the API (agents and admins only, Phase 3), tool policy (Phase 6), recorded approval (Phase 10), and the refund itself is a mock in v1.

---

## C. The registry

**Q13. Walk me through `execute`.**
1. Ask the policy if approval is needed. 2. If yes and not approved, return `approval_required`, run nothing. 3. Look up the tool; if missing, `unknown_tool`. 4. Run it inside `asyncio.wait_for` with `TOOL_TIMEOUT_SECONDS`. 5. Wrap success, timeout or exception into a `ToolResult`.

**Q14. Why return a result instead of raising?**
Tool failures must never crash the graph (CLAUDE.md 7.4). A failure is information the workflow and the trace can record, and the agent can decide what to do with it.

**Q15. What does `ToolResult` contain?**
`tool`, `ok`, `status` (`ok`, `approval_required`, `error`, `timeout`, `unknown_tool`), `requires_approval`, `executed`, `data`, `error`. The `executed` flag lets a test prove nothing ran.

**Q16. How is the timeout enforced, and how do you test it?**
`asyncio.wait_for` around the tool call, with the value read from settings at call time. The test registers a tool that sleeps five seconds, sets `TOOL_TIMEOUT_SECONDS=0.05`, and expects status `timeout`.

**Q17. Why read settings at call time rather than at import?**
So a changed setting (and tests that clear the settings cache) take effect without re-importing modules.

**Q18. Why use LangChain's `@tool`?**
The docstring becomes the description an LLM or an MCP client sees, and the type hints become the argument schema, so agents can bind the tools later without extra glue. The registry calls `ainvoke`.

**Q19. What is `registry.specs()` for?**
It lists each tool's name, description and approval bit. It is ready for the `/mcp/tools` endpoint and for the UI. That endpoint is not built yet.

**Q20. Can you register the same tool twice?**
No, it raises `ValueError`. Silent overwrite of a tool would be a security hole.

---

## D. The tools

**Q21. What are the read-only tools?**
`get_customer`, `get_subscription`, `get_ticket_history`, `search_docs`, `check_service_status`. They call existing repositories and the Phase 5 retriever. No new SQL, no new search logic.

**Q22. Where is the SQL?**
Only in repositories. Tools call them. That keeps the layering rule: repositories own SQL, tools never contain it.

**Q23. Why does `search_docs` return the evidence dict with a `kb://` source?**
Because customer-facing policy claims must be cited. Reusing `Evidence.to_dict()` keeps one citation format across the system.

**Q24. What does `update_ticket` protect against?**
Bad values. Category, severity and status are validated against the enums, and the database also has check constraints. A made-up category returns a failed result.

**Q25. What does `create_escalation` do?**
Saves an `escalations` row and notifies the named team through the notification adapter. Returns the escalation id and the notification id.

**Q26. What does `create_refund_request` do?**
Checks the amount is positive, reads the customer's subscription currency, and asks the billing adapter to create a refund. In v1 that adapter is a mock, so no money moves.

**Q27. What does `reset_demo_setting` guard against?**
Only three settings are allowed: `external_sharing`, `mfa_required`, `sso_enabled`. Anything else is refused even with approval. The tool changes the workspace row and calls the workspace-admin adapter.

**Q28. Do the write tools themselves check approval?**
No. They assume the registry did. The module says never call them directly. This is why "no tool bypasses the registry" is a rule, and why the registry is the only thing exported for execution.

---

## E. Integrations

**Q29. Why mock integrations?**
Non-goals for v1: no real emails, no real refunds. Mocks keep demos safe and tests offline.

**Q30. What is a Protocol and why use one?**
A Python interface: it lists the methods a service must have. Tools depend on the protocol, so replacing the mock with a real provider means one new adapter and a change in `factory.py`. No tool changes.

**Q31. How do tests prove a refund did not happen?**
Each mock records its calls in a list. The test asserts the billing list is empty after a blocked call and has one entry after an approved call.

**Q32. Why is the factory cached, and why a reset function?**
`lru_cache` gives one adapter instance per process so call logs persist across calls. `reset_integrations()` clears them so each test starts empty.

**Q33. Does `core` import integrations?**
No. That would break the layering rule. Only tools import the factory.

---

## F. Testing

**Q34. How many tests did Phase 6 add?**
28 in `tests/unit/test_tools.py`. The full suite is 192 passed, offline.

**Q35. How do the tests get a database?**
A fixture builds a private in-memory SQLite database seeded with the real demo data, and monkeypatches the one `tool_session` seam. They never touch the real database file.

**Q36. Name key behaviours the tests prove.**
Reads need no approval; refund and reset need it; unknown tools need it; a blocked refund writes nothing; the approved refund uses the same path; exceptions become `ok=False`; timeouts become `timeout`; an unlisted setting is refused; escalation writes a row and notifies; duplicate registration is refused.

**Q37. Does a test cover the settings-driven refund rule?**
Yes: with `APPROVAL_REQUIRED_FOR_REFUNDS=false` and a max of 0, even a one-dollar refund is still gated.

**Q38. How do you test `search_docs` offline?**
Index the real 15 articles into a private in-memory store and point the retriever at it. A query about MFA lockout returns evidence with a `kb://` source.

---

## G. Trade-offs and "what would you change?"

**Q39. Why does each tool open its own session?**
Tools run later from background workflow tasks, outside a request, so there is no FastAPI session to inherit. A short unit of work per call keeps transactions small. Trade-off: a multi-tool step is not one transaction.

**Q40. Weakness: the approval flag is a plain boolean.**
Correct. In Phase 10 the workflow only sets it after reading a recorded `approval_requests` row. I would also consider having the registry verify an approval id rather than trust a boolean from the caller.

**Q41. What about idempotency? Could an approved refund run twice?**
Not guarded yet. Phase 10 should record a `resolution_actions` row per action and skip one already executed. I would also pass an idempotency key to a real billing provider.

**Q42. What would you add for production?**
Real adapters with retries and secrets from a secret manager, per-tool audit rows, rate limits per tool, and a `/mcp/tools` endpoint to list specs. Also a CI check that production keeps refund approval on.

**Q43. Why not put policy in the prompt ("do not refund without approval")?**
A prompt is a request, not a guarantee. A model can be tricked or simply wrong. Code that runs before the tool is a guarantee, and it is testable.

**Q44. Why are tools in `backend/app/tools` but integrations at the repo root?**
Tools are application logic in the backend. Integrations are a standalone seam, like `rag/`, that could be reused by the MCP server and the workflow. The rule is that `core` must not import them.

**Q45. What is honestly not done?**
Nothing calls the tools yet; no approval screen; no `resolution_actions` rows; no `/mcp/tools` route; no real providers; nothing is containerised or deployed.
