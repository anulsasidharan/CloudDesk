# Phase 14 Interview Q&A: Evaluation and Delivery

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code.

---

## A. Big picture

**Q1. What did you build in Phase 14?**
Two things: a quality gate and a delivery layer. The gate is five evaluation thresholds that fail the build when missed (`tests/evaluation/test_thresholds.py`). The delivery layer is Dockerfiles, a Compose stack, Terraform scaffolds for three clouds, CI workflows and deployment hygiene tests.

**Q2. Which requirements does it cover?**
Thresholds for F2 (classification), F5 (retrieval and citation), F8 (grounded reply) and F10 (escalation); F14 (offline run); N8 (deployable as containers to AWS, Azure, GCP).

**Q3. Which tasks were in the phase?**
P14-1 evaluation thresholds, P14-2 Dockerfiles, P14-3 Compose, P14-4 Terraform and CI scaffolds, P14-5 deployment hygiene tests.

**Q4. Did product behaviour change?**
No. No route, schema, agent, rule or UI changed. The phase wraps the system in measurement and packaging.

**Q5. Explain it to a non-technical person.**
A car leaving the factory: first the crash tests with pass marks, then the shipping container and the blueprints for the dealerships. The tests run with no paid AI service, and the packaging is checked automatically for safety.

**Q6. The plan calls this Phase 13. Why Phase 14 here?**
`TASKS.md` splits the console into two phases (12 and 13), which moves evaluation and delivery to 14. I followed `TASKS.md`.

---

## B. Evaluation

**Q7. What are the five metrics and their bars?**
Classification accuracy 0.80, retrieval hit-rate@3 0.75, escalation correctness 0.90, citation rate 0.90, grounding rate 0.90. They come from CLAUDE.md section 13.

**Q8. How is each one computed?**
Classification compares the category to `expected_category`. Retrieval checks whether an `expected_articles` title appears in the top 3 hits. Escalation needs both the flag and the team to match. Citation requires every plan to have citations that start with `kb://`. Grounding requires every troubleshooting step to appear in the customer reply.

**Q9. What is the dataset?**
`datasets/eval_cases.json`, 27 cases, all 13 demo tickets plus extras, each with expected category, escalation, team and articles.

**Q10. Why are citation and grounding scored on only the 13 demo tickets?**
They need the full pipeline (customer context, tools, database), and only the demo tickets exist in the seeded database. Classification, retrieval and escalation need no database, so they use every case.

**Q11. How does the evaluation run with no API key?**
Everything uses the `fake` LLM provider, the in-memory vector store and fakeredis (F14). It finishes in under a second.

**Q12. Is a fake-model score meaningful?**
It measures the **rules, retrieval and plumbing**, which is what protects policy behaviour. It does not measure a real model's quality. A real-model evaluation would be a separate, costed run. I say this plainly.

**Q13. How does a failure help the developer?**
The assertion message prints the rate and the **ids of the missed cases**, so a regression points at specific tickets.

**Q14. Could thresholds be lowered to make the build pass?**
A test checks the bars match CLAUDE.md (0.80, 0.75, 0.90). Changing them means changing the spec and the test together, which a reviewer sees.

**Q15. How did you reuse fixtures between folders?**
Pytest fixtures in `tests/agents/conftest.py` are not visible in `tests/evaluation`. `tests/evaluation/conftest.py` loads that file and re-exports `maker`, `registry`, `ticket` and `pipeline`, so evaluation scores the same pipeline the graph uses without duplicating the setup.

**Q16. Why rate-based thresholds and not "all must pass"?**
Language and retrieval have honest grey areas. A rate with a bar tolerates a few edge cases but fails on a broad regression. Policy cases are separately pinned by exact tests (the four policy tickets must escalate).

---

## C. Docker

**Q17. Why multi-stage builds?**
Build tools and caches stay in the first stage; the final image holds only what runs. Smaller image, smaller attack surface.

**Q18. Why run as non-root?**
If the app were compromised, the attacker would not be an administrator inside the container. A hygiene test requires a non-root `USER` in the final stage of both Dockerfiles.

**Q19. What do the HEALTHCHECKs call?**
Backend: `GET /health/live`. Frontend: `GET /api/health`. `/health/live` deliberately does no I/O, so a slow Redis cannot make the container look dead and trigger restarts.

**Q20. Why is the backend built from the repository root?**
It needs `backend/`, `agents/`, `rag/`, `memory/`, `integrations/` and `sample_data/`, which are siblings. The frontend builds from `frontend/` alone.

**Q21. Why does the server bind `0.0.0.0`?**
Inside a container `127.0.0.1` is reachable only from that container. Binding all interfaces lets the published port work.

**Q22. Why is `NEXT_PUBLIC_API_URL` a build argument?**
Next.js inlines `NEXT_PUBLIC_*` values into the browser bundle at build time. Changing the API address means rebuilding the frontend image per environment.

**Q23. What does `.dockerignore` protect?**
It keeps `.env`, `data/`, `*.db` and `node_modules` out of the build context, so secrets and local databases cannot be baked into image layers.

**Q24. Are base images pinned?**
By tag (`python:3.12-slim`, `node:22-alpine`), not by digest. Both files say to pin by digest before production. That is a known gap.

**Q25. Did you build and run the images?**
**No.** The Docker daemon was not running on my machine, so only `docker compose config -q` was validated. I will not claim the images build until I have run `docker compose up --build` and the smoke test.

---

## D. Compose and networking

