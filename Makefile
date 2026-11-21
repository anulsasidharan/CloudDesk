# Windows: run from Git Bash / WSL, or call the commands directly (see CLAUDE.md section 14).
# Uses uv; PYTHONPATH must include backend.

.PHONY: setup seed ingest backend test lint

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

test:
	uv run pytest -q

lint:
	uv run ruff check .
