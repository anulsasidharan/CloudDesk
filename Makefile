# Windows: run from Git Bash / WSL, or call the commands directly (see CLAUDE.md section 14).
# Uses uv; PYTHONPATH must include backend.

.PHONY: setup seed ingest backend demo test lint

setup:
	uv sync
	@test -f .env || cp .env.example .env

seed:
	uv run python scripts/seed.py

ingest:
	uv run python scripts/ingest.py

# Run from the repo root so `rag/` (top-level) and `backend/app` are both importable.
backend:
	uv run python -m uvicorn app.main:app --app-dir backend --reload --port 8000

# CD-1002 by default (refund, pauses for approval). make demo TICKET=CD-1005 for an escalation.
TICKET ?= CD-1002
demo:
	uv run python scripts/demo.py $(TICKET)

test:
	uv run pytest -q

lint:
	uv run ruff check .

# ---- Phase 14: evaluation and delivery ----
.PHONY: eval smoke terraform-validate compose-check

eval:
	uv run pytest tests/evaluation -q

compose-check:
	docker compose config -q

terraform-validate:
	@for c in aws azure gcp; do terraform -chdir=deployment/$$c init -backend=false && terraform -chdir=deployment/$$c validate || exit 1; done

BASE_URL ?= http://localhost:8000
smoke:
	BASE_URL=$(BASE_URL) bash deployment/scripts/smoke_test.sh
