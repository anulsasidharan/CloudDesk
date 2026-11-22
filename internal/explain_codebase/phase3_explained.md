# Phase 3 Explained: The Security Guards

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
| **3** | **Identity and request guards** | **The security guards at the door.** |
| 4 | Support API | The reception desk: create and read tickets. |
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

## 3. What Phase 3 is

By the end of Phase 2 we had a filing cabinet full of customer data. But **anyone who could reach the system could read it.** Phase 3 puts guards at the door.

Think of an office building with four security measures:

| In the building | In our system |
|---|---|
| A **badge** that proves who you are | A signed **login token** |
| Badge **colours** deciding which rooms you may enter | **Roles**: viewer, agent, admin |
| A **turnstile** that stops one person rushing the door 1,000 times a minute | The **rate limiter** |
| A **visitor logbook** noting who did what, and when | The **audit log** |

### 3.1 The badge: login tokens

When a person logs in, the system hands them a **token**. Think of it as a tamper-proof ticket stamped with three facts: *who you are, what role you have, and when it expires.* It is "signed" with a secret that only our server knows, so if anyone changes a single letter, the signature no longer matches and the token is rejected.

- Tokens last **8 hours**, like a day pass.
- The token **never contains the secret** or any password.
- For the demo, there is a **demo login button** with three ready-made people: an admin, an agent (Sam) and a viewer (Vic). No passwords are needed, and this only works while the system is in demo mode.

### 3.2 The colours: three roles

| Role | Can do |
|---|---|
| **Viewer** | Look, but not touch. |
| **Agent** | Everything a viewer can, plus run the AI, reply, approve, escalate. |
| **Admin** | Everything, plus settings and re-indexing the help library. |

Each higher role includes everything below it. If you have no badge, you hear **"401: who are you?"** If you have a badge but the wrong colour, you hear **"403: you're not allowed in here."** One of our company's golden rules is that **a viewer must never be able to approve a refund**, and this is how it is enforced.

If a token arrives with no recognisable role, we give it the **lowest** role. When unsure, grant less.

### 3.3 The turnstile: rate limiting

A badly written program (or an attacker) could hammer the system with thousands of requests. The turnstile counts requests per visitor each minute, and after 120 it says **"slow down, come back in a few seconds"** (error 429). The counter lives in a fast scratch-pad memory called Redis, and each counter wipes itself after a minute.

Two sensible touches:
- **If the scratch-pad breaks, we let people through** rather than lock everyone out. A broken turnstile should not shut the building.
- **Health checks are never limited**, because the cloud platform pings those constantly to see whether we are alive.

### 3.4 The logbook: the audit trail

Every time somebody **changes** something (anything other than just looking), the system writes one line: *who, what, which address, whether it worked, and a reference number.* It never records the contents of what they sent, so passwords and personal details do not leak into the logbook. If the logbook itself fails, the original action still completes. The log must not become a reason for customers to see errors.

### 3.5 The order of the guards

The guards stand in a fixed sequence, and the order matters:

1. **Cross-origin check:** is this request from our own website?
2. **Reference number:** stamp the request so we can trace it everywhere.
3. **Turnstile:** too many requests? Stop here.
4. **Logbook:** note any change that is made.
5. **The actual work.**

The turnstile sits *before* the logbook so that an attacker flooding us cannot also flood our database with log lines.

---

## 4. How we know it works

We wrote **23 new automated tests**, bringing the total to 91, all passing. Highlights:

- No token → rejected. Fake or expired token → rejected. Token signed with the wrong secret → rejected.
- Vic the viewer is turned away from a change-making route (403). Sam the agent and the admin are let in.
- A change creates a logbook line; just looking does not.
- The turnstile blocks the 4th request when the limit is 3, and starts fresh in the next minute.
- If Redis is down, requests still go through.
- The login response never contains our signing secret.
- The guard order is exactly as designed.

---

## 5. What is honest to say is *not* done

- The tests use an **in-memory stand-in for Redis**. The code to talk to a real Redis server is written but has **not been tried against one**.
- Demo login has no passwords by design. A real deployment would use a proper identity provider (Supabase), and our token checker already understands its format.
- There are **no actual support routes yet** to protect. The guards are proven on test routes. Phase 4 builds the real ones and puts the guards on them.
- Nothing is deployed to the cloud.

---

## 6. The 30-second version to say out loud

> "Phase 3 is the security layer. Users get an 8-hour signed token, and every route can demand a minimum role: viewer, agent or admin. So a read-only viewer can never approve a refund. A rate limiter in Redis stops flooding, and an audit log records who changed what. The guards run in a deliberate order, and 23 new tests prove each one, including the failure cases."

---

## 7. Where Phase 3 fits

```text
Phase 1: the building stands.        Phase 2: the filing cabinet is full.
Phase 3: guards at the door.   <-- we are here
Phase 4: the reception desk opens, and the guards are already on duty.
```
