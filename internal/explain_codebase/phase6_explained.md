# Phase 6 Explained: The AI's Toolbox and the Permission Desk

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

**CloudDesk** is a fictional company that sells online tools for teamwork: file storage, shared workspaces, billing. Customers write in with problems ("I can't log in", "I was charged for 8 seats but use 5"). Each message is a **ticket**.

We are building an **AI assistant that investigates tickets for the human support agent**. It works out how urgent the ticket is, looks up the customer, finds the right help article, suggests a fix and drafts a reply. **Anything that costs money or changes an account waits for a human to approve.**

---

## 2. The 13 phases

| Phase | Name | In plain words |
|---|---|---|
| 1 | Runtime skeleton | The foundation: the system starts and reports its health. *(done)* |
| 2 | Persistence and demo data | The filing cabinet, filled with sample data. *(done)* |
| 3 | Identity and request guards | The security guards at the door. *(done)* |
| 4 | Support API | The reception desk: create and read tickets and customers. *(done)* |
| 5 | Knowledge pipeline | The searchable help library. *(done)* |
| **6** | **Tools and policy** | **The AI's toolbox, and the permission desk.** |
| 7 | Rules and guardrails | The rulebook and defences against trickery. |
| 8 | Specialist agents | The team of AI specialists. |
| 9 | Workflow graph and trace | The step-by-step process with a visible trail. |
| 10 | Approval and escalation | The "ask a human first" gate. |
| 11 | Memory | Remembering each customer. |
| 12 | Agent console | The screen the agent uses. |
| 13 | Evaluation and delivery | Measuring quality and packaging for the cloud. |

---

## 3. What Phase 6 is

An AI that can only *talk* is not much use to a support team. To actually help, it must be able to **do things**: look up a customer, check whether a service is down, change a ticket's status, request a refund.

But an AI that can do *anything* is dangerous. It could refund the wrong person, or change a customer's security settings because a ticket told it to.

Phase 6 solves both problems at once. It builds:

