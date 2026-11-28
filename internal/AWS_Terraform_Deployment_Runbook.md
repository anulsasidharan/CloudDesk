# CloudDesk – AWS Deployment Runbook (Terraform)

**Target:** AWS (ECR → ECS Fargate → ALB, Secrets Manager, CloudWatch, ElastiCache Redis)
**IaC:** Terraform in `deployment/aws/`
**LLM:** OpenAI (`LLM_PROVIDER=openai`)
**Audience:** the engineer deploying CloudDesk (you)
**Status of this document:** written from reading the repo. Nothing here has been applied to a real AWS account. Commands marked *(unvalidated)* have not been run.

---

## 0. Read this first – what the repo can and cannot do today

Reading `deployment/aws/`, `pyproject.toml`, `uv.lock`, `rag/vector_store.py` and `backend/Dockerfile` shows the following. Each item changes the plan below, so none of them is optional reading.

| # | Finding | Evidence | Impact | Action |
|---|---|---|---|---|
| G1 | **The AWS Terraform is a scaffold.** It creates only 2 ECR repos, 1 empty Secrets Manager secret (JWT), 1 CloudWatch log group, 1 ECS cluster. No VPC, ALB, ECS task definitions/services, IAM roles, Redis, or HTTPS. | `deployment/aws/main.tf` (line 40: "next increment") | `terraform apply` as-is deploys **no running app**. | Phase 5 of this runbook lists the resources to add. |
| G2 | **No OpenAI client library is installed.** `langchain-openai` / `openai` are absent from `pyproject.toml` and `uv.lock`. `llm.py` calls `init_chat_model(model, model_provider="openai")`, which needs `langchain-openai`. | grep of `uv.lock` | With `LLM_PROVIDER=openai` the backend image fails at the first LLM call. | `uv add langchain-openai` and regenerate `uv.lock` before building the image (Phase 2). |
| G3 | **No Postgres driver.** `asyncpg` is absent; only `aiosqlite` is installed. | `pyproject.toml` | `DATABASE_URL=postgresql+asyncpg://…` will not connect. | `uv add asyncpg` (Phase 2), or deliberately stay on SQLite (see G5). |
| G4 | **Embeddings are offline-only.** `get_embeddings()` raises `ValueError` for any provider other than `fake`. | `rag/vector_store.py:55` | Your OpenAI key can be used for the **chat LLM only**. Do **not** set `EMBEDDING_PROVIDER=openai`. Retrieval quality stays at the hashed bag-of-words level. | Keep `EMBEDDING_PROVIDER=fake`. Real embeddings are a code change (out of scope here). |
| G5 | **Workflow state is local to one process.** Checkpoints use `AsyncSqliteSaver` on a file, workflows run in-process via `BackgroundTasks`, and the approval resume must hit the same task. Fargate task disk is ephemeral. | `CLAUDE.md` §4.1, §7.3, §10; `Dockerfile` | More than one backend task, or a task restart during `waiting_on_approval`, loses or mis-routes paused workflows. The prod example `backend_count = 3` is **unsafe** for v1. | Run **`backend_count = 1`**, mount EFS at `/srv/data` for checkpoints (Phase 5), or accept loss on restart in dev. A Postgres checkpointer is future work. |
| G6 | **`NEXT_PUBLIC_API_URL` is baked into the frontend image at build time.** | `frontend/Dockerfile`, `CLAUDE.md` §11 | You need the public URL **before** building the frontend image. | Decide the domain first (Phase 1), use path routing on one ALB (Phase 5), then build. |
| G7 | **`QdrantVectorStore` exists but `qdrant-client` is not in `uv.lock`.** | grep of `uv.lock` | `VECTOR_STORE=qdrant` will not work in the current image. | Use `VECTOR_STORE=memory` for v1 (works with one backend task). Add `qdrant-client` only if you move to Qdrant Cloud. |
| G8 | **Redis is mandatory when deployed.** With `REDIS_URL` empty the app uses fakeredis (per-process). | `CLAUDE.md` §10.1 | Rate-limit and short-term memory only work correctly with real Redis. | ElastiCache (Phase 5). |
| G9 | `.github/workflows/_deploy.yml` has `plan` and `apply` as separate jobs with no artifact hand-off (`tfplan` is not shared) and no build/push job. | `_deploy.yml` | Pipeline will not work as written. | Use the manual path in this runbook first; fix CI afterwards (Phase 10). |

**Recommended v1 shape (what this runbook builds):** 1 backend task + 1 frontend task on ECS Fargate behind one ALB, ElastiCache Redis, Supabase Postgres (or SQLite on EFS for a throwaway demo), in-memory vector store, fake embeddings, OpenAI chat model.

