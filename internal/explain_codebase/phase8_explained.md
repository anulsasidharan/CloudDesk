# Phase 8 Explained: Memory, or How the System Remembers Customers

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

**CloudDesk** is a fictional company that sells online tools for teamwork: file storage, shared workspaces, billing. Customers write in with problems ("I can't log in", "I was charged for 8 seats but use 5"). Each message is a **ticket**.

We are building an **AI assistant that investigates tickets for the human support agent**. It works out how urgent the ticket is, looks up the customer, finds the right help article, suggests a fix and drafts a reply. **Anything that costs money or changes an account waits for a human to approve.**

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
| **8** | **Memory** | **Remembering each customer, safely.** |
| 9 | Specialist agents | The team of AI specialists. |
| 10 | Workflow graph and trace | The step-by-step process with a visible trail. |
| 11 | Approval and escalation | The "ask a human first" gate. |
| 12 | Agent console | The screen the agent uses. |
| 13 | Evaluation and delivery | Measuring quality and packaging for the cloud. |

*(The build order was adjusted: memory was pulled forward because it only needs the filing cabinet and the "black marker" from Phase 7. It does not need the AI team to exist yet.)*

---

## 3. What Phase 8 is

Imagine calling a company and having to explain your whole history again every single time. Annoying. Now imagine the opposite: the person who answers says, "Last month we fixed your login problem, and you prefer email." Much better.

Phase 8 gives CloudDesk that ability. It builds **two kinds of memory**:

| Memory | Analogy | What it holds | How long |
|---|---|---|---|
| **Short-term** | The sticky notes on a desk during a call | The back-and-forth of one ticket, and where the investigation currently is | 24 hours, then they fall off |
| **Long-term** | The customer's file in the cabinet | Facts about the customer worth keeping: past problems, fixes that were tried, how it was resolved | Permanent |

And a **memory service**, the librarian who sits in front of both and offers just two simple requests:

1. **Recall**: "What do we know about this customer?" (asked at the start)
2. **Record**: "Here is what happened, please file it." (asked at the end)

### 3.1 The three parts

| Part | Plain-words job |
|---|---|
| **Short-term memory** | Fast, temporary scratchpad. Forgets after a day. |
| **Long-term memory** | The permanent customer file. Cleans text before filing and never files the same thing twice. |
| **Memory service** | The one door the rest of the system uses: recall at the start, record at the end. |

---

## 4. Part one: short-term memory (the sticky notes)

Stored in **Redis**, a very fast in-memory store. Like sticky notes, it is quick to read and write but not meant to last.

It keeps:

- **The conversation for a ticket**: who said what (customer, agent, assistant). At most the newest 50 messages.
- **The workflow state**: a snapshot of where the investigation is up to.
- **The search cache** (already built in Phase 5): recent help-library answers kept for 5 minutes so repeated searches are instant.

Everything expires **24 hours** after the last update (the search cache after 5 minutes).

Two safety touches:

- Text is passed through the **black marker** (the scrub from Phase 7) before it is saved. Even sticky notes do not hold card numbers.
- **If Redis is down, nothing breaks.** The notes are a convenience, not a requirement, so a failure is logged and the ticket carries on. The system says "I could not save that" rather than crashing.

---

## 5. Part two: long-term memory (the customer file)

Stored in the **database** (the filing cabinet from Phase 2), in a table called `customer_memory`.

Four kinds of note exist:

| Kind | Example |
|---|---|
| **Preference** | "Prefers replies by email" |
| **Past issue** | "Charged for 8 seats but uses 5" |
| **Troubleshooting** | "Compared invoice with active seat count" |
| **Note** | "Resolution: refund for 3 seats requested" |

Every note goes through four steps before it is filed:

```text
 Text to remember
        │
        ▼
 1. BLACK MARKER   Card numbers, passwords and keys become [REDACTED:...]
        │
        ▼
 2. TIDY & TRIM    Extra spaces removed; kept to 500 characters
        │
        ▼
 3. DUPLICATE?     Same customer, same kind, same text already filed? Then skip it.
        │
        ▼
 4. FILE IT        Saved, with a link back to the ticket it came from
```

When **recalling**, the system returns the **10 newest notes** for that one customer. Never more, so the AI is not flooded, and never another customer's.

