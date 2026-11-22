# Phase 14 Explained: The Final Exam and the Shipping Box

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

**CloudDesk** is a fictional company that sells online tools for teamwork: file storage, shared workspaces, billing. Customers write in with problems ("I can't log in", "I was charged for 8 seats but use 5"). Each message is a **ticket**.

We built an **AI assistant that investigates tickets for the human support agent**. It judges how urgent the ticket is, looks up the customer, finds the right help article, suggests a fix and drafts a reply. **Anything that costs money or changes an account waits for a human to approve.**

Phases 1 to 13 built the brain, the safety rules and the screen the agent works on. **Phase 14 asks two last questions: "Is it good enough?" and "Can we ship it?"**

---

## 2. The phases at a glance

| Phase | Name | In plain words |
|---|---|---|
| 1 to 3 | Foundation, data, security | The building, the filing cabinet, the guards at the door |
| 4 to 5 | Support API, knowledge | The reception desk and the searchable help library |
| 6 to 8 | Tools, rules, memory | The toolbox, the rulebook, remembering each customer |
| 9 to 11 | Agents, workflow, approval | The AI team, the assembly line, the "ask a human first" gate |
| 12 to 13 | Console | The front door and the agent's cockpit |
| **14** | **Evaluation and delivery** | **The final exam, and the shipping box** |

---

## 3. What Phase 14 is

Think of a **new car about to leave the factory**.

| Car factory | CloudDesk Phase 14 |
|---|---|
| Crash and emissions tests with a pass mark | **Five quality scores.** If any falls below its pass mark, the build fails. |
| Putting the car in a standard shipping container | **Docker images**: the app packed so it runs the same everywhere |
| One instruction sheet that starts the whole line | **Docker Compose**: one command starts the four parts together |
| Blueprints for the dealerships in three countries | **Terraform plans** for Amazon, Microsoft and Google clouds |
| The inspector's checklist | **Automated checks** on the packaging and the safety of the files |

---

## 4. Part one: the final exam (five scores)

We keep a list of **27 sample tickets** with the right answers written down. The system answers each one and we mark it.

| What is measured | Plain meaning | Pass mark |
|---|---|---|
| Classification accuracy | Did it label the ticket correctly (billing, login, security...)? | 80% |
| Retrieval hit-rate | Did the right help article show up in its top three? | 75% |
| Escalation correctness | Did it send the risky tickets to the right specialist team, and leave the safe ones alone? | 90% |
| Citation rate | Does every reply point to a help article as its source? | 90% |
| Grounding rate | Does the reply actually include the fix steps the AI worked out? | 90% |

**Why this matters:** the exam runs **offline with no paid AI service**, in under a second. Anyone who later changes the code and accidentally makes the assistant worse will see the build go red **before** it reaches a customer.

---

## 5. Part two: the shipping box

### 5.1 Two Docker images
An image is a sealed box holding the app and everything it needs.
- **Backend box:** the Python brain. Built in two steps so the final box has no build tools in it (smaller, safer).
- **Frontend box:** the web screen.
- Both boxes run as an **ordinary user, not the all-powerful administrator**, so a break-in would have less power.
- Both have a **heartbeat check**: Docker asks "are you alive?" every 15 seconds and restarts the box if not.

### 5.2 Docker Compose: four parts, one command
`docker compose up` starts four containers in the right order:

1. **Redis** (short-term memory and the rate limiter)
2. **Qdrant** (a search database, reserved for later)
3. **Backend** (waits until Redis and Qdrant report healthy)
4. **Frontend** (waits until the backend reports healthy)

It is like opening a restaurant: kitchen equipment on, then the chefs, then the doors.

### 5.3 Terraform: blueprints for the cloud
Terraform describes cloud buildings as text files. We wrote starter blueprints for **AWS, Azure and Google Cloud**, with three versions each: dev, staging, production. The secrets (passwords, keys) are **never** written in these files.

### 5.4 Automatic checks (CI)
Five GitHub workflows run tests, scan for leaked secrets, build the images, validate the blueprints and, for production, **require a named human reviewer before anything is applied**. The image shipped is tagged with the exact code version that was tested.

### 5.5 The inspector's checklist
19 automatic tests confirm: containers don't run as admin, heartbeats exist, services start in order, no secret file is saved in the repository, the deploy script refuses "skip approval" for staging and production.

---

## 6. A real example: the test that caught a mistake

While building this phase, the checklist **failed**: the web-screen container in Compose had no heartbeat check. The test caught it, we added it, and everything went green. That is exactly what the checklist is for.

---

## 7. Honest status: what is done and what is not

This matters, so we say it plainly.

| Item | Status |
|---|---|
| Five quality scores, enforced | **Done. Passing locally** (432 tests in total pass offline) |
| Dockerfiles and Compose file | **Written. Compose file validated.** The Docker engine was **not running** on this machine, so the images were **never built or started** |
| Terraform blueprints | **Written. Not validated** (the Terraform tool is not installed here) and **not applied** |
| GitHub workflows | **Written. Never executed**; the repository has not been pushed with secrets configured |
| Anything running in a real cloud | **No.** No cloud account was used |
| Qdrant | A container is defined, but the app still uses its built-in in-memory search. Connecting to Qdrant is future work |

---

## 8. If you remember only five lines

1. Phase 14 is **the final exam plus the shipping box**.
2. Five quality scores must pass or the build fails, with **no paid AI needed**.
3. Docker packs the app; Compose starts four parts in order; Terraform sketches three clouds.
4. Safety is automated: **no admin users, no secrets in the repository, no production change without a human reviewer**.
5. We **do not claim it is deployed**. It is built and checked locally; cloud rollout is the next step.
