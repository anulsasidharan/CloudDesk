# Phase 4 Explained: The Reception Desk

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

**CloudDesk** is a fictional company that sells online tools for teamwork: file storage, shared workspaces, billing. Customers write in with problems ("I can't log in", "I was charged twice"). Each message is a **ticket**.

We are building an **AI assistant that investigates tickets for the human support agent**. It works out how urgent the ticket is, looks up the customer, finds the right help article, suggests a fix and drafts a reply. **Anything that costs money or changes an account waits for a human to approve.**

---

## 2. The 13 phases

| Phase | Name | In plain words |
|---|---|---|
| 1 | Runtime skeleton | The foundation: the system starts and reports its health. *(done)* |
| 2 | Persistence and demo data | The filing cabinet, filled with sample data. *(done)* |
| 3 | Identity and request guards | The security guards at the door. *(done)* |
| **4** | **Support API** | **The reception desk: create and read tickets and customers.** |
| 5 | Knowledge pipeline | The searchable help library. |
| 6 | Tools and policy | The tools the AI may use, and which need permission. |
| 7 | Rules and guardrails | The rulebook and defences against trickery. |
| 8 | Specialist agents | The team of AI specialists. |
| 9 | Workflow graph and trace | The step-by-step process with a visible trail. |
| 10 | Approval and escalation | The "ask a human first" gate. |
| 11 | Memory | Remembering each customer. |
| 12 | Agent console | The screen the agent uses. |
| 13 | Evaluation and delivery | Measuring quality and packaging for the cloud. |

---

## 3. What Phase 4 is

After Phase 3 we had a filing cabinet full of data and guards at the door, but **no counter where a person could actually ask for anything.** Phase 4 opens the **reception desk**.

Think of a doctor's surgery front desk. The receptionist can:

| At the desk | In our system |
|---|---|
| **Register a new patient visit** | Create a ticket |
| **Pull up a visit's folder** | Open one ticket with everything about it |
| **Show today's waiting list, filtered or searched** | List tickets (by status, severity, or a search word) |
| **Pull up a patient's file** | Open a customer with their plan, workspace, and past tickets |
| **Update the visit card** (priority, who's handling it) | Change a ticket's status, severity, or assignee |
| **Write a note to the patient** | Reply to the customer, or leave a private internal note |
| **Ask the patient a question** | Request more information (ticket waits on the customer) |
| **Call the senior doctor** | Escalate to the support leads team |

The guards from Phase 3 are already on duty: **viewers can look but not touch; agents and admins can make changes.**

### 3.1 What the desk deliberately does NOT do

Creating a ticket **does not start the AI.** Starting the AI is a separate button (built in Phase 10). This is on purpose: it keeps "record the problem" separate from "investigate the problem", so one can fail without breaking the other.

### 3.2 Three-layer rule: who does what

We kept a strict division of labour, like a restaurant:

| Layer | Restaurant | Job here |
|---|---|---|
| **API** | The waiter | Takes the order, checks you are allowed, returns the dish. No cooking. |
| **Service** | The chef | Decides how to make it: the actual rules, in the right order. |
| **Repository** | The pantry clerk | The only one who touches the shelves (the database). |

If a rule changes, only the chef changes. If the database changes, only the pantry clerk changes.

### 3.3 Small touches worth mentioning

- **You can use a friendly number.** Ask for `CD-1001` or for the long internal ID; both work.
- **Lists come in pages** (20 at a time by default, never more than 100), so a big company never gets a giant slow response.
- **Lists are built efficiently.** A page of 20 tickets takes a fixed handful of database trips, not 20 separate lookups.
- **Bad input is turned away politely.** An empty subject, an unknown channel (a fax?), or a made-up status gets a clear "422: that doesn't look right".
- **Clear errors.** Unknown ticket → "404 Ticket not found". Unknown customer → "404 Customer not found". Replying publicly on a closed ticket → "409 Ticket is closed" (private notes are still allowed).
- **The AI does not label tickets here.** A new ticket starts with no category and no severity. The AI assistant fills those in later.

---

## 4. How we know it works

We wrote **36 new automated tests**, bringing the total to **127, all passing**, with the code style checker clean. Highlights:

- Tickets can be created from **email, chat, web and API**, and a brand-new ticket starts as "new".
- All **13 demo tickets (CD-1001 to CD-1013)** can be opened one by one.
- Opening CD-1001 shows its customer, their enterprise plan, their workspace and their other tickets.
- Searching "refund" finds CD-1002. Page 2 of a list really is the next 5.
- Unknown tickets and customers give clean 404s on every route.
- A **viewer is refused (403)** on every route that changes something.
- Replying, asking for info and escalating move the ticket to the right status.

---

## 5. What is honest to say is *not* done

- **The AI is not connected yet.** The "run the AI" button and the live workflow view arrive in Phase 10. Today the ticket detail simply shows `workflow: null` and an empty event list.
- **No approvals or knowledge-library routes yet.** Those are later phases.
- **Customer replies are not yet safety-checked** for internal links or secrets. That check is Phase 7. For now replies are only recorded, never actually emailed.
- Real emails are never sent: all integrations are mocks.
- We changed the written API contract to match the real database (for example a customer has one `plan`, and a customer can have several workspaces). The contract file records this.
- Nothing is deployed to the cloud.

---

## 6. The 30-second version to say out loud

> "Phase 4 is the reception desk. Agents can create tickets from email, chat, web or API, search and filter them, open one to see the customer, their plan and past tickets, and update, reply, ask for information or escalate. A strict three-layer design keeps web handling, business rules and database access separate, and the Phase 3 guards mean viewers can look but never change anything. Creating a ticket deliberately does not start the AI; that is a separate step in a later phase. 36 new tests prove it, including the failure cases."

---

## 7. Where Phase 4 fits

```text
Phase 1: the building stands.        Phase 2: the filing cabinet is full.
Phase 3: guards at the door.         Phase 4: the reception desk opens.   <-- we are here
Phase 5-7: library, tools, rulebook. Phase 8-10: the AI team and its process.
```