Only this one component is allowed to write to the customer file. Nobody else can sneak notes in, which keeps the safety checks in one place.

---

## 6. Part three: the memory service (the librarian)

### At the start: recall

When a ticket arrives, the system asks: "What do we know about this customer?" It gets back up to 10 notes. The AI specialists can then use this, for example "this customer had a similar billing issue before."

### At the end: record

When a ticket has been handled, the service files exactly **five notes**:

| # | Note | Example |
|---|---|---|
| 1 | One **past issue** | "Charged for 8 seats, uses 5" |
| 2 to 4 | The first **three troubleshooting steps** | "Check seat count", "Compare invoice", "Confirm usage" |
| 5 | One **resolution** note | "Resolution: refund for 3 seats requested" |

Notice what is **not** filed: the **raw text of the customer's message**. Only a short summary and the plan. That keeps private wording, and any pasted secrets, out of the permanent file.

### The "run it twice" test

If the same ticket is processed twice, the second time every one of the five notes is recognised as a duplicate and skipped. The customer's file does not grow with copies. This is the project's demo checkpoint: **running ticket CD-1002 (the refund) twice does not duplicate the resolution note.**

---

## 7. Why safety matters here

Memory is a risk if done carelessly. Three things must never happen, and each is protected:

| Danger | Protection |
|---|---|
| A card number, password or key ends up in a permanent file | The black marker runs before saving. A test saves secrets on purpose and checks none arrive in the database. |
| One customer's information appears in another's file | Notes are always saved and recalled using one customer's ID. A test checks that customer B only sees B's notes. |
| Memory trouble stops a support ticket | Short-term memory fails quietly. Long-term memory is only called at the edges of a run. |

---

## 8. What is proven by tests

Phase 8 adds **10 new tests**. The whole project now has **304 passing tests**, all offline with no AI model and no internet. (Redis is simulated by a stand-in called fakeredis.)

| Promise | Checked |
|---|---|
| Conversation is stored and expires in 24 hours | Yes |
| Only the newest 50 messages are kept | Yes |
| Secrets typed in a conversation are blacked out | Yes |
| Workflow state saves, expires and can be cleared | Yes |
| Redis being down does not crash anything | Yes |
| Search cache key format and 5-minute expiry | Yes |
| Long-term notes are cleaned and exact copies skipped | Yes |
| Recall returns at most 10 notes, and only for that customer | Yes |
| A finished ticket writes exactly 5 notes (issue, 3 steps, resolution) | Yes |
| Recording the same ticket twice adds nothing | Yes |
| Card, key and password never reach the database | Yes |

---

## 9. What Phase 8 deliberately does *not* do

- **Nothing calls memory yet.** The AI team (Phase 9) and the workflow (Phase 10) will ask for recall at the start and record at the end. Phase 8 builds and tests the memory alone.
- **Duplicates are exact-match only.** The same sentence worded differently is filed as a new note. Smarter "similar meaning" matching is a possible future improvement.
- **The scrub is pattern-based.** It catches common card, key and password shapes. It is a strong safety net, not a guarantee against every unusual secret format.
- **No "forget" feature yet.** There is no button to delete a customer's memory, which a privacy request may eventually need.
- **Redis is simulated locally.** The real Redis container arrives with the Docker work in the final phase.

---

## 10. The 30-second summary to say out loud

> "Phase 8 is memory. Short-term memory is a fast scratchpad that holds a ticket's conversation and progress for 24 hours. Long-term memory is the permanent customer file: past issues, what we tried, and how it was resolved. Everything is passed through our black-marker scrub first, so card numbers and passwords are never kept, and the same note is never filed twice. A small memory service gives the rest of the system two simple requests: recall what we know, and record what happened. We proved it with 10 new tests, including running the same refund ticket twice and checking nothing is duplicated."

---

## 11. Where this fits

```text
Phases 1-7:  building, cabinet, guards, reception, library, toolbox, rulebook
   ──► Phase 8: MEMORY  (you are here)
Phase 9:      the AI specialists, who recall at the start of a ticket
Phase 10-11:  the process, and the human approval gate; the record step runs at the end
Phase 12-13:  the screen the agent uses; quality checks and cloud packaging
```

The AI team will no longer treat every customer as a stranger.
