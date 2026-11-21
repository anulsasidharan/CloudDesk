# Phase 4 Interview Q&A: Support API

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code so you can back it up.

---

## A. Big picture

**Q1. What did you build in Phase 4?**
The REST API agents use to work with tickets and customers: create, list, search, open, update, reply, ask the customer for info and escalate tickets; and list and open customers with their plan, workspaces, tickets and memory notes. All behind the Phase 3 roles.

**Q2. Which requirements does it cover?**
F1 (create a ticket from email, chat, web or API) and the read side of F4 (customer, subscription, workspace, previous tickets), plus the rule that the contract, schemas and types are written together.

**Q3. Why does creating a ticket not start the AI workflow?**
Recording a problem must not depend on the AI being healthy or on the model's latency. Run is a separate endpoint (Phase 10) that returns 202 and works in the background. The contract says this, and a test checks a new ticket has no category or severity.

**Q4. What is deliberately missing?**
`/run`, `/workflow`, approvals, knowledge, dashboard, agents, audit and settings routes. Also reply safety checks (output validation is Phase 7). They are not mounted, so they return 404 rather than pretending.

---

## B. Architecture and layering

**Q5. How is the code layered?**
API (`api/tickets.py`, `api/customers.py`) handles HTTP, auth and error mapping. Services (`ticket_service`, `customer_service`) hold the rules. Repositories hold all SQL. The restaurant picture: waiter, chef, pantry clerk.

**Q6. How do the layers talk about errors?**
Services raise domain exceptions (`TicketNotFoundError`, `TicketClosedError`, `ProfileNotFoundError`); the route turns each into the right HTTP status. So the service never imports HTTP and can be reused by the workflow later.

**Q7. Why is the response model separate from the database model?**
The database shape and the wire shape differ: `ticket_number` vs `number`, `role` vs `sender_type`, `internal` vs `is_internal`, computed fields like `approval_status` and `escalation_required`. Pydantic schemas in `schemas/` are the public contract; entities can change without breaking clients.

**Q8. Why does `customer_service` import from `ticket_service`?**
To reuse `summaries()` so a ticket looks identical in the ticket list and on the customer page. It is one-way (customers depend on tickets), so there is no cycle. The shared plain shapes live in a leaf module, `schemas/records.py`, to avoid circular imports.

---

## C. Contract-first and API design

**Q9. Why did you change the API contract?**
The first draft had fields the database does not have (`plan_name`, `lifetime_value`, an `ai` message role, escalation `priority`). Inventing columns just to match a draft is backwards, so I made the contract match the model, documented it in a "Contract changes in Phase 4" section, and wrote each route's status codes. The rule in the project is that contract, schemas and types change together.

**Q10. Why accept both the UUID and `CD-1001`?**
Humans and the demo use ticket numbers, machines use ids. `_load` tries the id first and then the number. Both return the same ticket or the same 404.

**Q11. How does pagination work?**
`page >= 1` and `1 <= page_size <= 100`, default 20, enforced by FastAPI `Query` validation (422 outside the range). The repository runs a count query and a limited query, and the response is `{items, total, page, page_size}`. Capping size protects memory and the database.

**Q12. How does search work?**
Case-insensitive `LIKE` over subject, body and ticket number; for customers over name, company and email. It is a simple scan, fine for 13 tickets; a production version needs an index or full-text search.

**Q13. Which status codes did you choose and why?**
201 on create, 404 for unknown ticket/customer/assignee, 409 for replying publicly on a closed ticket (a state conflict), 422 for bad input (blank text, unknown channel, empty PATCH), 403 for a viewer on a write route, 401 without a token.

**Q14. How does PATCH tell "not sent" from "set to null"?**
Pydantic `model_fields_set`. Only sent fields change, so `{"assigned_to": null}` un-assigns, while omitting it leaves the assignee alone. An empty body returns 422.

---

## D. Business behaviour

**Q15. What happens to ticket status in each action?**
Create: `new`. Public reply on a `new` ticket: `in_progress`. Request-info: `waiting_on_customer`. Escalate: `escalated`. PATCH: whatever the agent sets, and `resolved`/`closed` stamps `resolved_at`. Internal notes change nothing.

**Q16. Why can you add an internal note on a closed ticket but not reply?**
A note is for staff, so it is harmless and often useful after closure. A public reply to a closed ticket would reach the customer unexpectedly, so it returns 409.

