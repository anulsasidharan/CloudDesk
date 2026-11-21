# Phase 1: Interview Questions and Answers

*CloudDesk: Autonomous Customer Support & Resolution Platform*

**Phase 1: Runtime skeleton.** Settings, JSON logging, health checks, request tracking IDs, an offline test harness and developer tooling.

Questions are grouped from general (suitable for any panel member) to deep technical. Each answer is written to be said out loud. Short follow-up points are marked **Follow-up**.

| Section | Audience |
|---|---|
| A. Project and phase overview | Everyone |
| B. Design decisions and trade-offs | Everyone / engineering managers |
| C. Settings and secrets (P1-1) | Technical |
| D. Structured logging (P1-1) | Technical |
| E. Request ID middleware (P1-2) | Technical |
| F. Health checks (P1-2) | Technical / DevOps |
| G. CORS and routing (P1-2) | Technical |
| H. Testing (P1-3) | Technical / QA |
| I. Developer tooling (P1-4) | Technical |
| J. Infrastructure and future readiness | DevOps / architects |
| K. Security | Security-minded panel members |
| L. Process, behavioural and lessons learned | Everyone |
| M. Rapid-fire | Everyone |

---

## A. Project and phase overview

### A1. What is CloudDesk, in one sentence?
An AI assistant for customer-support agents. It reads a support ticket, investigates it (customer history, help articles, likely cause) and drafts a resolution, while a human approves anything that costs money or changes an account.

### A2. Who uses it?
Support agents, not customers. There are three roles: **viewer** (read only), **agent** (can run the AI, reply and approve) and **admin** (can also change settings and rebuild the knowledge index).

### A3. Why did you split the project into phases?
Each part depends on the one before it, like building a house: foundation, walls, wiring, furniture. With phases, every step is small, testable and demonstrable. The project has 13 phases (the task tracker splits the work into 14): runtime skeleton, data, identity, API, knowledge, tools, rules, agents, workflow, approvals, memory, console, and evaluation and delivery.

### A4. What did Phase 1 deliver?
The foundation, with no AI yet:
1. A **settings panel** that reads every configuration value from the environment, defaults to offline demo mode and hides secrets.
2. A **structured JSON logbook** where every line carries a `request_id` and a `workflow_id`.
3. A **web server** with three health checks: `/health`, `/health/live` and `/health/ready`.
4. **Request tracking numbers** (`X-Request-ID`) on every response.
5. An **offline test harness** and developer commands (`make setup / backend / test / lint`, `.env.example`).

### A5. Why is there no AI in Phase 1?
Because the AI needs the foundation underneath it. Logging, tracing, safe errors, configuration and tests are much harder to add afterwards. Building them first means every later feature, including the AI, gets them automatically.

### A6. Which requirements does Phase 1 satisfy?
**F14**: the system runs offline in demo mode with no API key. **N3**: every response carries an `X-Request-ID`. It also lays the groundwork for N2 (rate limit) and N6 (audit) by fixing the middleware order in advance.

### A7. How would you explain Phase 1 to a non-technical person?
"Before a restaurant serves food, it needs a building with power, a way to check the kitchen is safe to open, and a logbook of every order. Phase 1 built those for our software."

### A8. What is the tech stack?
Python 3.12, FastAPI, Pydantic v2 and pydantic-settings, Uvicorn, pytest, ruff, and `uv` for dependency management. Later phases add SQLAlchemy, LangGraph/LangChain, Redis, Qdrant and a Next.js frontend.

---

## B. Design decisions and trade-offs

### B1. What does "offline-first" mean, and why did you choose it?
By default the system uses stand-ins for everything external: a fake AI provider, in-memory vector store, fake Redis and a local SQLite file. Anyone can run and test it on a laptop with no internet, no paid keys and no Docker. That keeps tests fast and reproducible and removes cost and secret-handling risk from development and demos.
**Follow-up:** switching to real services is purely configuration (environment variables). No code changes.

### B2. Why configure through environment variables instead of a config file?
This is the twelve-factor app approach. Containers, CI and every major cloud inject configuration as environment variables, and secret managers expose secrets the same way. One code path then works on a laptop, in Docker and in AWS, Azure or GCP. A local `.env` file is supported only as a developer convenience.

