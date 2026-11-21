# Phase 1 Explained: Building the Foundation

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

Picture a software company called **CloudDesk**. It sells online tools for teamwork: file storage, shared workspaces, billing and so on. Every day its customers write in with problems, for example:

- "I can't log in."
- "You charged me for 8 seats but we only use 5."
- "I think someone broke into my account."

At the moment a human support agent reads each message, looks up the customer, searches the help articles, works out the fix and writes a reply. That is slow and repetitive.

**We are building an AI assistant that does the investigation for the support agent.** When a message (a "ticket") arrives, the system:

1. **Reads it** and works out what kind of problem it is.
2. **Decides how urgent it is.**
3. **Looks up the customer**: their plan and their past problems.
4. **Searches the help library** for the right articles.
5. **Works out the likely cause** and the steps to fix it.
6. **Drafts a reply** to the customer.
7. **Stops and asks a human** before anything risky, such as giving back money.
8. **Passes serious cases to a specialist team**, for example a security breach or a legal request.
9. **Remembers** what happened, so it knows the customer better next time.

One principle runs through the whole design: **the AI suggests, and a human approves anything that costs money or changes an account.** The AI is a very fast assistant. It never has the final say on anything risky.

---

## 2. How we are building it: 13 phases

Building a house works in a fixed order: foundation, walls, plumbing and wiring, rooms, then furniture. Nobody puts up curtains before the walls exist. We split the project the same way, into **13 phases**, and each one builds on the one before.

| Phase | Name | In plain words |
|---|---|---|
| **1** | **Runtime skeleton** | **The foundation: the system can start, check its own health, and keep a record of what it does.** |
| 2 | Persistence and demo data | A filing cabinet: somewhere to store tickets and customers, filled with sample data. |
| 3 | Identity and request guards | The front door and locks: logins, who is allowed to do what, and a log of every change. |
| 4 | Support API | The service counter: create a ticket, look one up, view a customer. |
| 5 | Knowledge pipeline | The library: help articles organised so the system can find the right one quickly. |
| 6 | Tools and policy | The toolbox, with safety catches on the dangerous tools (refunds need approval). |
| 7 | Rules and guardrails | The rulebook: fixed company policies, plus protection against trick messages. |
| 8 | Specialist agents | The team: six AI "specialists", each with one job (reader, researcher, fixer, and so on). |
| 9 | Workflow and trace | The assembly line: the specialists work in order, and every step is recorded. |
| 10 | Approval and escalation | The manager's sign-off: pause for a human when money is involved, and hand serious cases to experts. |
| 11 | Memory | The notebook: remember each customer's history, without ever storing passwords or card numbers. |
| 12 | Agent console | The screen that support agents actually use. |
| 13 | Evaluation and delivery | The final inspection: measure quality, then package the system to run in the cloud. |

**This document covers Phase 1, the foundation.**

---

## 3. What Phase 1 is

Phase 1 contains no AI yet. That is deliberate.

Before a restaurant serves any food, it needs a building with power and running water, a way to check that the kitchen is safe to open, and a logbook of every order. Phase 1 builds that equivalent for our software. Every later phase depends on it.

Phase 1 delivers **five things**.

### 3.1 The "on switch": the server starts

We built the core program, called the **backend server**. It runs in the background and answers requests. In later phases, those requests will be things like "show me ticket 1002" or "run the AI on this ticket."

For now it only has to start up cleanly and stay running.

> **Analogy:** opening the shop doors in the morning. The shelves are still empty, but the shop is open and ready.

### 3.2 The settings panel: one place for every setting

Every system needs settings. Which database do we use? Which AI provider? Are we in demo mode or real mode?

We built **one central settings panel** that reads these values when the system starts. It has three important features:

- **It works with no internet and no paid AI account.** By default the system runs in **demo mode**, with a pretend AI and pretend data stores built in. Anyone, including an interview panel, can run the whole system on a laptop with no passwords and no cost.
- **It hides secrets.** Passwords and access keys are stored in a protected way. If the system ever prints its settings, for example while someone is fixing a problem, secrets show up as `**********` and never as the real value.
- **Every setting is listed in one template file**, with placeholder values only. A new team member can see every switch the system has without ever seeing a real password.

> **Analogy:** the control panel of a building. One panel, every switch labelled, and the safe-box keys locked inside it instead of taped to the front.

### 3.3 Health checks: can the system tell us it is OK?

When software runs in the cloud, automated monitors ask it every few seconds, "Are you alive? Are you ready to work?" We built three answers to those questions:

| Check | The question it answers | Analogy |
|---|---|---|
| **Health** | "Who are you, and what version are you?" | A name badge |
| **Live** | "Are you awake?" | Checking someone has a pulse |
| **Ready** | "Can you actually do your job right now?" | Checking a pilot has fuel, radio and instruments before take-off |

The **Ready** check is the clever one. It goes through each part the system depends on: the database, the short-term memory store, the knowledge library and the AI provider. It reports **"ready"** only when all of them are in place. If anything is missing it reports **"degraded"**, so the cloud stops sending work to it until it is fixed.

When something is wrong, the Ready check **explains the problem without revealing any passwords or private addresses**. A monitoring screen can show the result safely.

The **Live** check is deliberately simple and never depends on anything else. If the database has a short outage, the system will not be restarted for no reason.

### 3.4 Tracking numbers: every request gets an ID