**Q17. How is an escalation created here versus in the AI flow?**
This is the human path: team `support_leads`, severity `high` (or `critical` if urgent), ticket set to `escalated`. The AI path with policy rules (disputes, deletions, security, data loss) is Phase 7 and Phase 11, and "rules first, LLM second" stays the principle there.

**Q18. How do you compute `approval_status` and `escalation_required` on a ticket?**
`approval_status` is the status of the latest approval request for the ticket, or `not_required`. `escalation_required` is true if an escalation row exists or the status is `escalated`. Both come from batch queries, not new columns.

**Q19. Who is the author of a reply?**
The caller. The service looks up their profile for a full name ("Sam Agent"), falling back to their email from the token. A test checks it.

---

## E. Security

**Q20. How is RBAC applied?**
By dependency on each route: GETs use `require_role(viewer)`, everything that changes data uses `require_role(agent)`. A test loops over every write route as a viewer and expects 403, and another checks all read routes return 401 without a token.

**Q21. Is anything audited?**
Yes, through the Phase 3 middleware: every non-GET request (create, patch, reply, escalate) writes an `audit_logs` row with actor, path, status and request id, but never the body.

**Q22. Can a customer's message do harm?**
In this phase ticket text is only stored and returned as data. Prompt-injection defence (`wrap_untrusted`) is Phase 7 and matters when the text reaches a model. The ticket CD-1013 exists to test that later.

**Q23. Can a reply leak internal data?**
Not yet protected: output validation (N5) is Phase 7. Today replies are only recorded, not sent, and the honest status says so.

---

## F. Performance and data

**Q24. What is the N+1 problem and did you avoid it?**
Loading a list of 20 tickets and then querying the customer, approval and escalation for each would be 60 extra queries. `summaries()` loads those three for the whole page in three batch queries (`IN (...)`), so a page costs a fixed number of trips.

**Q25. How are ticket numbers generated and what is the risk?**
Highest existing number plus one, `CD-1001` onward. Two simultaneous creates could pick the same number; the unique constraint makes one fail loudly instead of duplicating. For real load I would use a database sequence in a new migration.

**Q26. How do transactions work?**
`get_session` yields one session per request; it commits if the handler returns and rolls back if it raises. A failed reply cannot leave a half-written ticket.

**Q27. Does it run on Postgres?**
The same SQLAlchemy code is designed for both, but tests only ran on SQLite. I have not run the API against real Postgres or Supabase.

---

## G. Testing

**Q28. What did you test?**
36 tests in `tests/api/test_tickets_customers.py`, total 127 passing offline: four channels, all 13 demo tickets by number, filters, search and paging, validation, every 404, viewer 403 on each write route, patch semantics, reply/closed rules, request-info, escalation, events, customer list, search and detail.

**Q29. How do tests stay independent of each other?**
They share one seeded database, so tests that change data create their own new ticket first and never depend on counts that other tests might change (they use "at least" checks for totals).

**Q30. How do you map tests to the requirement?**
F1 → `test_create_ticket_accepts_every_channel`; F4 read side → `test_ticket_detail_loads_customer_context`, `test_customer_detail_loads_subscription_workspace_and_tickets`; list and 404 contract → the list and unknown-ticket tests.

**Q31. How do you know mutations are audited?**
A test makes a reply, then reads the `audit_logs` table directly and expects a `POST .../reply` row with status 201.

---

## H. Honest status and "what next"

**Q32. What is validated and what is not?**
Validated locally: 127 tests pass, ruff clean. Not done: Postgres run, Docker, cloud, workflow routes, reply safety checks.

**Q33. What did you learn or change along the way?**
Two lint rules shaped the code: calling `require_role(...)` in a default argument is flagged by ruff B008, so I hoisted the role dependencies into module constants; and I merged a nested `if` the linter flagged. Neither changed behaviour.

**Q34. What comes next and how does Phase 4 help?**
The workflow (Phases 9 and 10) will read the same customer context through these services and write status, category and severity. The console (Phase 12) can be built from the contract alone, in parallel.

**Q35. 30-second summary.**
"Phase 4 opens the reception desk. Agents create tickets from any channel, search and open them with the customer's plan and history, and reply, ask for info or escalate. A three-layer design keeps HTTP, rules and SQL apart, lists are paged and built without N+1 queries, and the Phase 3 roles make viewers read-only. Creating a ticket doesn't start the AI; that's a separate step later. 36 new tests, 127 total, all passing."
