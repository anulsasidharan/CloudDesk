# Phase 3 Interview Q&A: Identity and Request Guards

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code so you can back it up.

---

## A. Big picture

**Q1. What did you build in Phase 3?**
The security layer: signed JWT tokens, three roles (viewer, agent, admin) enforced per route, a Redis rate limiter, and an audit log of every state-changing request, plus a demo login so the three demo users can sign in. They run in a fixed order: CORS → RequestId → RateLimit → Audit → router.

**Q2. Why build security before the ticket API?**
So every route is born protected. If we added tickets first, there would be a window where real data sat on open routes, and retrofitting auth tends to miss endpoints. In Phase 4 a route just declares `Depends(require_role("agent"))`.

**Q3. Which requirements does it cover?**
N1 (JWT auth), N2 (rate limiting), N6 (audit log), and the "never allow" rule that a viewer cannot approve, reply or run a workflow.

---

## B. Authentication (JWT)

**Q4. What is a JWT, in simple terms?**
A small signed note containing claims: who you are, your role, when it expires. The server signs it with a secret. Anyone can read it but nobody can alter it without the signature breaking.

**Q5. Why JWT rather than server-side sessions?**
It is stateless: no database hit on each request, and it scales across containers without shared session storage. It is also compatible with Supabase, which issues JWTs. The trade-off is that you cannot revoke a token before it expires, so we keep demo tokens to 8 hours.

**Q6. What do you check when a token arrives?**
Signature (HS256), expiry, audience (`authenticated`), and that `exp` and `sub` exist. Any failure becomes a 401 with `WWW-Authenticate: Bearer`. We pin the algorithm list to HS256 so a forged `alg: none` token is rejected.

**Q7. 401 vs 403?**
401 means "we don't know who you are" (no or bad token). 403 means "we know you, but you're not allowed". Tests cover both.

**Q8. Where does the signing secret come from? What if it's missing?**
The `JWT_SECRET` env var, or `SUPABASE_JWT_SECRET` which takes priority. If neither is set the system fails closed: login returns 503 and token checks return 401. It never falls back to a default secret.

**Q9. Can the secret leak?**
Settings hide secrets in `repr` and redact them in dumps; the token only contains `sub, email, role, aud, iat, exp`; and a test asserts the login response doesn't contain the secret. Secrets live in `.env` (git-ignored) or a cloud secret store.

**Q10. How does this work with Supabase?**
Supabase tokens use the same HS256 secret and the `authenticated` audience. Its `role` claim is just `"authenticated"`, so we read our role from `app_metadata.role`, and if that is missing the caller becomes a viewer. A unit test covers both cases. I have not tested against a live Supabase project.

---

## C. Authorization (roles)

**Q11. How do roles work?**
A ladder: viewer 1 < agent 2 < admin 3. `require_role("agent")` is a dependency factory; it allows anyone at level 2 or above and returns 403 otherwise.

**Q12. Why a ladder instead of separate permission lists?**
Three roles map cleanly onto how a support team works, and a number comparison is easy to reason about and test. If we needed fine-grained permissions we would move to explicit scopes.

**Q13. What happens with an unknown role in a token?**
It becomes `viewer`, the least privileged. Fail towards less access. Also the issuer refuses to sign a token with an invalid role.

**Q14. How is "a viewer can never approve a refund" guaranteed?**
Approve, reply and run routes will use `require_role("agent")`, and a test proves a viewer gets 403. The refund itself has a second guard in Phase 6 and 10 (tool policy plus a recorded approval), so it is defence in depth.

**Q15. Why are roles in the token and not looked up each time?**
Speed and simplicity. The downside is a role change only takes effect when the token is re-issued. For an 8-hour demo token that is acceptable; production could shorten the lifetime.

---

## D. Demo login

**Q16. Isn't login without a password insecure?**
Yes, which is why it exists only when `DEMO_MODE=true`; otherwise the route returns 404 as if it did not exist. It signs in the three seeded demo users. Real deployments use a proper identity provider.

**Q17. How does the login choose the user?**
Email wins; else the first profile with the given role; else the demo agent. Unknown email gives 404.

**Q18. How is the code layered?**
The route (`api/auth.py`) handles HTTP only, `auth_service` holds the logic, and `ProfileRepository` holds the SQL. This follows our rule that APIs contain no business rules and only repositories touch the database.

---

## E. Rate limiting

**Q19. Explain your rate limiter.**
Fixed window: for each client and each minute, one Redis counter. We `INCR` it; on the first hit we set an expiry so it cleans itself. Over the limit returns 429 with `Retry-After` and `X-RateLimit-*` headers.

**Q20. Why Redis rather than a Python dictionary?**
A dictionary is per-process. With several backend containers each would count separately, multiplying the real limit. Redis is shared and has built-in expiry. Offline we use fakeredis with the same code.