**Q26. What services does the stack have?**
Frontend, backend, Redis and Qdrant, with three named volumes.

**Q27. How is start order controlled?**
`depends_on` with `condition: service_healthy`: backend waits for Redis and Qdrant, frontend waits for backend. A hygiene test asserts it and also that every service has a health check and `restart: unless-stopped`.

**Q28. How do containers find each other?**
Compose's network provides DNS by service name, so the backend uses `redis://redis:6379/0`.

**Q29. Why is the frontend's API URL `localhost:8000` and not `http://backend:8000`?**
The **browser** makes the API calls, and a browser is outside the Docker network, where `backend` does not resolve. It must be an address the browser can reach: the published host port. A test guards this.

**Q30. Which ports are exposed?**
Only 3000 and 8000. Redis and Qdrant stay on the internal network.

**Q31. Why is Qdrant in Compose if the app uses the in-memory store?**
The architecture calls for it and the service is provisioned, but `VECTOR_STORE` is `memory` and the Qdrant client is not a dependency yet. It is reserved, and I list it as a gap rather than a feature.

**Q32. Where does state live?**
In `backend-data` (`/srv/data`): SQLite and the checkpoint database, so a paused approval survives a restart.

**Q33. Can you scale the backend to many replicas?**
Not yet. The workflow runs as an in-process background task on SQLite and a file checkpointer. Scaling needs Postgres, a shared checkpointer and a worker. The Kubernetes manifest sets one replica for this reason.

**Q34. How are secrets passed in Compose?**
`${JWT_SECRET:-default}` style substitution from the shell. The default is dev-only. A test checks the file uses substitution for the JWT secret and LLM key.

---

## E. Terraform and CI

**Q35. What is in the Terraform roots?**
One root per cloud (`deployment/aws`, `azure`, `gcp`) with registry, secrets and logging resources, three environment var-files each, and outputs. Compute, load balancer, network and Redis are the next increment.

**Q36. Why var-files and not copied code per environment?**
Environments differ only in values (names, counts, regions). One code path means dev behaves like prod. Only `*.tfvars.example` is committed.

**Q37. How are secrets kept out of Terraform?**
They come through `TF_VAR_*` environment variables, and `.gitignore` excludes real `*.tfvars`, `backend.hcl`, state and plans.

**Q38. How does production get protected?**
`_deploy.yml` uses the GitHub Environment `prod-apply` with required reviewers, and `deploy.sh` refuses `--auto-approve` for staging and prod. A test checks both strings exist.

**Q39. Why tag images with the git SHA?**
So the artifact that was tested is exactly the artifact that ships, and every running version maps to a commit. ECR tags are set immutable.

**Q40. What do the five workflows do?**
`test.yml` runs ruff, pytest and the frontend lint, test and build. `security.yml` runs gitleaks and checkov. `docker-build.yml` validates Compose and builds both images. `terraform-validate.yml` validates each cloud root. `_deploy.yml` is the reusable plan, approve, apply and smoke pipeline.

**Q41. Have the workflows run?**
No. The repository has not been pushed with secrets and OIDC roles configured. I describe them as written, not as "passing in CI".

**Q42. Did you run `terraform validate`?**
No. Terraform is not installed on this machine. Local `make terraform-validate` and the CI job are the way to check it.

**Q43. How does AWS map to Azure and GCP?**
ECR, ECS Fargate, ALB, Secrets Manager and CloudWatch map to ACR, Container Apps, Key Vault and Log Analytics, and to Artifact Registry, Cloud Run, Secret Manager and Cloud Logging. The two images and health routes are identical on all three.

---

## F. Hygiene tests

**Q44. What do the deployment tests check?**
19 static tests: non-root user and HEALTHCHECK, multi-stage builds, health routes, standalone output, Compose services and start order, volumes, no inline secrets, `.env.example` coverage, no secret files tracked, no key-shaped strings, three env var-files per cloud, five workflows, the prod reviewer rule, and the deploy script's guard.

**Q45. How do you prove no `.env` is committed?**
The test runs `git ls-files` and matches against forbidden names (`.env`, `terraform.tfvars`, `backend.hcl`, `tfplan`, state files, `*.db`), with `.env.example` allowed.

**Q46. How do you prove `.env.example` is complete?**
The test reads the fields of the `Settings` model and fails if any name is missing from the file.

**Q47. Did the tests ever catch a real mistake?**
Yes. On the first run the frontend Compose service had no health check, so the test failed. I added it and re-ran to green.

**Q48. Are these tests proof of deployment?**
No. They prove the files are well formed and safe. They say nothing about a running cloud environment.

---

## G. Honest status and judgement

**Q49. What is verified and what is not?**
Verified locally: all 432 tests pass offline, and `docker compose config -q` passes. Not verified: image builds, `compose up`, the smoke test, `terraform validate`, workflows, any cloud deployment. No cloud credentials were used.

**Q50. What would you do next?**
Run the images and smoke test, fill the compute, load balancer, network and Redis resources, wire Qdrant, move to Postgres with a shared checkpointer and a worker, pin base images by digest, and add a real-model evaluation run.

**Q51. Biggest risk in this phase?**
Claiming more than is true. Compose validation and tests are not a deployment. I keep the status table current so the claim matches the evidence (CLAUDE.md section 15.1).

**Q52. How does this phase connect to earlier ones?**
It measures Phases 5, 8 and 10 (retrieval, specialists, escalation), packages Phases 1 to 13, and enforces Phase 3's secret and JWT rules at the file level.
