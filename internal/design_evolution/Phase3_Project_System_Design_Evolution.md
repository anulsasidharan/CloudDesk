# Phase 3: System Design Evolution

*CloudDesk: Autonomous Customer Support & Resolution Platform*

**Phase 3: Identity and request guards.** Requirements N1 (JWT auth), N2 (rate limiting), N6 (audit), and the §18.1 rule that a viewer can never approve, reply or run a workflow.

Diagram key: solid = built in this phase. Dashed grey = planned for a later phase.

---

## Step 0: Starting point (end of Phase 2)

Open routes, one middleware, a database nobody guards.

```mermaid
flowchart LR
    C["Any caller"] --> CORS --> RID["RequestId<br/>middleware"] --> H["/health routes"]
    H -.-> DB[("SQLite<br/>16 tables")]
    classDef x fill:#fff
```

Only health routes existed, so nothing sensitive was exposed yet. But every route added in Phase 4 would have been public.

---

## Step 1 (P3-1): Identity: JWT and `require_role`

**File:** `backend/app/core/security.py`

A token is HS256-signed with `effective_jwt_secret` (Supabase secret if set, else `JWT_SECRET`). Claims: `sub, email, role, aud, iat, exp`. Verification checks signature, audience (`authenticated`, the Supabase value) and expiry.

```mermaid
flowchart TD
    R["Request + Authorization: Bearer ..."] --> G["get_current_user"]
    G -->|"no header"| E401a["401 Not authenticated"]
    G --> D["decode_token"]
    D -->|"bad signature / expired / wrong aud"| E401b["401 invalid or expired"]
    D --> U["AuthUser(id, email, role)"]
    U --> RR["require_role(minimum)"]
    RR -->|"level below minimum"| E403["403 Requires role X"]
    RR -->|"ok"| ROUTE["Route handler"]
```

Role ladder: `viewer 1 < agent 2 < admin 3`. Unknown or missing role claims degrade to `viewer` (least privilege), which also lets a plain Supabase token (`role: "authenticated"`) work safely.

Design choices:
- **Stateless**: no DB lookup per request; the token is the proof.
- **`require_role` is a dependency factory**, so the policy is visible at the route signature.
- Core never imports `agents/` (layering rule preserved).

---

## Step 2 (P3-2): Demo login

**Files:** `api/auth.py` → `services/auth_service.py` → `repositories/people.py` (`ProfileRepository`), `schemas/auth.py`

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as POST /api/v1/auth/demo-login
    participant S as auth_service
    participant R as ProfileRepository
    participant DB as profiles table
    B->>A: {email?} or {role?}
    A->>A: DEMO_MODE off? -> 404
    A->>S: demo_login
    S->>R: get_by_email / first_with_role
    R->>DB: SELECT
    DB-->>R: Profile
    S->>S: create_access_token (8h)
    S-->>B: {access_token, expires_in 28800, user}
    B->>A: GET /auth/me (Bearer)
    A-->>B: User
```

Resolution rule: email wins over role; neither → demo agent; unknown email → 404. Layers respected: the route handles HTTP, the service holds the logic, the repository holds the SQL.

---

## Step 3 (P3-3): Rate limit

**Files:** `middleware/rate_limit.py`, `core/redis.py`

Fixed window per client: key `rl:{client}:{minute}`, `INCR`, first hit sets `EXPIRE`. Client = first `X-Forwarded-For` hop (behind a load balancer) or the socket IP.

```mermaid
flowchart TD
    REQ["request"] --> EX{"path starts /health?"}
    EX -->|yes| PASS["pass through"]
    EX -->|no| INCR["Redis INCR rl:client:window"]
    INCR -->|"Redis error"| OPEN["log + fail open"] --> PASS
    INCR --> CMP{"count > limit?"}
    CMP -->|yes| T["429 + Retry-After + X-RateLimit-*"]
    CMP -->|no| PASS2["pass + X-RateLimit-Remaining"]
```

`get_redis()` returns **fakeredis** when `REDIS_URL` is empty (offline demo/tests) and a real `redis.asyncio` client otherwise. The limiter takes the client factory and clock as arguments, so tests are deterministic.

---

## Step 4 (P3-4): Audit and middleware order

**File:** `middleware/audit.py`; wiring in `main.py`.

For every non-`GET/HEAD/OPTIONS` request, after the route finishes, insert an `audit_logs` row: `actor_id, actor_email, method, path, status_code, request_id, detail{actor_role}`. The actor comes from the bearer token if it verifies, else null (a 401 attempt is still logged). No bodies, query strings or tokens are stored. A failed write is logged and swallowed.

---

## Step 5: End state of Phase 3

```mermaid
flowchart LR
    B["Browser"] --> CORS["CORS"]
    CORS --> RID["RequestId"]
    RID --> RL["RateLimit"]
    RL --> AU["Audit"]
    AU --> ROUTER{"Router"}
    ROUTER --> HL["/health*<br/>no auth"]
    ROUTER --> AUTH["/api/v1/auth/*"]
    ROUTER -.-> PROT["Phase 4+ routes<br/>require_role(...)"]:::future
    RL <--> RED[("Redis /<br/>fakeredis")]
    AU --> DB[("audit_logs")]
    AUTH --> DB2[("profiles")]
    classDef future stroke-dasharray: 5 5,fill:#eee,color:#666
```

**Order rationale** (request path CORS → RequestId → RateLimit → Audit → router):

| Position | Why |
|---|---|
| CORS outermost | Browser pre-flights are answered before anything else |
| RequestId before the rest | Every later layer, including 429s and audit rows, can use the id |
| RateLimit before Audit | A flood is stopped before it can flood the database with audit rows |
| Audit innermost | It sees the route's real final status code |

Note: a request rejected by the limiter (429) is *not* audited by design.

---

## What changed vs. Phase 2

| Area | Phase 2 | Phase 3 |
|---|---|---|
| Middleware | CORS, RequestId | + RateLimit, Audit |
| Routes | health | + `/api/v1/auth/demo-login`, `/auth/me` |
| Dependencies | none for auth | + `pyjwt`, `redis`, `fakeredis` |
| Tables written | seed only | + `audit_logs` on every change |
| Tests | 68 | 91 |

## Status (honest)

| Item | State |
|---|---|
| JWT, roles, demo login, limiter, audit | Implemented and validated locally (offline) |
| Real Redis server | Code path written; **not tested against a real Redis** |
| Supabase-issued tokens | Format handled in unit tests; **not tried with a real Supabase project** |
| Protecting real support routes | Phase 4 |
| Deployed | No |