### B3. Why build health checks this early?
Container platforms and load balancers rely on them to decide whether to restart a container or send it traffic. Defining them now, with the right semantics (live versus ready), means the Docker and cloud phases plug straight in.

### B4. Why fix the middleware order in Phase 1 when only two middlewares exist?
Order affects behaviour. The project defines it as CORS → RequestId → RateLimit → Audit. Request ID must run before rate limit and audit, so that rejected or audited requests still carry a tracking number. Writing this down now means Phase 3 slots in without reshuffling anything or breaking tests.

### B5. What is the layering rule, and how does Phase 1 follow it?
The code is split into layers: API, services, repositories, core, tools, agents, RAG, memory and integrations. Each layer has one job and a list of things it must not do. Phase 1 touches only **API** (HTTP only, no business rules), **middleware** and **core** (config, logging, readiness, database stub). Core must never import agents, so the foundation never depends on the AI.

### B6. What trade-offs did you accept?
- **Cached settings:** fast and consistent, but you must restart after changing `.env`.
- **Readiness checks configuration only, not real connectivity, for now:** honest and fast, but it cannot detect a dead remote database yet. It reports remote services as "not probed yet" and returns 503 instead of pretending they are fine.
- **Pure ASGI middleware:** more code than FastAPI's helper class, but correct context propagation (see E4).

### B7. How did you keep scope under control?
Each subtask (P1-1 to P1-4) had its own branch, files, tests and exit criteria from the phase plan. Anything that belonged to a later phase, such as real database connections or auth, was explicitly left as a stub or a documented placeholder.

---

## C. Settings and secrets (P1-1)

### C1. How are settings loaded?
A `Settings` class (pydantic-settings) declares every variable from the environment contract with a type and a default. Values come from environment variables, then from a `.env` file at the repo root if one exists, then from defaults. `get_settings()` returns one instance.

### C2. Why is `get_settings()` wrapped in `lru_cache`?
To read and validate the environment only once per process. It is fast and gives every part of the app the same view of configuration. In tests, `get_settings.cache_clear()` forces a fresh read after changing environment variables.

### C3. What are the default values, and why those?
`DEMO_MODE=true`, `LLM_PROVIDER=fake`, `EMBEDDING_PROVIDER=fake`, `VECTOR_STORE=memory`, an empty `REDIS_URL` (which means fakeredis), `DATABASE_URL=sqlite+aiosqlite:///./data/support.db`, `CORS_ORIGINS=http://localhost:3000`, `APPROVAL_REQUIRED_FOR_REFUNDS=true` and `MAX_REFUND_WITHOUT_APPROVAL=0`. The defaults are always the safe, offline and most restrictive choice.

### C4. How are secrets protected?
Secret fields (`JWT_SECRET`, `SUPABASE_JWT_SECRET`, `LLM_API_KEY`, `QDRANT_API_KEY`, `LANGCHAIN_API_KEY`) are typed as `SecretStr` and excluded from `repr`. A custom serializer turns them into `**********` in `model_dump()`. `DATABASE_URL` and `REDIS_URL` are also excluded from `repr`, and any password embedded in them is masked as `scheme://***@host/...`.
**Follow-up:** the code that opens a connection reads the real value directly from the object. Only printed or serialised forms are redacted.

### C5. What is `effective_jwt_secret`?
A property that returns the Supabase JWT secret if one is set, and `JWT_SECRET` otherwise. The same auth code then works with demo-issued tokens and with Supabase tokens in production. It is used from Phase 3.

### C6. How do you stop invalid configuration?
Types and validators. `VECTOR_STORE` is a `Literal["memory", "qdrant"]`, so any other value fails at start-up. Provider names and environment are normalised (trimmed, lower-cased). Numbers and booleans are parsed and validated by Pydantic.

### C7. What happens with unknown environment variables?
They are ignored (`extra="ignore"`). Container platforms inject many unrelated variables, and the app must not crash because of them.

### C8. How do you decide between fakeredis and real Redis?
The `uses_fake_redis` property is true when `USE_FAKE_REDIS` is set or `REDIS_URL` is empty. An empty value therefore means "use the offline stand-in", which is the safe default.

