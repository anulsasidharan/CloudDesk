# Phase 12 Explained: The Console Shell, or "The Reception Desk Screen"

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

**CloudDesk** is a fictional company that sells online tools for teamwork: file storage, shared workspaces, billing. Customers write in with problems ("I can't log in", "I was charged for 8 seats but use 5"). Each message is a **ticket**.

We are building an **AI assistant that investigates tickets for the human support agent**. It works out how urgent the ticket is, looks up the customer, finds the right help article, suggests a fix and drafts a reply. **Anything that costs money or changes an account waits for a human to approve.**

Until now, everything we built was **behind the scenes**: you could only talk to it with technical tools. Phase 12 builds the **first screen a person can actually look at**.

---

## 2. The 13 phases

| Phase | Name | In plain words |
|---|---|---|
| 1 | Runtime skeleton | The foundation. *(done)* |
| 2 | Persistence and demo data | The filing cabinet. *(done)* |
| 3 | Identity and request guards | The security guards at the door. *(done)* |
| 4 | Support API | The reception desk (no screen yet). *(done)* |
| 5 | Knowledge pipeline | The searchable help library. *(done)* |
| 6 | Tools and policy | The toolbox and the permission desk. *(done)* |
| 7 | Rules and guardrails | The rulebook and defences against trickery. *(done)* |
| 8 | Memory | Remembering each customer, safely. *(done)* |
| 9 | Specialist agents | The team of AI specialists. *(done)* |
| 10 | Workflow graph and trace | The assembly line with a flight recorder. *(done)* |
| 11 | Approval and escalation | The "ask a human first" gate. *(done)* |
| **12** | **Agent console** | **The screen the agent uses. First half: the shell.** |
| 13 | Evaluation and delivery | Measuring quality and packaging for the cloud. |

*(Our task list splits the screen work in two: "Console shell" is the part finished now; the ticket screen with the Approve button comes next.)*

---

## 3. What Phase 12 is

Think of a **hospital**. For eleven phases we built the doctors, the records room and the rules. But a patient walking in found **no front desk and no signs on the walls**.

Phase 12 builds the **front desk and the building's signs**:

| Hospital | CloudDesk Phase 12 |
|---|---|
| The entrance with a badge check | The **login page** |
| Different badges open different doors | **Roles**: viewer, agent, admin see different things |
| Signs pointing to each department | The **menu on the left** (Dashboard, Tickets, Customers...) |
| A waiting-room board listing patients | The **ticket list** and **customer list** |
| A patient's chart you can read but not write on | The **read-only ticket and customer pages** |
| A phone line to the records room | The **API client**: the one way the screen asks the back office for data |

---

## 4. The pieces, in plain words

### 4.1 The login page
You choose who you are: **Agent**, **Viewer** or **Admin**. This is a *demo* login with no passwords, so anyone can try the system. It hands the screen a **temporary pass** (a token) that lasts 8 hours. If the pass expires, the screen sends you back to login with a polite message.

### 4.2 The three roles
| Role | Who | What the screen lets them do |
|---|---|---|
| **Viewer** | A trainee or auditor | **Look** at everything. Action buttons are greyed out. |
| **Agent** | A support person | Look, plus act (run the AI, approve, reply). |
| **Admin** | A manager | Everything, plus the **Settings** page. |

The screen hides the Settings link from non-admins, **but this is only politeness**. The **back office checks the pass on every request** and would refuse a viewer anyway. The screen never makes the security decision.

### 4.3 The menu
There is **one list** of menu items in the code. The menu and the automated tests both read it, so they can never disagree. Eight sections:

> Dashboard, Tickets, Customers, Knowledge, Escalations, Agents, Audit, Settings.

### 4.4 The list pages
Each page asks the back office for data and shows a table:

