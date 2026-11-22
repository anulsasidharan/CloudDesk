#!/usr/bin/env bash
# Usage: BASE_URL=http://localhost:8000 deployment/scripts/smoke_test.sh
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8000}"
for path in /health/live /health; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL$path")
  [ "$code" = "200" ] || { echo "FAIL $path -> $code"; exit 1; }
  echo "ok $path"
done