### C9. How are multiple CORS origins configured?
`CORS_ORIGINS` is a comma-separated string. `cors_origin_list` splits it, trims each entry and drops empty ones.

---

## D. Structured logging (P1-1)

### D1. Why JSON logs instead of plain text?
Machines can search and filter them reliably. Log platforms such as CloudWatch, Log Analytics, Cloud Logging and Datadog index JSON fields automatically, so you can query "all lines for request_id X" without fragile text parsing.

### D2. What fields does each log line have?
Exactly these: `timestamp` (UTC, ISO-8601), `level`, `logger`, `message`, `request_id` and `workflow_id`, plus `exception` when there is one. Unset IDs are JSON `null`.

### D3. Why a fixed set of fields? Why not copy every extra attribute?
Predictability and safety. Copying arbitrary extra attributes risks leaking sensitive data into logs and makes the schema unstable for dashboards.

### D4. How does each log line get the right `request_id` without passing it around?
Through Python `contextvars`. `log_context(request_id=...)` sets a context variable for the current task. A logging filter and the formatter read it and stamp it on every line. When the block exits, the previous value is restored using the context-variable tokens.

### D5. Why `contextvars` and not a global variable or thread-local?
The app is async. Many requests run concurrently on one thread, so a global or a thread-local would mix up IDs between requests. Context variables are isolated per asyncio task, which makes them correct for async servers.

### D6. What does `log_context` do when you pass only one ID?
It changes only the ID you passed. Omitted arguments are left unchanged, thanks to a private `_UNSET` marker. This allows nesting, for example a workflow block inside a request block, and the outer values come back when the inner block ends.

### D7. Why does `setup_logging()` remove existing handlers?
To guarantee exactly one JSON handler. Calling it twice, or after another library attached a handler, must not produce duplicate lines or mixed formats. A test checks this.

### D8. How are exceptions logged?
The traceback goes into a single `exception` field in the same JSON object, so a stack trace never breaks the one-line-per-event rule.

### D9. Where do logs go?
Standard output. In containers, the platform collects stdout, so the app never manages log files.

---

## E. Request ID middleware (P1-2)

### E1. What is a request ID, and why does it matter?
A unique tracking number for each HTTP request, returned in the `X-Request-ID` header and written on every log line. When a user reports a problem, you can find every log line for that exact request in seconds.

### E2. Do you trust an `X-Request-ID` sent by the caller?
Only if it is safe. It must match a strict pattern: letters, digits and `._:-`, starting with an alphanumeric character, up to 128 characters. Otherwise a new UUID replaces it. Keeping a valid upstream ID lets traces continue through a load balancer or gateway.

### E3. Why validate it at all?
To prevent log injection and header forgery. An attacker could send newlines or control characters to fake log entries or split headers. Rejecting anything outside the safe pattern closes that hole.

### E4. Why write it as pure ASGI middleware instead of `BaseHTTPMiddleware`?
`BaseHTTPMiddleware` runs the downstream app in a separate task, so context variables set in the middleware may not be visible to route handlers and background tasks. Pure ASGI middleware calls the app in the same task, so the `request_id` context reliably reaches every log line. It also has less overhead.

### E5. How does the ID get onto the response?
The middleware wraps the ASGI `send` function. When it sees the `http.response.start` message, it adds the `X-Request-ID` header. This works for every response, including 404s and errors.

### E6. Where else is the ID stored?
On `request.state.request_id`, so handlers and later middleware (such as audit in Phase 3) can read it.

### E7. What happens if a handler crashes?
If no response has started yet, the middleware logs the full exception with the request ID and returns a clean `500 {"detail":"Internal Server Error"}` with the same `X-Request-ID`. No stack trace or internal detail reaches the client. If the response had already started, the error is re-raised, because a second response cannot be sent.

### E8. Which requirement is this?
N3: `X-Request-ID` on every response. Tests cover generated IDs, echoed IDs, replaced unsafe IDs, IDs on 404 and on 500, the ID in log lines, clearing it after the request, and CORS exposure.

---

## F. Health checks (P1-2)

### F1. What are the three health endpoints?
- `GET /health`: identity. Status `ok`, service name, version and environment.
- `GET /health/live`: liveness. Returns `alive` and touches nothing.
- `GET /health/ready`: readiness. Checks the database, Redis, vector store and LLM configuration, and returns `ready`, or `degraded` with HTTP **503**.