- **Tickets**: search by words or ticket number (CD-1002), filter by status and severity, page through the results. Coloured **pills** show status at a glance (green resolved, red critical).
- **Customers**: search by name, company or email. Click one to see their plan, seats, storage, workspaces and the notes the AI remembered.
- **Knowledge**: the help articles the AI is allowed to quote.
- **Dashboard, Escalations, Agents, Audit, Settings**: built and ready, but see section 6.

### 4.5 The phone line: the API client
**Every screen talks to the back office through exactly one file.** That gives us one place to handle three real-world problems:

1. **Pass expired.** Clear it, go to login with the message "Your session expired".
2. **Back office unreachable.** Try again twice automatically, then show a clear banner ("Cannot reach the API") with a **Retry** button. Not a blank page.
3. **Never repeat a click that changes things.** Only *reading* is retried. A "send reply" is never re-sent, because it might send twice.

### 4.6 The hand-built toolkit
Buttons, tables, pills and cards are written by hand, with **no outside design library and no gradients** (a deliberate project rule). That keeps the screen small, fast and fully understood by the team.

---

## 5. A walk through the demo

1. Open the console. It sends you to **login**.
2. Click **Sign in as Viewer (Vic)**. You land on the dashboard. The menu has **no Settings**.
3. Open **Tickets**. Type `CD-1002` in the search box. One ticket remains.
4. Click it. You see the customer's message, the plan and the seats (8 paid, 5 used). A note says running the AI comes next phase.
5. Open **Customers**, click the same customer. You see **the same tickets and the same status**. Both pages read the same records, so they cannot disagree.
6. **Sign out**, sign in as **Admin**. **Settings** now appears.

---

## 6. Honest status: what is built and what is not

| Item | State |
|---|---|
| Login, roles, menu, API client, list pages, toolkit | **Built and tested** (15 automated screen tests, type check, style check, production build all pass) |
| Tickets, Customers, Knowledge pages | **Show real data** from the back office |
| Dashboard, Escalations, Agents, Audit, Settings pages | Screens built. The back-office routes that feed them **do not exist yet**, so they show **"Not available yet"** instead of breaking |
| Ticket screen with Run, Approve, Reject, Reply buttons | **Next phase** |
| A live click-through in a real browser against the running back office | **Not done yet.** Tests and the build pass, but I have not watched it in a browser |
| Cloud packaging of the screen | Later phase |

Saying "not available yet" instead of hiding the gap is deliberate: the board should hear what is real.

---

## 7. Why this design is good (talking points)

1. **One front door for data.** All traffic passes through one file, so security and error handling are written once.
2. **The screen never decides security.** It *shows* what a role may do; the back office *enforces* it.
3. **Fails politely.** Expired pass, server down, missing feature: each has a clear message.
4. **Built to be extended.** Adding a page means adding one file and one menu line.
5. **Small and understandable.** No heavy third-party design kit.
6. **Honest.** The "Not available yet" cards show exactly what is missing.

---

## 8. One-line summary per task

| Task | Plain words |
|---|---|
| P12-1 App shell and navigation | The frame of the building and the signs |
| P12-2 Typed API client | The single phone line to the back office, with rules for bad calls |
| P12-3 Login and role-aware layout | The badge check, and doors that match your badge |
| P12-4 Read-only list pages | The boards listing tickets, customers and articles |

---

## 8b. Glossary

| Word | Meaning |
|---|---|
| **Console** | The screen support agents work in |
| **Token / pass** | A temporary proof of who you are, valid 8 hours |
| **API** | The back office's menu of things the screen can ask for |
| **Role** | Your badge level: viewer, agent, admin |
| **Pill** | A small coloured label such as "Escalated" |
| **Next.js** | The tool used to build the screen |

---

## 9. What comes next

**Phase 13** builds the screen the agent really lives in: one ticket page where you press **Run AI**, watch the twelve steps light up, then **Approve** or **Reject** the refund and **send the reply**. It reuses everything from this phase: login, roles, the API client and the toolkit.