1. **A toolbox**: a fixed list of nine actions the AI is allowed to take. Nothing outside the list is possible.
2. **A permission desk**: one single doorway that every action must pass through. At the doorway, a **rule** (not the AI's opinion) decides whether the action can go ahead on its own or must wait for a human.
3. **Pretend outside services**: stand-ins for a billing system, an email system and so on, so we can demonstrate everything safely with no real money or real emails.

### 3.1 The analogy: a bank with a vault

Think of a bank.

| In the bank | In our system |
|---|---|
| The **tools in the staff room** (stapler, calculator, vault key) | The **nine registered tools** |
| **Looking up an account balance**: any clerk may do it | **Read-only tools**: always allowed |
| **Moving money**: needs a manager's signature | **Refunds and setting resets**: need human approval |
| **One service window** where every request is checked | The **Tool Registry**: the only way to run a tool |
| A **checklist on the window** that says which requests need a signature | The **Tool Policy** |
| If a clerk does not know a request type, they **refuse and ask a manager** | **Unknown tools always need approval** |
| **Play money** used in staff training | **Mock integrations**: they pretend to refund, but no real money exists |

The key idea: **the AI never reaches the vault directly. It hands a slip to the window, and the window follows the checklist.**

---

## 4. The nine tools

| Tool | What it does | Changes anything? | Needs a human? |
|---|---|---|---|
| Get customer | Looks up who the customer is | No | No |
| Get subscription | Looks up their plan, seats and limits | No | No |
| Get ticket history | Lists their earlier tickets | No | No |
| Search docs | Searches the help library from Phase 5, with citations | No | No |
| Check service status | Is any service currently having an incident? | No | No |
| Update ticket | Changes a ticket's status, category or summary | Yes (the ticket only) | No |
| Create escalation | Hands the ticket to a specialist team and notifies them | Yes | **No**: it is the *safe* path |
| **Create refund request** | Starts a refund | **Yes: money** | **Yes** |
| **Reset a setting** | Changes a workspace setting such as external sharing | **Yes: an account** | **Yes** |

Why does escalation need no approval? Because handing a problem to a human expert is always the cautious choice. We want it to be easy.

---

## 5. How one tool call travels

```text
 The AI (or the workflow) says:  "run create_refund_request, amount 24"
                    │
                    ▼
        ┌──────────────────────────┐
        │   THE TOOL REGISTRY      │   (the one service window)
        │                          │
        │  1. Ask the Tool Policy: │
        │     does this need a     │
        │     human?               │
        └───────────┬──────────────┘
                    │
        ┌───────────┴───────────┐
   YES, and nobody          NO, or a human
   approved yet             already approved
        │                        │
        ▼                        ▼
  STOP. Return             2. Run it, with a time limit
  "approval required".        (default 30 seconds)
  Nothing happens.            │
                              ▼
                       3. Success or failure?
                          Either way, hand back a
                          tidy result. Never crash.
```

Four small promises the window keeps:

1. **No signature, no action.** A refund without approval does nothing at all. There is a test that proves it.
2. **Unknown requests are refused.** If something asks for a tool we never built, it is treated as needing approval, and then reported as unknown.
3. **A slow tool cannot hang the system.** Every tool has a time limit.
4. **A broken tool cannot crash the system.** Errors become a calm "this failed, here is why" message, and the workflow carries on.

---

## 6. The pretend outside services

The real product would talk to a payments company, an email provider and a team chat. For the demo we do not want real money or real emails, so Phase 6 builds **mock** versions:

| Service | What the pretend version does |
|---|---|
| Billing | Writes down "refund of $24 requested" and gives it a fake id. No money moves. |
| Email | Writes down "email would be sent". Nothing is sent. |
| Team notifications | Writes down "security team would be paged". |
| Workspace admin | Writes down "setting would be changed". |

Each one keeps a **logbook** of what it was asked to do. This is how our tests prove something: *"the billing logbook is empty, so no refund happened."*

The tools only know the **job description** of these services (called a *protocol*), not the pretend version. So in the future, swapping the pretend billing for a real one means writing one new file, and **no tool has to change**.

---

## 7. What is proven by tests

Phase 6 adds **28 new tests**. The whole project now has **192 passing tests**, all running offline with no internet and no API keys.

| Promise | Test |
|---|---|
| Reading tools never need approval | Checked for all five |
| Refund and setting-reset always need approval | Checked |
| Unknown tools need approval | Checked |
| **A refund without approval writes nothing** | The billing logbook stays empty |
| The same refund *with* approval goes through the same path | Checked |
| A tool that crashes returns a failed result, not a crash | Checked |
| A slow tool is stopped at the time limit | Checked |
| A bad value (a made-up category) is rejected | Checked |
| An unlisted setting cannot be reset | Checked |
| An escalation is saved and the right team is notified | Checked |

---

## 8. What Phase 6 deliberately does *not* do

Being honest about this matters:

- **Nothing calls the toolbox yet.** The AI team arrives in Phase 8 and the workflow in Phase 9. Phase 6 builds and tests the toolbox on its own.
- **No approval screen yet.** The "pause and ask a human" step is Phase 10. Phase 6 only makes sure the toolbox *refuses* until told approval was given.
- **All outside services are pretend.** No real refunds or emails are possible in this version.

---

## 9. The 30-second summary to say out loud

> "Phase 6 gives the AI a toolbox of nine actions and, more importantly, one single doorway every action must pass through. At that doorway, a fixed rule, not the AI's opinion, decides whether the action may run alone or needs a human's approval. Looking things up is free. Moving money or changing an account always waits for a person. Every tool has a time limit and cannot crash the system. And because the outside services are pretend for now, we can demonstrate all of this safely. We have 28 new tests, including one proving that a refund without approval does nothing."

---

## 10. Where this fits

```text
Phases 1-5: the building, the filing cabinet, the guards, the reception desk, the library
   ──► Phase 6: THE TOOLBOX AND THE PERMISSION DESK  (you are here)
Phase 7:      the rulebook that spots dangerous tickets
Phases 8-10:  the AI team, the process, and the human approval gate
```

When Phase 10 adds the human approval screen, it will call **this same doorway** with "a human approved". No second, secret path exists.