### F2. What is the difference between liveness and readiness?
Liveness asks "is the process stuck or dead, and should it be restarted?" Readiness asks "can it serve traffic right now, and should it get requests?" They lead to different actions: restarting the container versus routing traffic away from it.

### F3. Why must `/health/live` do no I/O?
If liveness depended on the database, a short database outage would make the platform restart every backend container. That does not fix the database and causes a cascading outage. Liveness reflects only the process itself.

### F4. Why return 503 when degraded instead of 200 with a message?
Load balancers and orchestrators look at status codes, not response bodies. A 503 tells them to take the instance out of rotation automatically.

### F5. What does readiness actually check in Phase 1?
Configuration only. No network connections are opened. Offline backends (SQLite, fakeredis, the in-memory vector store, the fake LLM) count as `ok`. A remote backend reports `error` with "connectivity is not probed yet" until its real client and connection check exist in later phases.

### F6. Isn't reporting remote services as errors a problem?
It is deliberate honesty. Reporting "ready" for a service we have never contacted would be a false positive. Once the real clients exist, the check becomes a real connectivity probe.

### F7. Do health error messages leak anything?
No. The `detail` field never contains URLs, hostnames, passwords or keys. A test sets secret-bearing URLs and keys and asserts that none of them appear in the response.

### F8. Why are health routes not under `/api/v1`?
Probes should be stable and independent of API versioning, and they must not require authentication once auth arrives in Phase 3.

### F9. Why are response shapes Pydantic models?
`HealthResponse`, `LiveResponse` and `ReadyResponse` enforce the exact shapes in `API_CONTRACT.md`, generate accurate OpenAPI docs, and stop accidental extra fields from leaking.

---

## G. CORS and routing (P1-2)

### G1. What is CORS, and why do you need it?
Browsers block a page from one origin (the console on `localhost:3000`) from reading responses from another origin (the API on `localhost:8000`) unless the server allows it. CORS middleware tells the browser which origins are permitted.

### G2. Why expose `X-Request-ID` in CORS?
By default, browser JavaScript can read only a few "simple" response headers. `expose_headers=["X-Request-ID"]` lets the frontend read the tracking number and show it in error banners or support reports.

### G3. Why is CORS the outermost middleware?
It must answer browser pre-flight (`OPTIONS`) requests and add CORS headers to every response, including error responses produced by inner layers.

### G4. In FastAPI, middleware added last runs first. How did you handle that?
`RequestIdMiddleware` is added first and `CORSMiddleware` second, so CORS is outermost and the request passes CORS → RequestId → router. Comments in `main.py` record this.

### G5. What is the app factory (`create_app`), and why use one?
A function that builds and configures the FastAPI app: logging, settings, middleware and routers. It keeps start-up explicit and testable. Tests can build a fresh app after changing the environment.

---

## H. Testing (P1-3)

### H1. How do tests run with no internet and no API keys?
`tests/conftest.py` sets the offline environment **before** importing the app: `DEMO_MODE=true`, `LLM_PROVIDER=fake`, `EMBEDDING_PROVIDER=fake`, `VECTOR_STORE=memory`, `USE_FAKE_REDIS=true`, a temporary SQLite database, `CHECKPOINT_DB_PATH=:memory:` and a test-only JWT secret.

### H2. Why must the environment be set before importing the app?
Settings are cached on first read, and the app is created at import time. If the import came first, the app would capture the developer's real `.env` values.

### H3. How do you test HTTP endpoints without starting a server?
FastAPI's `TestClient` calls the ASGI app directly in memory. No port is opened and nothing touches the network, yet the full middleware and routing stack runs.

### H4. Which behaviours are tested?
- **Settings:** fields match the environment contract, offline defaults need no API key, environment overrides, caching and cache-clearing, JWT secret precedence, the fakeredis rule, CORS splitting, an invalid vector store rejected, secrets hidden in `repr` and dumps.
- **Logging:** IDs on every line, extra fields ignored, context restored after nesting, exceptions on one line, handlers replaced.
- **API:** all three probes, ready versus degraded with 503, no secret leakage, request ID generated, echoed and replaced, the ID on 404 and on 500, the ID in log lines and cleared afterwards, CORS exposure, the ID on request state.

