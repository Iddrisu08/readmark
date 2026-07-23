#!/usr/bin/env bash
# Post-deploy smoke test. Exits non-zero if any critical check fails.
# Usage: scripts/smoke-test.sh https://getreadmark.com
set -euo pipefail

BASE="${1:-http://localhost:8000}"
API="$BASE/api"
fail=0

check() { # name, expected_code, url [, method, data]
  local name="$1" want="$2" url="$3" method="${4:-GET}" data="${5:-}"
  local code
  if [ -n "$data" ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "$url" \
      -H 'Content-Type: application/json' -d "$data")
  else
    code=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "$url")
  fi
  if [ "$code" = "$want" ]; then
    printf '  ✅ %-28s %s\n' "$name" "$code"
  else
    printf '  ❌ %-28s got %s, want %s\n' "$name" "$code" "$want"; fail=1
  fi
}

echo "Smoke testing $BASE"
check "health"   200 "$API/health"
check "ready"    200 "$API/ready"
check "metrics"  200 "$BASE/metrics"

EMAIL="smoke-$RANDOM@example.com"
check "register" 201 "$API/auth/register" POST \
  "{\"email\":\"$EMAIL\",\"password\":\"smoketest123\",\"name\":\"Smoke\"}"
check "login"    200 "$API/auth/login" POST \
  "{\"email\":\"$EMAIL\",\"password\":\"smoketest123\"}"

[ "$fail" = 0 ] && echo "All checks passed." || { echo "FAILED."; exit 1; }
