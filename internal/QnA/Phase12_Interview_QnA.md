# Phase 12 Interview Q&A: Console Shell

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code.

---

## A. Big picture

**Q1. What did you build in Phase 12?**
The first screen for the product: a Next.js 15 console in `frontend/`. An app shell with one navigation list, a typed API client (`lib/api.ts`), a login page with a role-aware layout (`AuthProvider`, `Shell`), and read-only pages for tickets, customers and knowledge, plus dashboard, escalations, agents, audit and settings pages.

**Q2. Which requirements does it cover?**
It lays the base for F12 (everything from one screen) and the UI rules in CLAUDE.md section 11. The ticket action screen itself is Phase 13. It also supports F13 and N3 indirectly: requests carry a bearer token and the `X-Request-ID` comes back.

**Q3. Which tasks were in the phase?**
P12-1 app shell and navigation, P12-2 typed API client, P12-3 login and role-aware layout, P12-4 read-only list pages.

**Q4. How does `PLAN_PHASE.md` Phase 12 relate to `TASKS.md`?**
`TASKS.md` splits the plan's "Agent console" into Phase 12 (shell) and Phase 13 (ticket workflow screen). I finished the shell. Approve, reject, reply and the twelve-step panel are Phase 13.

**Q5. What is the demo checkpoint?**
Sign in as the viewer, search `CD-1002`, open it, then open the customer page and see the same ticket state. Sign in as admin and see Settings appear. I have **not** done that click-through in a live browser; the automated checks pass.

**Q6. Explain it to a non-technical person.**
Until now the system had no front desk. Phase 12 adds the entrance with a badge check, signs to each department, and boards that list tickets and customers. You can look but, for now, not act.

---

## B. Frontend architecture

**Q7. Why Next.js?**
The project specifies Next.js 15 App Router with TypeScript. It gives file-based routing, route groups and a standalone build output for a small container image.

**Q8. Why a `(dashboard)` route group?**
It lets every console page share one layout (auth guard plus sidebar) without adding a URL segment. `/login` sits outside it, so it has no sidebar and no guard.

**Q9. Why is navigation declared once in `nav.ts`?**
So the sidebar and the tests read the same list. A test asserts Settings is the only admin-only link. Adding a page means one file and one line.

**Q10. Why no UI library and no gradients?**
CLAUDE.md section 11 forbids both. A small hand-written kit (`components/ui/`) keeps the bundle small (about 103 kB shared) and means the team understands every piece of chrome.

**Q11. What is `DataState`?**
One component that turns loading, error, "route not built" and success into UI. Every page uses it, so failures look the same everywhere.