---

## 1. Credentials, API keys and accounts – get these first

### 1.1 Summary table

| # | What | Required? | Where to get it | Goes into | Cost |
|---|---|---|---|---|---|
| 1 | **OpenAI API key** (`LLM_API_KEY`) | **Yes** | https://platform.openai.com/api-keys → *Create new secret key* | AWS Secrets Manager → backend task env `LLM_API_KEY` | Pay-per-token; needs prepaid credit |
| 2 | **AWS account + deploy identity** | **Yes** | https://aws.amazon.com → create account; then IAM Identity Center user (preferred) or an IAM user | Your shell (`aws sso login`) and later GitHub OIDC role | Free tier + usage |
| 3 | **App JWT secret** (`JWT_SECRET`) | **Yes** | Generate yourself (no vendor) | Secrets Manager (`clouddesk-<env>/jwt-secret`) | Free |
| 4 | **Terraform state bucket** | **Yes** | You create it in S3 (Phase 3) | `backend.hcl` (git-ignored) | Cents |
| 5 | **Postgres `DATABASE_URL`** | Recommended | Supabase: https://supabase.com → New project → *Project Settings → Database → Connection string* (use the **pooler**, URI form) | Secrets Manager → `DATABASE_URL` | Free tier or paid |
| 6 | **Supabase JWT secret** (`SUPABASE_JWT_SECRET`) | Only if using Supabase Auth tokens | Supabase → *Project Settings → API → JWT Settings → JWT Secret* | Secrets Manager | Free |
| 7 | **Domain name + ACM certificate** | Strongly recommended (HTTPS) | Domain: Route 53 or any registrar. Cert: AWS Certificate Manager (free) | Terraform var `certificate_arn`, `domain_name` | ~$12/yr domain |
| 8 | **Qdrant Cloud URL + API key** (`QDRANT_URL`, `QDRANT_API_KEY`) | **No** for v1 (see G7) | https://cloud.qdrant.io → create cluster → *API Keys* | Secrets Manager | Free 1 GB cluster |
| 9 | **LangSmith API key** (`LANGCHAIN_API_KEY`) | Optional | https://smith.langchain.com → *Settings → API Keys* | Secrets Manager + `LANGCHAIN_TRACING_V2=true` | Free tier |
| 10 | **GitHub OIDC role** | Only for CI deploy | You create it in AWS IAM (Phase 10) – no key to download | GitHub repo variable `AWS_ROLE_ARN` | Free |
| 11 | **Alert email** | Optional | Your address | Terraform var for SNS subscription | Free |

You do **not** need: an Anthropic key, an OpenAI **embeddings** key (separate from item 1; unused per G4), a Stripe/SendGrid key (all integrations are mocks, `CLAUDE.md` §1), or Azure/GCP credentials.

### 1.2 OpenAI – detailed steps

1. Sign in at https://platform.openai.com. Create or select an **Organization** and a **Project** (name it `clouddesk-prod`; use a separate project per environment so keys and spend are isolated).
2. *Settings → Billing*: add a payment method and prepaid credit. Keys fail with `429 insufficient_quota` without credit.
3. *Dashboard → API keys → Create new secret key*. Choose **Project** key, owned by the `clouddesk-<env>` project. Copy it once; it starts with `sk-` and cannot be shown again.
4. *Project → Limits*: set a monthly budget and restrict allowed models to the one you choose.
5. Choose the model and set `LLM_MODEL` (required, the code raises `LLM_MODEL must be set for a real provider` if empty). Pick a current chat model from https://platform.openai.com/docs/models that supports **structured output / tool calling** (the app uses `call_structured`). A small, cheap model is the right start. Verify the exact model id on that page rather than trusting a name in this document.
6. Smoke-test the key from your laptop before putting it in AWS *(unvalidated)*:
   ```bash
   curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | head -c 300
   ```
7. Never paste the key into `.env.example`, a tfvars file, a ticket, or the chat. `guardrails.py` redacts `sk-…` patterns from memory notes, but the key still must not reach logs.

### 1.3 Generating the JWT secret

```bash
openssl rand -hex 32        # 64 hex chars; use this value for JWT_SECRET
```
The dev default `dev-only-secret-change-me-…` in `docker-compose.yml` must never reach AWS.

### 1.4 AWS access – detailed steps

1. Create/choose an AWS account. Enable MFA on the root user, then stop using root.
2. Enable **IAM Identity Center** (recommended) and create a user with a permission set for deployment (start with `PowerUserAccess` + `IAMFullAccess` in a **dev** account, then tighten to a least-privilege policy covering ECR, ECS, EC2/VPC, ELBv2, ElastiCache, Secrets Manager, CloudWatch, IAM role/pass-role, EFS, S3, ACM, Route 53, SNS).
3. Install and sign in:
   ```bash
   aws configure sso --profile clouddesk-dev
   aws sso login --profile clouddesk-dev
   aws sts get-caller-identity --profile clouddesk-dev     # confirms the account id
   export AWS_PROFILE=clouddesk-dev
   ```
