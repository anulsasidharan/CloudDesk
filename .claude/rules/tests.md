---
paths:
  - "tests/**"
---
# Tests

- Tests run offline: `DEMO_MODE=true`, `LLM_PROVIDER=fake`, `VECTOR_STORE=memory`, `USE_FAKE_REDIS=true`, temp SQLite.
- Run with `.venv/Scripts/python.exe -m pytest -q` (Windows). `PYTHONPATH` must include `backend`.
- pytest uses `asyncio_mode = "auto"`; do not add `@pytest.mark.asyncio` with another loop scope.
- Auth fixtures: `agent_headers`, `admin_headers`, `viewer_headers`.
- One feature, one PRD row, at least one test.
- Report only the pass/fail digest and the first failure, not full output.