### H5. How do you test that logs contain the request ID?
A fixture points `setup_logging` at an in-memory `StringIO` buffer. The test makes a request, parses the JSON lines and asserts that `request_id` equals the response header. It also checks the ID is `null` once the request ends.

### H6. Why does the test database live in a temp folder?
So tests never touch the developer's real `./data/support.db`, and each run starts clean.

### H7. How are async tests configured?
`asyncio_mode = "auto"` with session loop scope in `pyproject.toml`, and `pythonpath = ["backend"]` so `import app` works. Tests must not mix in `@pytest.mark.asyncio` with a different scope.

### H8. How do tests map to requirements?
Test names reference the requirement where it matters, for example `test_f14_offline_defaults_need_no_api_key`. The project rule is that every requirement maps to at least one test.

---

## I. Developer tooling (P1-4)

### I1. What does the Makefile provide?
- `make setup`: `uv sync`, then copies `.env.example` to `.env` only if `.env` is missing.
- `make backend`: runs Uvicorn with reload on port 8000.
- `make test`: pytest.
- `make lint`: ruff.

### I2. What is `.env.example`, and why commit it?
A template listing **every** environment variable the app uses, with placeholder values only. It documents the configuration contract and is what a container or cloud deployment must supply. The real `.env` is git-ignored.

### I3. How do you make sure `.env.example` stays complete?
A test checks that the `Settings` fields match the environment contract. The final delivery phase adds a deployment test that checks `.env.example` covers every variable and that no `.env` is committed.

### I4. Why `uv`?
A fast, reproducible Python package manager with a lockfile (`uv.lock`). Every machine and CI run gets the same dependency versions.

### I5. How do you run it on Windows without `make`?
Call the commands directly with `.venv/Scripts/python.exe`. `PYTHONPATH` must include `backend` (`;` separator on Windows), and `PYTHONIOENCODING=utf-8` keeps CLI output with symbols readable.

---

## J. Infrastructure and future readiness

### J1. Is Phase 1 containerised?
No. Dockerfiles, Compose, Terraform and CI arrive in the final delivery phase. Phase 1 still makes the decisions the containers rely on: port 8000, environment-variable configuration, stdout JSON logs, liveness and readiness probes, CORS for the frontend origin, and request IDs.

### J2. How will Docker use the Phase 1 health checks?
The backend Dockerfile's `HEALTHCHECK` calls `/health/live`. Compose uses `depends_on: condition: service_healthy` so services start in order. Cloud load balancers use `/health/ready` to decide where traffic goes.

### J3. How does the request ID work behind a load balancer?
If the load balancer or gateway sets a safe `X-Request-ID`, the backend keeps it, so one ID follows the request across hops and appears in all logs.

### J4. How does the same code run on AWS, Azure and GCP?
All configuration is environment variables, logs go to stdout and health checks follow the standard conventions. Each cloud's container service (ECS Fargate, Container Apps, Cloud Run) injects variables and secrets and reads stdout. No code is cloud-specific.

### J5. Why does Uvicorn bind to 127.0.0.1 locally but 0.0.0.0 in a container?
Locally, binding to loopback keeps the dev server private to the machine. Inside a container, it must listen on all interfaces so the Docker network and the load balancer can reach it.

### J6. How would you scale this?
The backend is stateless per request: configuration comes from the environment, and state will live in the database, Redis and checkpoints. You scale horizontally by running more containers behind the load balancer, and readiness keeps unhealthy instances out of rotation. Long-running AI workflows are planned to move from in-process background tasks to a worker in a later extension.

---

## K. Security

### K1. What security measures exist in Phase 1?
- Secrets are hidden in all printed and serialised forms, and URL passwords are masked.
- Request IDs are validated (log-injection defence).
- Clients get a generic 500, and details stay in the logs.
- Health responses never include URLs or keys.
- CORS allows only configured origins.
- `.env` and data files are git-ignored, and `.env.example` holds only placeholders.

### K2. What is log injection, and how did you prevent it?
An attacker puts newlines or crafted text into a value that gets logged, to forge entries or break log parsers. Prevention here comes from two things. Caller-supplied request IDs must match a strict safe pattern, and every line is JSON-encoded with ASCII escaping, so embedded newlines cannot create new lines.