**Q21. Downsides of a fixed window?**
A burst at the end of one window plus the start of the next can briefly allow up to twice the limit. A sliding window or token bucket is smoother but more complex. For a support console it is acceptable.

**Q22. What if Redis goes down?**
We fail open: log the error and allow the request. Availability of the console matters more than perfect throttling. A security-critical limiter (like login brute-force) might choose to fail closed instead.

**Q23. Why are health checks exempt?**
Load balancers and orchestrators probe them constantly. If they were throttled or needed a token, a healthy service could be marked dead and restarted.

**Q24. How do you identify a client?**
First hop in `X-Forwarded-For`, else the socket IP. Known gap: if the backend is directly reachable, the header can be forged. In deployment the backend must accept traffic only from the load balancer.

**Q25. How did you test it without real Redis or waiting a minute?**
The middleware takes the Redis client and a clock as parameters. Tests pass fakeredis and a fake clock, then "advance" 60 seconds to show the counter reset.

---

## F. Audit logging

**Q26. What does the audit log record?**
For every non-GET request: actor id and email (if the token is valid), role, method, path, status code and request id. Never request bodies, query strings or tokens.

**Q27. Why not audit GET requests?**
They do not change state, and logging them would create huge volume. The requirement is an audit of state-changing actions. (A "who viewed what" log would be a separate privacy-driven feature.)

**Q28. Why does the audit run after the response, and what if it fails?**
It needs the final status code, so it records once the route finishes. If the write fails we log the error and carry on; an audit outage should not break a successful customer action. The trade-off is that in that case a change could go unrecorded, which is why the failure is logged loudly.

**Q29. Are failed attempts audited?**
Yes: a request with no token that gets 401 is recorded with an empty actor. Those are the most interesting rows for spotting abuse.

---

## G. Middleware design

**Q30. What is the order and why?**
CORS → RequestId → RateLimit → Audit → router.
- CORS outermost, so browser pre-flight checks are answered first.
- RequestId early, so everything after (including 429s and audit rows) carries the id.
- RateLimit before Audit, so a flood is stopped before it can flood the audit table.
- Audit innermost, so it sees the real route status.

**Q31. Why "pure ASGI" middleware rather than Starlette's `BaseHTTPMiddleware`?**
It keeps the request id on the same async task as the route (so log context works) and avoids known quirks of `BaseHTTPMiddleware` with background tasks and context variables.

**Q32. How do you prove the order in a test?**
The test reads the app's middleware list, which Starlette keeps outermost-first, and asserts the four names in order.

---

## H. Testing

**Q33. How many tests, and what do they prove?**
23 new tests, 91 total, all offline. Missing, malformed, expired, wrong-key and wrong-audience tokens are rejected; viewer gets 403 and agent/admin are accepted; non-GET writes an audit row and GET doesn't; the limiter blocks, resets and isolates clients; Redis failure fails open; login never returns the secret; demo login is hidden when demo mode is off.

**Q34. How do tests get tokens?**
Shared fixtures `agent_headers`, `admin_headers`, `viewer_headers` call demo login once per session. Later phases reuse them.

**Q35. Why set a very high rate limit in the test environment?**
So unrelated tests are not throttled by the shared client IP. Rate-limit tests build their own small app with a tiny limit.

---

## I. Trade-offs, risks, next steps

**Q36. What are the weaknesses of this phase?**
- Tokens cannot be revoked before expiry.
- Real Redis path is untested.
- `X-Forwarded-For` trust needs network-level protection.
- Rate limiting is per IP, so many users behind one office NAT share a budget.
- Demo login is deliberately not real authentication.

**Q37. What would you change for production?**
Use a real identity provider, shorter token lifetimes with refresh, per-user as well as per-IP limits, trusted-proxy configuration, and ship audit logs to a write-once store.

**Q38. Any surprises while building?**
Ruff flagged FastAPI's `Depends(...)` default arguments as a lint error. That is the framework's normal idiom, so I configured the linter to allow it, rather than rewriting every route. I also had to add three dependencies (`pyjwt`, `redis`, `fakeredis`) that the spec named but the project did not yet have.

**Q39. How does this set up Phase 4?**
Every ticket and customer route will declare its minimum role in one line, get rate limiting and auditing automatically from the middleware, and the shared test fixtures already exist.

**Q40. Give me a 30-second summary.**
"Phase 3 is the front door's security. Users receive an 8-hour signed token. Each route declares a minimum role, so a read-only viewer can never approve a refund. A Redis limiter stops flooding and fails open if Redis is down, and an audit log records every change. The guards run in a deliberate order, and 23 new tests prove them, including the failure cases."
