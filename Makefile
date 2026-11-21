# Windows: run from Git Bash / WSL, or call the commands directly (see CLAUDE.md section 14).
# Uses uv; PYTHONPATH must include backend.

.PHONY: setup backend test lint

setup:
	uv sync
	@test -f .env || cp .env.example .env

backend:
	cd backend && uv run --project .. uvicorn app.main:app --reload --port 8000

test:
	uv run pytest -q

lint:
	uv run ruff check .