Every request that reaches the system gets a unique **tracking number**, called a **Request ID**, and every reply carries the same number back.

Why this matters: suppose a support agent reports, "Something went wrong when I clicked Approve." With the tracking number, an engineer can find exactly that request in the logs within seconds. There is no searching through thousands of lines.

We also made it **safe**. If someone sends a fake or malicious tracking number, for example one designed to corrupt our logs, the system quietly ignores it and creates a fresh one.

If something unexpected breaks, the user sees only a polite "Internal Server Error". Internal details are never shown. The error is still recorded in full on our side, under the same tracking number.

> **Analogy:** a parcel tracking number. Whatever happens to the parcel, you can always find out where it went, and the number on your receipt matches the number in the warehouse system.

### 3.5 The logbook: structured records of everything

Every event the system records is written as a **neat, consistent line** containing:

- the time,
- how serious it is (information, warning or error),
- what happened,
- the **Request ID** (which request it belongs to),
- the **Workflow ID** (which AI investigation it belongs to, once the AI exists in later phases).

Each line has the same fixed format, so computers can search and filter it, not just people. In the cloud, these logs feed dashboards and alerts.

> **Analogy:** a ship's logbook where every entry has the same columns (time, event, which voyage), instead of scribbled notes in the margins.

---

## 4. How the pieces fit together

When any request arrives, it passes through a short series of checkpoints in this order:

```text
   A request arrives (for example from the agent's browser)
        │
        ▼
   ┌───────────────────────┐
   │ 1. Front-door check   │  Is this request coming from our own website?
   └───────────────────────┘
        │
        ▼
   ┌───────────────────────┐
   │ 2. Tracking number    │  Give it a Request ID (or keep a safe one it brought)
   └───────────────────────┘
        │
        ▼
   ┌───────────────────────┐
   │ 3. The actual work    │  Phase 1: the health checks.
   │                       │  Later phases: tickets, AI, approvals...
   └───────────────────────┘
        │
        ▼
   Reply goes back, stamped with the same Request ID
   Every log line along the way also carries that ID
```

This line of checkpoints is designed to grow. **Phase 3** will add two more: a **speed limit**, so nobody can flood the system with requests, and an **audit recorder**, which notes who changed what. The order is already fixed, so those slot in without rebuilding anything.

---

## 5. How we know it works: automated tests

Saying "it works" is not enough. We wrote **automated tests**: small programs that check the system's behaviour automatically, in seconds, every time the code changes. They run fully offline.

Some of the things they check:

- The system starts with **no AI key and no internet** (demo mode).
- The Health, Live and Ready checks give the right answers.
- **Every reply carries a tracking number**, including error replies and "page not found" replies.
- A malicious tracking number is rejected and replaced.
- **Secrets never appear** in settings printouts or health-check messages.
- Every log line carries the right tracking number, and the number is cleared afterwards so it never leaks into the next request.
- When something crashes, the user sees only a generic message, and the full error is logged on our side.

> **Analogy:** a pre-flight checklist. The pilot runs it before every take-off, not only on the first flight.

---

## 6. Why we started here

A non-technical listener might ask: "Why spend a whole phase on things the customer never sees?"

There are three reasons:

1. **Safety from day one.** Secret handling, safe error messages and tracking numbers are much harder to bolt on later. Building them first means every future feature inherits them automatically.
2. **Anyone can run it.** Demo mode means a reviewer, a new teammate or an interview panel can start the whole system on a laptop with no accounts, keys or cost.
3. **When something goes wrong, we can find out why.** An AI system that makes decisions about customers must be explainable. The tracking numbers and structured logs built here are the first step. In Phase 9 they let us show every decision the AI made, step by step.

---

## 7. What comes next

- **Phase 2** gives the system a memory for records: a database of tickets and customers, pre-loaded with 13 realistic sample tickets and 8 sample customers.
- **Phase 3** adds logins and permissions. There are three roles: **viewer** (can only look), **agent** (can act) and **admin** (can change settings). A viewer can never approve a refund.
- From **Phase 5** onward, the AI parts arrive: the help library, the rulebook, the six specialist agents, the step-by-step workflow and the human approval gate.

---

## 8. One-sentence summary

> **Phase 1 built the foundation of an AI customer-support assistant: a server that starts anywhere with no cost or keys, keeps its secrets hidden, reports its own health honestly, and gives every request a tracking number so nothing that happens is ever lost.**

---

### Appendix: where each part lives (for technical listeners)

| Plain-English name | Technical name | File |
|---|---|---|
| The server | FastAPI application | `backend/app/main.py` |
| Settings panel | Pydantic settings (`get_settings`) | `backend/app/core/config.py` |
| Settings template | Environment variable list | `.env.example` |
| Health / Live / Ready checks | Health probe routes | `backend/app/api/health.py`, `backend/app/core/readiness.py`, `backend/app/schemas/health.py` |
| Database placeholder | Database stub (real database comes in Phase 2) | `backend/app/core/database.py` |
| Tracking numbers | `X-Request-ID` middleware (requirement N3) | `backend/app/middleware/request_id.py` |
| Logbook | JSON logging with `request_id` and `workflow_id` | `backend/app/core/logging.py` |
| Automated tests | pytest, fully offline | `tests/conftest.py`, `tests/api/test_health.py`, `tests/unit/` |
| Run commands | `make setup`, `make backend`, `make test`, `make lint` | `Makefile` |