4. Request quota/limits if the account is new (Fargate vCPU, Elastic IPs) via *Service Quotas*.
5. Use **separate AWS accounts** (or at minimum separate state keys and name prefixes) for dev, staging and prod. Never apply prod from a laptop profile that also has dev access.

### 1.5 Where each secret finally lives

| Secret | Store | Injected as |
|---|---|---|
| `LLM_API_KEY`, `JWT_SECRET`, `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `QDRANT_API_KEY`, `LANGCHAIN_API_KEY` | AWS Secrets Manager | ECS task-definition `secrets[].valueFrom` (never plain `environment`) |
| Non-secret config (`LLM_PROVIDER`, `LLM_MODEL`, `CORS_ORIGINS`, …) | Terraform → ECS `environment` | plain env vars |
| Terraform inputs that are secret | `TF_VAR_*` env vars at apply time | never in committed files (`CLAUDE.md` §15) |

---

## 2. Target architecture on AWS

```text
Internet ─HTTPS─▶ Route 53 ─▶ ALB (public subnets, ACM cert, :443)
                               ├─ /api/v1/*, /health* ─▶ ECS service "backend"  (private subnets, :8000)
                               └─ everything else     ─▶ ECS service "frontend" (private subnets, :3000)

backend ─▶ ElastiCache Redis (private)           REDIS_URL
        ─▶ Supabase Postgres (internet, TLS)     DATABASE_URL    (via NAT gateway)
        ─▶ OpenAI API (internet, TLS)            LLM_API_KEY     (via NAT gateway)
        ─▶ EFS mount /srv/data                   checkpoints.db  (v1, see G5)
ECR (backend, frontend images, tag = git SHA) · Secrets Manager · CloudWatch Logs /clouddesk/<env>
```

Resource map (existing in Terraform vs. to be added):

| Resource | In `main.tf` today? |
|---|---|
| `aws_ecr_repository` backend + frontend (immutable, scan on push) | Yes |
| `aws_secretsmanager_secret` jwt | Yes (secret container only, **no value**) |
| `aws_cloudwatch_log_group` `/clouddesk/<env>` (14 d dev, 90 d prod) | Yes |
| `aws_ecs_cluster` | Yes |
| VPC, subnets, NAT, route tables, security groups | **No** |
| ALB, target groups, listeners, ACM, Route 53 record | **No** |
| ECS task execution role + task role, task definitions, services | **No** |
| Secrets Manager secrets for LLM key / DB URL | **No** |
| ElastiCache Redis | **No** |
| EFS for checkpoints | **No** |
| CloudWatch alarms / SNS | **No** |

---

## 3. Prerequisites on your machine

| Tool | Version | Check |
|---|---|---|
| Terraform | >= 1.6 (as in `main.tf`) | `terraform version` |
| AWS CLI v2 | current | `aws --version` |
| Docker Desktop | current, running | `docker version` |
| uv | current | `uv --version` |
| Git, curl, openssl | any | |
| Git Bash (Windows) | for `deploy.sh` | scripts are bash |

Repo state before starting:
```bash
git switch development && git pull
git status                        # must be clean
make test                         # backend tests green, offline  (CLAUDE.md §14)
make lint
cd frontend && npm ci && npm run lint && npm run test -- --run && npm run build && cd ..
docker compose config -q          # compose file valid
```
**Gate:** do not continue if tests fail. The artifact that ships is the artifact that was tested (`CLAUDE.md` §15).

---

## 4. Runbook

Conventions: `ENV` is `dev`, `staging` or `prod`. Do **dev first, always**. Prod applies need a reviewed plan.

### Phase 1 – Decisions (30 min)

Fill this table in before touching AWS.

| Decision | Recommended v1 | Your choice |
|---|---|---|
| Region | `us-east-1` (matches tfvars examples) | |
| Environment to start | `dev` | |
| Public hostname | `clouddesk-dev.<yourdomain>` | |
| Database | Supabase Postgres (needs G3 fix) · or SQLite on EFS for throwaway demo | |
| Vector store | `memory` (G7) | |
| Redis | ElastiCache `cache.t4g.micro`, single node (dev) | |
| Backend task count | **1** (G5) | |
| `DEMO_MODE` | `true` for dev/staging (seeds 13 demo tickets and demo users). **`false` for anything customer-facing**, and then you must provide real users/tokens | |
| OpenAI model (`LLM_MODEL`) | cheap, structured-output-capable | |

The frontend URL must be known now (G6): `NEXT_PUBLIC_API_URL` = `https://clouddesk-dev.<yourdomain>` (same origin through the ALB, so `CORS_ORIGINS` is the same host).

### Phase 2 – Fix the application dependencies (G2, G3)

```bash
uv add langchain-openai          # G2: OpenAI chat support
uv add asyncpg                   # G3: only if using Postgres/Supabase
uv lock
make test                        # still green with LLM_PROVIDER=fake
```
Commit on a feature branch (`feat/aws-deploy-deps`) and open a PR against `development` per `CLAUDE.md` §14. Do not build images from uncommitted changes: the image tag is the git SHA.

Validate the Postgres URL form: `postgresql+asyncpg://USER:PASSWORD@HOST:5432/postgres`. For Supabase use the **pooler** host and URL-encode special characters in the password. Apply `database/schema.sql` (and `rls_policies.sql`) through the Supabase SQL editor, or rely on `create_tables()` at startup. Decide which, and do not do both blindly. Read `CLAUDE.md` §6 first.

### Phase 3 – Terraform remote state bootstrap (one-time per account)

`main.tf` declares `backend "s3" {}` and expects `-backend-config=backend.hcl`.

```bash
export AWS_PROFILE=clouddesk-dev
export REGION=us-east-1
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export STATE_BUCKET=clouddesk-tfstate-$ACCOUNT

aws s3api create-bucket --bucket $STATE_BUCKET --region $REGION   # us-east-1 needs no LocationConstraint
aws s3api put-bucket-versioning --bucket $STATE_BUCKET --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket $STATE_BUCKET \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket $STATE_BUCKET \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```
For regions other than `us-east-1`, add `--create-bucket-configuration LocationConstraint=$REGION`.

Create `deployment/aws/backend.hcl` (git-ignored, check with `git check-ignore deployment/aws/backend.hcl`):
```hcl
bucket       = "clouddesk-tfstate-<ACCOUNT_ID>"
key          = "clouddesk/dev/terraform.tfstate"    # one key per environment
region       = "us-east-1"
encrypt      = true
use_lockfile = true      # S3-native locking, Terraform >= 1.10. On 1.6-1.9 use dynamodb_table instead.
```
If you are on Terraform 1.6–1.9, create a DynamoDB table (`LockID` string hash key) and set `dynamodb_table = "clouddesk-tflock"` in place of `use_lockfile`.

### Phase 4 – Create the environment tfvars

```bash
cp deployment/aws/environments/dev/terraform.tfvars.example deployment/aws/environments/dev/terraform.tfvars
```
`terraform.tfvars` is git-ignored. Edit values (never put secrets here):
```hcl
environment   = "dev"
name_prefix   = "clouddesk-dev"
backend_count = 1                 # G5: keep at 1 for v1, including prod
region        = "us-east-1"
```
Variables currently declared: `environment`, `name_prefix`, `region`, `backend_count`, `image_tag`. You will add more in Phase 5.

### Phase 5 – Complete the Terraform (closes G1)

Edit `deployment/aws/`, preferably as shared modules under `deployment/modules/` (CLAUDE.md §15 calls for `networking, container-registry, secrets, compute, load-balancer, monitoring, redis`). Work through this checklist; each row is a PR-sized chunk. Keep `terraform validate` green after each.

| Step | Add | Key settings |
|---|---|---|
| 5.1 Networking | VPC `10.0.0.0/16`, 2 public + 2 private subnets in 2 AZs, IGW, **1 NAT gateway** (dev) / 1 per AZ (prod), route tables | NAT is needed so private tasks reach OpenAI and Supabase |
| 5.2 Security groups | `alb` (443/80 from internet), `backend` (8000 from `alb` only), `frontend` (3000 from `alb` only), `redis` (6379 from `backend` only), `efs` (2049 from `backend` only) | no `0.0.0.0/0` ingress except ALB |
| 5.3 Secrets | `aws_secretsmanager_secret` + `_version` for `llm-api-key`, `database-url`, (`supabase-jwt-secret`); extend existing `jwt` secret with a version | values from `TF_VAR_*`, **marked `sensitive = true`**. They end up in Terraform state, so the state bucket must stay private/encrypted. Alternative: create the secret shell in Terraform and set the value with `aws secretsmanager put-secret-value` so the value never enters state. **Prefer the alternative.** |
| 5.4 IAM | Execution role (`AmazonECSTaskExecutionRolePolicy` + `secretsmanager:GetSecretValue` on the specific secret ARNs + `kms:Decrypt` if CMK) and a minimal task role | no wildcard resources |
| 5.5 Redis | `aws_elasticache_subnet_group` + `aws_elasticache_replication_group` (or `cluster`), `cache.t4g.micro`, in private subnets, `at_rest_encryption_enabled`, `transit_encryption_enabled` | `REDIS_URL` = `rediss://<primary_endpoint>:6379/0` when in-transit encryption is on (note `rediss`) |
| 5.6 EFS (G5) | `aws_efs_file_system` (encrypted), mount targets in private subnets, access point with uid/gid `10001` (the `app` user in the Dockerfile) | mount at `/srv/data`; the SQLite checkpoint file lives there |
| 5.7 Load balancer | ALB, target group `backend` (health check `/health/live`, port 8000), target group `frontend` (health check `/api/health`, port 3000), HTTPS listener with ACM cert, HTTP→HTTPS redirect, listener rule: path `/api/v1/*` and `/health*` → backend, default → frontend | `target_type = "ip"` for Fargate |
| 5.8 Task definitions | `backend`: 0.5 vCPU / 1 GB to start, port 8000, env vars from §6, `secrets` block, log driver `awslogs` → `/clouddesk/<env>`, EFS volume. `frontend`: 0.25 vCPU / 0.5 GB, port 3000 | image = `${repo_url}:${var.image_tag}`; `image_tag` has default `unset`, add a validation so apply fails if it is still `unset` |
| 5.9 Services | `aws_ecs_service` ×2, Fargate, private subnets, `desired_count = var.backend_count` (backend) and 1–2 (frontend), `deployment_circuit_breaker { enable = true, rollback = true }`, `health_check_grace_period_seconds = 60` | `platform_version = "LATEST"`. Set `deployment_minimum_healthy_percent = 0` for the backend while it is a single task on EFS, otherwise two copies briefly share the SQLite file |
| 5.10 DNS | Route 53 alias record → ALB (if the zone is in Route 53) | |
| 5.11 Monitoring | CloudWatch alarms: ALB 5xx, target unhealthy hosts, ECS CPU/memory, Redis CPU; SNS topic + email subscription | |
| 5.12 Outputs | `alb_dns_name`, `app_url`, `backend_repository_url`, `frontend_repository_url`, secret ARNs, `cluster_name`, service names | existing outputs: the two ECR URLs |
| 5.13 Variables | add `domain_name`, `certificate_arn`, `llm_model`, `frontend_desired_count`, `alert_email`, `vpc_cidr` | |

Validate locally (no AWS needed):
```bash
terraform -chdir=deployment/aws init -backend=false
terraform -chdir=deployment/aws fmt -recursive -check
terraform -chdir=deployment/aws validate
make terraform-validate
```
Optional static scan (CI runs checkov in `security.yml`): `checkov -d deployment/aws`.

**Gate:** `validate` and `fmt -check` pass; PR reviewed and merged to `development`.

### Phase 6 – Bootstrap the registry and push images

Image tags are immutable git SHAs, so the ECR repos must exist before the push, and the tag must exist before the service starts. Break the chicken-and-egg by creating only the registry first.

```bash
cd deployment/aws
terraform init -backend-config=backend.hcl
terraform apply -var-file=environments/dev/terraform.tfvars \
  -target=aws_ecr_repository.backend -target=aws_ecr_repository.frontend
cd ../..
```
`-target` is acceptable here as a documented one-time bootstrap only. Do not use it for routine applies.

Build and push (context for the backend is the **repo root**, per the Dockerfile header):
```bash
export SHA=$(git rev-parse --short=12 HEAD)
export REGISTRY=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com
export APP_URL=https://clouddesk-dev.<yourdomain>

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $REGISTRY

docker build -f backend/Dockerfile -t $REGISTRY/clouddesk-dev-backend:$SHA .
docker build -f frontend/Dockerfile --build-arg NEXT_PUBLIC_API_URL=$APP_URL \
  -t $REGISTRY/clouddesk-dev-frontend:$SHA frontend

docker push $REGISTRY/clouddesk-dev-backend:$SHA
docker push $REGISTRY/clouddesk-dev-frontend:$SHA
```
Repo names are `${name_prefix}-backend` / `-frontend`, so they match `name_prefix` in your tfvars.

Check the scan result and that the tag exists:
```bash
aws ecr describe-image-scan-findings --repository-name clouddesk-dev-backend --image-id imageTag=$SHA \
  --query 'imageScanFindings.findingSeverityCounts'
```
Because the frontend image embeds the URL, **a different environment needs its own frontend build** (G6). Git SHA stays the same; the build arg differs. Note that in your tag convention.

Local pre-check of the exact image before pushing *(unvalidated)*:
```bash
docker run --rm -p 8000:8000 -e DEMO_MODE=true -e LLM_PROVIDER=fake \
  -e JWT_SECRET=$(openssl rand -hex 32) $REGISTRY/clouddesk-dev-backend:$SHA
curl -s localhost:8000/health/live
```

### Phase 7 – Create the secret values

Terraform created the secret shells (5.3). Put values in from the CLI, so they never touch Terraform state or git:

```bash
aws secretsmanager put-secret-value --secret-id clouddesk-dev/jwt-secret   --secret-string "$(openssl rand -hex 32)"
read -rs OPENAI_KEY; aws secretsmanager put-secret-value --secret-id clouddesk-dev/llm-api-key --secret-string "$OPENAI_KEY"; unset OPENAI_KEY
read -rs DBURL;      aws secretsmanager put-secret-value --secret-id clouddesk-dev/database-url --secret-string "$DBURL"; unset DBURL
```
(`read -rs` keeps the values out of shell history.) The `jwt` secret name `${name_prefix}/jwt-secret` comes from `main.tf`; the other secret names are whatever you choose in 5.3.

### Phase 8 – Plan and apply

```bash
cd deployment/aws
terraform plan  -var-file=environments/dev/terraform.tfvars -var image_tag=$SHA -out=tfplan
```
**Review the plan line by line** (a human gate, per `CLAUDE.md` §15 and the "never apply without a reviewed plan" rule). Check for: only expected resources, no `destroy`/`replace` of the cluster or ECR repos, no secret values in the output, correct var file for the environment (never apply the dev var-file to prod, or the reverse).

```bash
terraform apply tfplan
terraform output
```
Or use the repo script, which enforces the same flow (`--auto-approve` is refused for staging and prod):
```bash
bash deployment/scripts/deploy.sh aws dev
```
Caveat: `deploy.sh` plans **without** `-var image_tag=…`, so `image_tag` stays `unset`. Either export `TF_VAR_image_tag=$SHA` first (preferred) or edit the script. Do this before relying on it.

### Phase 9 – Verify

```bash
export BASE_URL=$(terraform -chdir=deployment/aws output -raw app_url)    # or https://clouddesk-dev.<yourdomain>
bash deployment/scripts/smoke_test.sh        # checks /health/live and /health  → both must be 200
curl -s $BASE_URL/health/ready | python -m json.tool     # db, redis, vector store, llm all "ok"
```

Interpretation of `/health/ready` for `llm`: with `LLM_PROVIDER=fake` it reports offline; with `openai` it reports configured. The probe does **not** open an LLM connection (`readiness.py` docstring), so a good readiness result does not prove the key works.

Functional check (needs `DEMO_MODE=true` or valid tokens):
1. Open `$BASE_URL`, log in as `sam.agent@clouddesk.demo` (see how demo login works in `docs/API_CONTRACT.md` `/auth`).
2. Open ticket **CD-1002** (refund) → **Run AI workflow**. Expect: runs, pauses at `waiting_on_approval`, **no refund executed** until you click Approve (F9).
3. Run **CD-1005** (security) → expect auto-escalation. Run **CD-1013** (prompt injection) → expect no export, text treated as data (N4).
4. Log in as `vic.viewer@clouddesk.demo` → action buttons disabled; direct API call to `/run` returns **403**.
5. **Real LLM proof:** open the ticket's events (`GET /api/v1/tickets/{id}/events`) and confirm `llm_called` events with non-zero token counts and cost (the fake provider reports 0.0).
6. Confirm logs: CloudWatch group `/clouddesk/dev` shows JSON lines with `request_id` and `workflow_id`.
7. Confirm response header `X-Request-ID` is present (N3).

Exit criteria for dev: all above pass, ALB targets healthy, no secrets visible in task definition JSON or logs.

### Phase 10 – CI/CD (after manual deploy works)

`_deploy.yml` needs repair (G9) before use. Minimum fixes: add a `build-and-push` job (ECR login via OIDC), pass `image_tag=${{ github.sha }}` to `apply`, and upload/download `tfplan` as an artifact so apply runs the **reviewed** plan. Also create `backend.hcl` in CI from a variable, since it is git-ignored.

OIDC role (no long-lived keys):
1. IAM → *Identity providers* → add `token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.
2. Create a role trusted by that provider with a condition `token.actions.githubusercontent.com:sub` = `repo:anulsasidharan/CloudDesk:environment:prod-apply` (and one per env). Scope it to least privilege.
3. GitHub repo → *Settings → Environments*: create `dev`, `staging`, `prod-apply`; add **required reviewers** to `prod-apply`; add variables `AWS_ROLE_ARN`, `BASE_URL`.
4. Branch flow stays `feature → development → testing → main` (`CLAUDE.md` §14).

Do not claim "passes in CI" until a workflow has actually run (`CLAUDE.md` §15.1).

### Phase 11 – Promote to staging and prod

Repeat Phases 3–9 with: a separate state key (`clouddesk/staging/terraform.tfstate`), its own tfvars, its own OpenAI project key, its own secrets, its own frontend image build (G6). For prod additionally:
- `DEMO_MODE=false`. Plan real user provisioning first. Demo credentials must not exist in prod.
- Use a different `JWT_SECRET`. Rotate if it was ever shared.
- Keep `backend_count = 1` (G5) regardless of the example's `3`.
- Multi-AZ NAT, Redis with replica, log retention 90 days (already in `main.tf`).
- Required-reviewer approval before apply; read the plan.
- Pin base images by digest (Dockerfile header notes this).

---

## 5. Application environment variables on ECS

Backend task:

| Variable | Value for AWS | Source |
|---|---|---|
| `DEMO_MODE` | `true` (dev/staging) · `false` (prod) | plain |
| `ENVIRONMENT` | `dev` / `staging` / `production`. Check the accepted values in `backend/app/core/config.py` before setting | plain |
| `CORS_ORIGINS` | `https://clouddesk-dev.<yourdomain>` | plain |
| `JWT_SECRET` | from Secrets Manager | **secret** |
| `SUPABASE_JWT_SECRET` | only if using Supabase tokens (it overrides `JWT_SECRET` when set) | **secret** |
| `DATABASE_URL` | `postgresql+asyncpg://…` (Supabase) or leave the Dockerfile default SQLite path on EFS | **secret** |
| `CHECKPOINT_DB_PATH` | `/srv/data/checkpoints.db` (on the EFS mount) | plain |
| `REDIS_URL` | `rediss://<elasticache-endpoint>:6379/0` | plain |
| `USE_FAKE_REDIS` | `false` | plain |
| `LLM_PROVIDER` | `openai` | plain |
| `LLM_API_KEY` | OpenAI key | **secret** |
| `LLM_MODEL` | e.g. a chat model id you verified in §1.2 | plain |
| `EMBEDDING_PROVIDER` | `fake` (G4) | plain |
| `EMBEDDING_DIMENSIONS` | `384` | plain |
| `VECTOR_STORE` | `memory` (G7) | plain |
| `APPROVAL_REQUIRED_FOR_REFUNDS` | `true` | plain |
| `MAX_REFUND_WITHOUT_APPROVAL` | `0` | plain |
| `TOOL_TIMEOUT_SECONDS` | e.g. `30` | plain |
| `RATE_LIMIT_PER_MINUTE` | e.g. `120` dev, lower in prod | plain |
| `SAMPLE_DATA_DIR` | image default (`/srv/sample_data`), verify in config | plain |
| `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT` | optional; key is a **secret** | |

Frontend task: no runtime secrets. `NEXT_PUBLIC_API_URL` is a **build arg** (Phase 6). Frontend must never receive a service-role key (`CLAUDE.md` §4.2).

`get_settings()` is `lru_cache`d, so a changed env var requires a **new task deployment** (force a new deployment).

---

## 6. Operations

### 6.1 Deploy a new version
```bash
SHA=$(git rev-parse --short=12 HEAD)        # on a commit that passed tests
# build + push both images (Phase 6), then:
terraform -chdir=deployment/aws plan  -var-file=environments/<env>/terraform.tfvars -var image_tag=$SHA -out=tfplan
terraform -chdir=deployment/aws apply tfplan
bash deployment/scripts/smoke_test.sh
```
Circuit breaker (5.9) rolls back automatically if the new tasks fail health checks.

### 6.2 Rollback
Re-plan with the **previous known-good** SHA (images are immutable, so it still exists in ECR):
```bash
terraform -chdir=deployment/aws plan -var-file=environments/<env>/terraform.tfvars -var image_tag=<previous_sha> -out=tfplan
terraform -chdir=deployment/aws apply tfplan
```
`deployment/scripts/rollback.sh` and `build_and_push.sh` are referenced in `CLAUDE.md` §15 but **do not exist** (only `deploy.sh` and `smoke_test.sh` do). Use the commands above or write them.

### 6.3 Logs
```bash
aws logs tail /clouddesk/dev --follow --since 15m
aws logs filter-log-events --log-group-name /clouddesk/dev --filter-pattern '{ $.workflow_id = "<id>" }'
```

### 6.4 Rotate the OpenAI key
1. Create a new key in the same OpenAI project. 2. `aws secretsmanager put-secret-value …` 3. `aws ecs update-service --cluster clouddesk-dev-cluster --service <backend-service> --force-new-deployment` 4. Verify an `llm_called` event succeeds. 5. Delete the old key in OpenAI.

### 6.5 Cost (rough, verify with the AWS Pricing Calculator)
Always-on items dominate: NAT gateway (~$32/month + data), ALB (~$16+), ElastiCache `t4g.micro` (~$12), Fargate (1×0.5 vCPU/1 GB + 1×0.25 vCPU/0.5 GB, roughly $25–30), CloudWatch, EFS (small). Order of magnitude **$90–120/month for dev** before OpenAI usage. OpenAI cost is per token; set the project budget limit (§1.2). Run `terraform destroy` for dev when idle.

### 6.6 Teardown
```bash
terraform -chdir=deployment/aws plan -destroy -var-file=environments/dev/terraform.tfvars -out=tfdestroy
# review, then:
terraform -chdir=deployment/aws apply tfdestroy
```
ECR repos with images and non-empty buckets may block destroy; empty them deliberately after checking what is in them. Secrets Manager secrets have a recovery window (default 30 days) and will block re-creation of the same name; use `aws secretsmanager delete-secret --force-delete-without-recovery` only on dev, after confirming the target.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend task stops immediately, log: `No module named 'langchain_openai'` | G2 not done | Phase 2, rebuild with a new SHA |
| `LLMError: LLM_MODEL must be set for a real provider` | `LLM_MODEL` empty | set it, force new deployment |
| `401 invalid_api_key` / `429 insufficient_quota` from OpenAI | wrong key or no credit | check key in the right OpenAI project, billing page |
| `ModuleNotFoundError: asyncpg` / DB connect error | G3, or password not URL-encoded, or using direct instead of pooler host | fix URL; Supabase pooler |
| Tasks `RESOURCE_INITIALIZATION_ERROR` / cannot pull secret | execution role missing `GetSecretValue` on that ARN | 5.4 |
| Tasks cannot pull image | NAT/VPC endpoint missing, or tag does not exist (`unset`) | 5.1; verify `image_tag` and `aws ecr describe-images` |
| ALB 502/503, targets unhealthy | wrong health-check path/port, SG blocks ALB→task, start-up slower than grace period | use `/health/live` (backend) and `/api/health` (frontend); increase grace period |
| Browser shows CORS or network error | `NEXT_PUBLIC_API_URL` baked with the wrong host, or `CORS_ORIGINS` mismatch | rebuild frontend with the right URL (G6) |
| Workflow paused, then approval returns 409 or the workflow vanished | task restarted or a second task handled the request (G5) | keep 1 backend task; EFS for checkpoints |
| Redis connection errors | `redis://` used while in-transit encryption is on | use `rediss://` |
| `terraform apply` fails: `ECR immutable tag` | re-pushing an existing SHA | commit a change; never reuse a tag |
| State lock error | previous run aborted | `terraform force-unlock <id>` only after confirming no one is running apply |

---

## 8. Honest status checklist (`CLAUDE.md` §15.1)

Update this table as you progress. Do not write "deployed" until the last two columns are true.

| Item | Implemented | Validated locally | Needs cloud creds | Actually deployed |
|---|---|---|---|---|
| ECR, secret shell, log group, ECS cluster (existing `main.tf`) | yes | no (`validate` not recorded) | yes | no |
| VPC / ALB / ECS services / Redis / EFS / IAM / alarms | **no** (Phase 5) | – | yes | no |
| OpenAI dependency in the image (G2) | **no** | – | no | no |
| Postgres driver (G3) | **no** | – | no | no |
| Real embeddings (G4) | **no, not planned for v1** | – | – | – |
| Multi-task safe workflow state (G5) | **no** | – | – | – |
| CI deploy pipeline (G9) | partial, broken as written | no | yes | no |
| `rollback.sh`, `build_and_push.sh` | **no** | – | – | – |

---

## 9. Quick-start order (cheat sheet)

1. Get the OpenAI key, AWS access, domain/cert, (Supabase) – §1
2. `uv add langchain-openai asyncpg`, tests green, PR merged – Phase 2
3. Create state bucket + `backend.hcl` – Phase 3
4. Create tfvars – Phase 4
5. Finish Terraform (VPC, ALB, ECS, Redis, EFS, IAM, secrets, alarms) – Phase 5
6. `terraform apply -target` the two ECR repos, build and push images – Phase 6
7. `put-secret-value` for JWT, OpenAI key, DB URL – Phase 7
8. `plan` → review → `apply` – Phase 8
9. Smoke test + CD-1002 / CD-1005 / CD-1013 / viewer-403 checks – Phase 9
10. CI/OIDC, then staging, then prod – Phases 10–11
