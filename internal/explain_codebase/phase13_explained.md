# Phase 13 Explained: The Ticket Screen, or "The Agent's Cockpit"

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

**CloudDesk** is a fictional company that sells online tools for teamwork: file storage, shared workspaces, billing. Customers write in with problems ("I can't log in", "I was charged for 8 seats but use 5"). Each message is a **ticket**.

We are building an **AI assistant that investigates tickets for the human support agent**. It works out how urgent the ticket is, looks up the customer, finds the right help article, suggests a fix and drafts a reply. **Anything that costs money or changes an account waits for a human to approve.**

Phases 1 to 11 built the brain and the safety rules. Phase 12 built the front door. **Phase 13 builds the room where the work happens.**

---

## 2. The 13 phases

| Phase | Name | In plain words |
|---|---|---|
| 1 | Runtime skeleton | The foundation. *(done)* |
| 2 | Persistence and demo data | The filing cabinet. *(done)* |
| 3 | Identity and request guards | The security guards at the door. *(done)* |
| 4 | Support API | The reception desk. *(done)* |
| 5 | Knowledge pipeline | The searchable help library. *(done)* |
| 6 | Tools and policy | The toolbox and the permission desk. *(done)* |
| 7 | Rules and guardrails | The rulebook and defences against trickery. *(done)* |
| 8 | Memory | Remembering each customer, safely. *(done)* |
| 9 | Specialist agents | The team of AI specialists. *(done)* |
| 10 | Workflow graph and trace | The assembly line with a flight recorder. *(done)* |
| 11 | Approval and escalation | The "ask a human first" gate. *(done)* |
| 12 | Console shell | The front door and the waiting-room boards. *(done)* |
| **13** | **Ticket workflow screen** | **The cockpit: run the AI, watch it, approve, reply.** |

*(In our task list the final phase, measuring quality and packaging for the cloud, is the next one. It is listed as Phase 13 in the original plan and Phase 14 in the task list, because the screen work was split in two.)*

---

## 3. What Phase 13 is

Think of an **airline pilot's cockpit**. The plane (the AI) can do a lot by itself, but the pilot needs one panel showing what it is doing, with a few big switches for the decisions that only a human should make.

| Cockpit | CloudDesk Phase 13 |
|---|---|
| The pilot | The **support agent** |
| "Start engines" button | **Run AI workflow** |
| The row of progress lights | **Twelve steps** that light up one by one |
| "Permission to proceed?" prompt | **Approve / Reject** for a refund |
| The radio message to passengers | The **reply**, drafted by AI, edited by the agent, then sent |
| The emergency call to base | **Escalate** to the support leads |
| Guest passengers can watch but not fly | **Viewers** see everything, buttons greyed out |

---

## 4. The pieces, in plain words

### 4.1 One screen, three columns
- **Left:** the customer's message and the reply box.
- **Middle:** who the customer is: their plan, how many seats they pay for versus use, and their earlier tickets.
- **Right:** what the AI is doing and has found.

An agent never has to jump between pages to finish a ticket.

### 4.2 The twelve lights
When you press **Run AI workflow**, twelve steps run in order: understand the message, judge urgency, look up the customer, find help articles, work out the cause, plan the fix, check the risk, ask a human if needed, carry out the fix, escalate if needed, write a summary, update memory.

The screen shows each step as **grey (waiting)**, **blue (working now)**, **green (done)** or **purple (waiting for a human)**. Steps that were never needed, like "Escalate" on a normal refund, are marked **skipped** at the end, so it is clear that the path not taken was deliberately not taken.

### 4.3 How the screen stays up to date
The AI works in the background and can take a few seconds. The screen **asks the back office for an update every 2 seconds** while it is working, like checking a parcel tracker. When the AI pauses to wait for a person, or finishes, the screen **stops asking**, because nothing will change until someone acts. That keeps the traffic small.

### 4.4 The approval box
For a refund, the AI stops and a purple box appears: *"Approval required: refund 3 seats"*, with the reasons. Two buttons: **Approve** and **Reject**.

- The box appears **only when an approval is really waiting**. Not before, not after.
- **Approve:** the refund runs **exactly once**. A second click is refused politely ("already decided").
- **Reject:** the ticket is escalated to a human team instead.
- **Viewers see the buttons greyed out.** And even if someone bypassed the screen, the back office would refuse them. The screen is courtesy; the back office is the lock.

### 4.5 The reply: AI drafts, human decides
The AI's drafted reply appears in an editable box. The agent can **change every word** before pressing **Send reply**. Nothing goes to the customer unless a person sends it. Before the draft is even shown, the back office has already checked it does not contain internal links, secrets or another customer's data.

The agent can also **Request more info** (one question per line) or **Escalate** with a reason, from the same box.

### 4.6 Clear errors instead of silent failures
If something goes wrong (not allowed, already approved, ticket closed), the screen shows **the back office's own message** in a red box. The agent always knows what happened.

---

## 5. A walk through the demo

1. Log in as the **Agent** and open ticket **CD-1002** (the customer was charged for 8 seats but uses 5).
2. Press **Run AI workflow**. The twelve lights come on one at a time.
3. The run **pauses at "Human approval"**. A purple box offers **Approve** and **Reject**. Evidence and a diagnosis are on the right.
4. Press **Approve**. The refund runs once, the remaining steps finish, and the ticket updates.
5. The drafted reply appears. Edit it if you like, then press **Send reply**. It joins the conversation.
6. Open **CD-1005** (a suspected breach). The AI **escalates automatically**; no approval box, a red "Escalated" banner instead.
7. Log in as the **Viewer** and open the same ticket. Everything is visible, **every button is greyed out**.

---

## 6. Why it was built this way

- **The human always has the last word.** Approve, Reject and Send are all clicks by a person.
- **The screen does no thinking of its own.** It shows what the back office says. The decisions (what needs approval, who is allowed) live in the back office, where they are tested and cannot be skipped by clicking around.
- **One small piece of logic is separated and tested heavily:** "which of the twelve lights should be which colour". It is plain code with no screen attached, so we could test every case quickly.

---

## 7. Honest status: what is built and what is not

| Item | State |
|---|---|
| Three-column ticket screen, twelve lights, 2-second updates | **Built and tested** |
| Approve, Reject, edit-and-send reply, request info, escalate | **Built and tested** |
| Viewer sees everything but cannot act | **Built and tested** |
| Automated checks | **32 screen tests, type check, style check and production build pass.** Back office: 408 tests pass |
| A live click-through in a real browser against the running back office | **Not done.** The pieces are tested individually, but I have not watched the whole flow in a browser |
| The detailed timeline of every step and tool call on this screen | **Not shown yet.** The data exists; the display is a later improvement |
| Cloud deployment | **No.** Packaging and quality thresholds are the next phase |

We say this plainly: the board should hear what is real, what is tested, and what is still to do.

---

## 8. One-sentence summary for the board

> **Phase 13 gives the support agent a single screen where they press one button, watch the AI investigate in twelve visible steps, make the money decision themselves with Approve or Reject, and send a reply they have personally reviewed.**

---

## 9. What comes next

The final phase **measures quality** (the system must score above set thresholds or the build fails) and **packages everything for the cloud** (containers, infrastructure files, automated checks). Nothing will be claimed as deployed until it really is.