**Q12. Why custom hooks instead of a data library?**
The needs are small: `useAsync` (load and reload), `usePolling` (for Phase 13's 2-second poll), `useDebounced` (search boxes). That avoids another dependency. A data library would be reasonable later.

**Q13. Why are the pages client components?**
They need the token from `localStorage`, which only exists in the browser, and they react to filters. So data loads in the browser after the page arrives. The trade-off: no server-rendered data, which is fine for an internal tool behind login.

---

## C. The API client

**Q14. Why one API file?**
CLAUDE.md says the backend is reached only through `lib/api.ts`. Token handling, the 401 redirect, retry and error shaping are written once. Pages call `api.tickets(...)`, never `fetch`.

**Q15. What happens on a 401?**
The client clears the token and navigates to `/login?reason=expired`, and the login page shows "Your session expired". A test covers it. Login itself is called with `auth: false`, so a wrong credential does not redirect in a loop.

**Q16. What happens when the API is down?**
For a GET the client retries twice with a growing delay, then throws `NetworkError`. `DataState` shows a red banner with a Retry button. A test checks the three attempts.

**Q17. Why only retry GETs?**
A retried POST could act twice (send two replies, create two tickets). A test confirms a failed POST is attempted once.

**Q18. How do you tell "record not found" from "route not built"?**
FastAPI's missing-route 404 has `detail: "Not Found"`; the app's own 404s have messages like "Ticket not found". `isNotBuilt()` checks for the first, and the page shows "Not available yet".

**Q19. How do types stay in step with the backend?**
`lib/types.ts` mirrors `docs/API_CONTRACT.md` and the Pydantic schemas by hand. The project rule is to change contract, schema and types together. Nothing generates them, so drift is possible; generating types from the OpenAPI schema would be a worthwhile improvement.

**Q20. Why is the token in `localStorage`?**
The project convention says so. The risk is that any script injected into the page could read it. For a demo JWT in an internal tool it is acceptable; for production an HttpOnly cookie would be safer. I would flag this as a known trade-off.

---

## D. Roles and security

**Q21. Does hiding the Settings link secure it?**
No. Hiding is usability. The security is the backend's `require_role`, which checks the token on every request. A viewer who types `/settings` would still be refused (the page also shows "Admins only" without calling the API).

**Q22. How does the UI know the role?**
After login, `AuthProvider` calls `GET /auth/me` and keeps the `User` in context. `useAuth()` exposes it; `hasRole` and `canAct` use the same ordering as the backend (viewer 1, agent 2, admin 3).

**Q23. What does `canAct` do today?**
It tells the UI whether to enable action buttons. It is tested now. The buttons it gates (Run, Approve, Reject, Reply) are built in Phase 13.

**Q24. Is the service-role key in the frontend?**
No, and it must never be. The only secret the browser handles is the demo JWT. `NEXT_PUBLIC_*` values are public by design.

**Q25. What about XSS?**
React escapes text by default and I do not use `dangerouslySetInnerHTML`. Ticket bodies are rendered as plain text with `whitespace-pre-wrap`, so a malicious ticket such as CD-1013 cannot inject markup into an agent's screen.

**Q26. Is the demo login a vulnerability?**
It only exists when `DEMO_MODE=true` (the endpoint returns 404 otherwise) and has no password by design. It must not be enabled in production.

---

## E. Pages and behaviour

**Q27. How does ticket search work?**
The input is debounced 300 ms (so typing does not fire a request per key), then `GET /tickets?search=` matches subject, body or ticket number. Changing any filter resets to page 1.

**Q28. Why do the ticket list and customer page agree on status?**
Both read the same `tickets` rows through the backend; there is no separate frontend copy of state.

**Q29. Five pages say "Not available yet". Is that unfinished work?**
The screens are built against the contract, but the routes that feed them (`/dashboard/summary`, `/escalations`, `/agents`, `/audit`, `/settings`) do not exist in the backend yet. I chose a clear message over fake data or a crash, and I record it in `MEMORY.md`. When the routes land, the pages should work without frontend changes, but that is untested.

**Q30. Why is the ticket detail page read-only?**
Phase 13 owns the three-column workflow screen. A read-only page gives the list a place to link to and lets me verify the contract shape.

**Q31. How are statuses shown?**
`StatusPill` maps known values (new, escalated, critical...) to flat colours and falls back to neutral for unknown values, so a new status never breaks the page.

---

## F. Testing and quality

**Q32. What tests exist?**
15 vitest tests. `StatusPill` (humanizing, null, colour), `EmptyState`, role helpers and the admin-only nav rule, and the API client: bearer header, 401 redirect, no redirect on login, GET retry then success, give-up after retries, no POST retry, and not-built detection.

**Q33. What was not tested?**
There are no component tests for the pages, and no live browser run against the real backend. I tried a local backend smoke test but dropped it, so CORS and real payload shapes were checked by reading the code, not by running them.

**Q34. What other checks passed?**
`tsc --noEmit`, `next lint` and `next build` (13 routes) all pass.

**Q35. The spec lists a `WorkflowSteps.deriveSteps` test. Where is it?**
That component belongs to the Phase 13 ticket screen, so its test lands there. Likewise the "Approve and Reject only when pending" test.

---

## G. Infrastructure and delivery

**Q36. How do the console and API connect?**
The browser loads pages from Next.js on :3000, then the page's JavaScript calls FastAPI on :8000 directly. Different origins, so the API's CORS middleware allows `http://localhost:3000`.

**Q37. What is `NEXT_PUBLIC_API_URL` and why does it matter?**
The API address, copied into the bundle at build time. Changing it at run time does nothing, so the image is rebuilt per environment. In Docker it must be an address the **browser** can reach, not the internal service name.

**Q38. What is `/api/health` on the console?**
A route handler returning `{status: "ok"}`. It is the planned container health check. It does not call the backend, so it proves only that Next.js is up.

**Q39. Is there a Dockerfile yet?**
No. Phase 14 adds it (`node:22-alpine`, standalone output, non-root, HEALTHCHECK). `output: "standalone"` is already set to prepare for it.

**Q40. What would break first in a real deployment?**
CORS: if the deployed console origin is not in `CORS_ORIGINS`, every call fails in the browser as a "network error". Second: a wrong baked-in API URL.

---

## H. Honest status and trade-offs

**Q41. What is done, and what is not?**
Done and validated locally: shell, client, login, role-aware menu, list pages, 15 tests, build. Not done: live browser check, five backend routes, the ticket workflow screen, `frontend/.env.example` (my tool was blocked from creating it), Docker, cloud.

**Q42. What would you improve next?**
Generate TypeScript types from the OpenAPI schema; move the token to an HttpOnly cookie; add page-level tests with a mocked API; add the missing backend routes.

**Q43. What was the hardest design call?**
How to treat pages whose backend routes do not exist. Options were mock data, hiding the pages, or an explicit "Not available yet" state. I picked the last: it is honest, needs no throwaway code, and shows exactly what is missing.

**Q44. How does Phase 12 prepare Phase 13?**
Phase 13 needs login, roles, the client, `usePolling` for the 2-second workflow poll, `canAct` for disabled buttons and the UI kit. All exist and are tested, so Phase 13 can focus on the ticket screen.
