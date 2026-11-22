# Phase 13 Interview Q&A: Ticket Workflow Screen

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code.

---

## A. Big picture

**Q1. What did you build in Phase 13?**
The ticket workflow screen: one three-column page where an agent runs the AI workflow, watches the twelve steps, approves or rejects a refund, edits the AI's draft and sends the reply. It is in `frontend/app/(dashboard)/tickets/[id]/page.tsx`, with components in `frontend/components/ticket/` and pure logic in `frontend/lib/workflow.ts`.

**Q2. Which requirement does it cover?**
F12: approve, reject, escalate, reply and request info from one screen. It also surfaces F9 (approval gate) and F13 (workflow inspectability) to a human.

**Q3. Which tasks were in the phase?**
P13-1 ticket detail layout, P13-2 workflow steps and polling, P13-3 approve, reject, reply and escalate actions, P13-4 frontend unit tests.

**Q4. Did the backend change?**
No. No route, schema, migration or contract change. The screen consumes routes from Phases 4, 10 and 11. I added only types and client methods.

**Q5. Why does `PLAN_PHASE.md` call Phase 13 "Evaluation and delivery"?**
The plan has one "Agent console" phase; `TASKS.md` splits it into Phase 12 (shell) and Phase 13 (ticket screen), which pushes evaluation and delivery to Phase 14. I followed `TASKS.md` and the branch name `Phase13_Ticket_workflow_screen`.

**Q6. Explain it to a non-technical person.**
It is the cockpit. The agent presses one button, watches twelve progress lights, makes the money decision with Approve or Reject, edits the AI's draft reply and sends it. The AI never sends anything on its own.

**Q7. What is the demo checkpoint?**
Agent opens CD-1002, runs the workflow, watches the steps, approves, sends the reply. Then viewer sees disabled actions. I have **not** run this in a live browser; unit tests, type check, lint and build pass.

---

## B. Screen design

**Q8. Why three columns?**
The agent needs the message and reply, the customer facts (plan, seats), and the AI's findings together. Left is conversation and composer, centre is customer, right is workflow. No page switching to finish a ticket.

**Q9. Why split into components?**
`WorkflowSteps`, `WorkflowPanel`, `ApprovalBar` and `ReplyComposer` each have one job and take props, so they test without the network. The page owns state and calls the API.

**Q10. Where does state live?**
In the page: the ticket (via `useAsync`), the workflow state, the reply draft, a `busy` flag and a message. It is local component state because nothing else needs it; no global store was warranted.

**Q11. How does the page know a run already exists when you open the ticket?**
On mount it calls `api.workflow(id)`. A 404 ("No workflow has run") just means not run yet.

**Q12. What happens to stale data when you press Run again?**
The page clears the old workflow state and draft, then polls. Otherwise the old twelve lights would flash before the new run appears.

---

## C. The twelve steps and polling

**Q13. How are the twelve steps drawn?**
`deriveSteps()` in `lib/workflow.ts` maps `completed_nodes`, `current_node` and `status` to a state per step: done, current, waiting, pending, skipped, failed. The ids match `GRAPH_NODES` in `agents/graph.py`.

**Q14. What is "skipped"?**
Three nodes are branch-only: `human_approval`, `execute_resolution` and `escalation`. After a run finishes, any step that never ran is shown as skipped, so you can see which path the graph took.

**Q15. Why separate `deriveSteps` from React?**
It is pure: input workflow, output list. I can test every state in a few lines with no rendering. CLAUDE.md names this test explicitly.

**Q16. Why poll instead of WebSockets or server-sent events?**
The project convention is a 2-second poll (CLAUDE.md section 11). It needs no new server infrastructure, works through any load balancer and the backend already saves state after every node. The cost is up to 2 s of lag and steady requests.

**Q17. When does polling stop?**
`shouldPoll` is true only while `status === "running"` (or just after pressing Run, before the first state arrives). A run paused for approval does not change by itself, so it stops; it ends too when completed, escalated or failed. This keeps idle tickets silent.

**Q18. What if a poll fails?**
The page keeps the last good state and the next tick retries. A blip or a 429 causes delay, not a blank screen.

**Q19. How do you avoid polling forever?**
When the status leaves `running`, the `enabled` flag of `usePolling` turns false and the interval is cleared on cleanup. A test covers each status.

**Q20. Why reload the ticket when a run finishes?**
The workflow changes the ticket row: status, category, severity, approval and sometimes a new message or escalation. One reload on leaving `running` brings the left and centre columns up to date without reloading continuously.

---

## D. Approval and human-in-the-loop

**Q21. When do Approve and Reject appear?**
Only when `canDecide(workflow)`: approval status is `pending` and an approval id exists. Not before the pause, not after the decision. A test checks pending versus approved versus not_required.

**Q22. Where does the approval id come from?**
From the workflow state: `approval_request_id`, set when the graph pauses at `human_approval`. The screen then calls `POST /approvals/{id}/approve`.

**Q23. What does Approve do?**
It records the decision, resumes the graph with `Command(resume=...)`, runs the refund through `ToolRegistry` exactly once, finishes the summary and memory steps, and returns the finished workflow. The screen sets that state and reloads the ticket.

**Q24. What if the agent clicks Approve twice?**
The server returns 409 "Approval has already been decided", shown in a red box. The refund does not run twice. The button is also disabled while a request is in flight (`busy`).