### K3. Why not show the stack trace to the user? It would help debugging.
Stack traces reveal file paths, library versions and sometimes data. That is useful to an attacker. Developers get the same information in the logs, linked by the request ID the user can quote.

### K4. Where do real secrets live?
Locally, in the git-ignored `.env`. In the cloud, in a secrets manager (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager), injected as environment variables. Never in code, images or committed files.

### K5. What comes in Phase 3?
JWT authentication (HS256, Supabase-compatible), role checks (viewer, agent and admin, where a viewer gets 403 on actions), rate limiting in Redis and an audit log of every state-changing request, all in the order fixed in Phase 1.

---

## L. Process, behavioural and lessons learned

### L1. How did you organise the work?
From a single source of truth (`CLAUDE.md`), a phase plan with goals, files, tests and exit criteria, and a task list with one feature branch per subtask (P1-1 to P1-4). Each branch opens a pull request against `development`, which is later promoted to `testing` and then `main`.

### L2. How did you keep status honest?
The project tracks *implemented*, *validated locally*, *needs cloud credentials* and *actually deployed* separately. The status file never says "deployed" or "passes in CI" until that has happened. For Phase 1: implemented and tested locally, with no cloud credentials used and nothing deployed.

### L3. Tell us about a problem you hit in this phase and what you learned.
When two branches of the request-ID and app-entry work were merged, the merge combined two versions of `main.py` and `request_id.py` without resolving them, and some dependencies in `pyproject.toml` were duplicated. The files no longer compiled. Lessons:
1. After every merge, run at least a syntax check or the test suite before pushing.
2. Protect the integration branches with a required CI test run, so a broken merge cannot be merged.
3. Keep feature branches short-lived to reduce overlapping edits.
I'd answer this openly: catching it, explaining the cause and adding a safeguard matters more than pretending it never happened.

### L4. How did you use AI coding tools in this project?
As an assistant inside a defined process. Project rules and plans constrain what it writes. Each change is tied to a requirement and a test, and changes are reviewed before merging. The architectural decisions and the policy rules (approvals, escalations) are mine and are tested deterministically.

### L5. If you started Phase 1 again, what would you change?
I'd add a CI workflow running ruff and pytest on every pull request from day one, instead of waiting for the delivery phase. That would have caught the broken merge automatically.

### L6. How does Phase 1 show production thinking, given that it's a demo project?
It covers the concerns that distinguish production systems: observability (structured logs and request tracing), operability (correct probes), security (secret handling, safe errors, input validation), reproducibility (offline tests and a lockfile) and portability (environment-variable configuration). Those concerns are there before any feature code.

---

## M. Rapid-fire

| Question | Answer |
|---|---|
| Backend port? | 8000 |
| Frontend origin allowed by CORS? | `http://localhost:3000` |
| Header name for tracing? | `X-Request-ID` |
| Max length of an accepted request ID? | 128 characters |
| What replaces an unsafe request ID? | A new UUID |
| Liveness endpoint? | `/health/live`, returns `alive`, no I/O |
| Readiness failure status code? | 503 |
| Readiness states? | `ready` / `degraded` |
| Components readiness checks? | database, redis, vector_store, llm |
| Default LLM provider? | `fake` |
| Default vector store? | `memory` |
| Default database? | `sqlite+aiosqlite:///./data/support.db` |
| When is fakeredis used? | `USE_FAKE_REDIS=true` or empty `REDIS_URL` |
| How are secrets shown? | `**********` |
| Log format? | One JSON object per line on stdout |
| IDs on every log line? | `request_id`, `workflow_id` |
| Mechanism for per-request IDs? | `contextvars` |
| Why pure ASGI middleware? | Context reaches handlers and background tasks |
| Middleware order (final)? | CORS → RequestId → RateLimit → Audit |
| Settings cache? | `lru_cache`; restart after `.env` changes |
| Test client? | FastAPI `TestClient`, in-memory |
| Requirements covered? | F14, N3 |
| Lint tool? | ruff |
| Dependency manager? | uv |
| Deployed to cloud? | No, not yet |
