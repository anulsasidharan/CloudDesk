#!/usr/bin/env bash
# PreToolUse hook (Bash). Gates `git commit` on lint + tests. Fails open if tools are missing.
input="$(cat)"
case "$input" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
elif [ -x .venv/bin/python ]; then PY=.venv/bin/python
else exit 0; fi

# Type check: <TODO: command> (none configured in pyproject.toml yet)

staged="$(git diff --cached --name-only --diff-filter=ACM -- '*.py' 2>/dev/null)"
if [ -n "$staged" ] && "$PY" -m ruff --version >/dev/null 2>&1; then
  # shellcheck disable=SC2086
  if ! out="$("$PY" -m ruff check $staged 2>&1)"; then
    echo "pre-commit: ruff failed on staged files" >&2; echo "$out" | tail -20 >&2; exit 2
  fi
fi

if "$PY" -m pytest --version >/dev/null 2>&1; then
  if ! out="$("$PY" -m pytest -q 2>&1)"; then
    echo "pre-commit: tests failed" >&2; echo "$out" | tail -30 >&2; exit 2
  fi
fi
exit 0