**Q25. What does Reject do?**
It resumes the graph on the rejection branch, which goes to the `escalation` node. The ticket ends escalated to a human team.

**Q26. Where is the role check?**
Twice. The UI disables the buttons for viewers (`canAct`). The backend `require_role` returns 403 regardless. The UI is courtesy; the server is the control.

**Q27. Why is a refund never executed by the screen?**
The screen never calls a tool. It only calls the approval route, and the server runs the tool through the registry with `approved=True`. Money and accounts stay approval-gated (CLAUDE.md 18.1).

**Q28. Why does the approval box list the reasons?**
The approver should see what they are approving and why it was flagged: the planned action descriptions and the risk reasons from `risk_check`. A bare button would invite rubber-stamping.

---

## E. Reply, request info, escalate

**Q29. Is the AI reply sent automatically?**
Never. It is a draft in an editable box. A human presses Send reply.

**Q30. When is the draft filled in?**
After the run, from `final_response` (or the plan's `customer_response`). It is prefilled only until the agent types, tracked with a ref, so a poll update never overwrites the agent's edits.

**Q31. How is the draft kept safe (N5)?**
Output validation runs server side in the resolution step: it blocks internal URLs, secrets and other customers' data and raises risk if it fails. The screen shows what the server produced.

**Q32. What are internal notes?**
A checkbox sends the same text with `internal: true`: stored on the ticket but not visible to the customer.

**Q33. Why do request info and escalate share the reply box?**
A v1 shortcut: one text box, three buttons labelled with how the text is used (one question per line, or the escalation reason). It works but is less clear than separate fields. I would split it with a small dialog for each.

**Q34. What can go wrong when sending?**
A closed ticket returns 409 for a public reply; a viewer gets 403. Both show the server's message. The empty draft cannot be sent (button disabled).

---

## F. Errors, security and roles

**Q35. How are errors shown?**
The page catches the `ApiError` and shows its `detail` (409, 403, 404). `DataState` handles load failures and `NetworkError`.

**Q36. Why are POSTs never retried?**
A retry could act twice: two replies, two approvals. The client retries only GETs. A test proves a failed run POST is attempted once.

**Q37. Does a viewer see anything different?**
They see everything read-only. Run, Approve, Reject and the composer controls are disabled, with a note. They can also load the page by URL, because reads are allowed to viewers.

**Q38. Is the token safe in `localStorage`?**
It is the project convention and acceptable for a demo JWT in an internal tool. A script injected into the page could read it. A production hardening step is an HttpOnly cookie. React escapes text by default, and I never render server text as HTML.

**Q39. Can ticket text inject instructions into the screen?**
The screen renders ticket and AI text as plain text (React escapes it). Prompt-injection defence is server side (`scan_for_injection`, `wrap_untrusted`); CD-1013 stays data.

---

## G. Testing

**Q40. What did you test?**
17 new vitest tests (32 in total): `deriveSteps` for every state, the twelve rows rendered, the polling rule, `canDecide`, `ApprovalBar` (only when pending, disabled for viewer, handlers fire), `ReplyComposer` (viewer disabled, empty cannot send), and API calls (POST not retried, bearer header, 409 message).

**Q41. What did you not test?**
The full page with a mocked backend and live polling timers, and a real browser run. The logic is covered in pieces, not as one flow. That is the next best test to add (a Playwright run against the demo stack).

**Q42. What checks pass?**
`tsc --noEmit`, `next lint` and `next build` pass; the backend's 408 tests still pass.

**Q43. How do you test a viewer cannot act?**
Components take an `allowed` prop derived from `canAct(role)`. Tests render with `allowed=false` and assert every button is disabled. The server-side 403 is covered by the existing API tests.

---

## H. Trade-offs and improvements

**Q44. What are the limits of polling?**
Up to 2 s lag; 30 requests per minute per active tab; with a per-IP limit of 120 per minute, about four active runs from one office IP can hit the limiter. A WebSocket or SSE stream would cut that.

**Q45. What would you improve first?**
A live end-to-end browser test, separate forms for reply, request-info and escalate, and showing the `/events` timeline (tool calls, timings, tokens) on the screen.

**Q46. Is the background workflow production-ready?**
No. It runs in the API process. A restart loses an in-flight run, and the SQLite checkpointer means one replica only. The production step is a worker queue and a shared checkpointer.

**Q47. What would change for many agents on one ticket?**
Two agents could both see Approve. The 409 protects the money, but the second agent gets an error rather than a live update. Presence or push updates would help.

**Q48. How do you prevent type drift with the backend?**
`types.ts` mirrors `API_CONTRACT.md` by hand and the rule is to change both together. Generating types from the OpenAPI schema would remove the manual step.

---

## I. Honest status

**Q49. Is it deployed?**
No. Nothing is containerised or on a cloud; no credentials were used. Everything is validated locally.

**Q50. What would you tell the board is not done?**
A live browser click-through, the on-screen event timeline, dashboard and other pages whose backend routes do not exist yet, and cloud delivery.

**Q51. How does Phase 13 prepare the final phase?**
Evaluation thresholds and packaging need a working product to measure. This phase completes the user-facing flow; the next adds Dockerfiles, Compose, Terraform, CI and the quality gate, and makes `NEXT_PUBLIC_API_URL` a per-environment build argument.
