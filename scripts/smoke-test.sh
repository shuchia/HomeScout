#!/bin/bash
set -euo pipefail

# Comprehensive smoke tests for HomeScout backend deployments.
# Usage: ./scripts/smoke-test.sh <env>

ENV=${1:?Usage: smoke-test.sh <env>}

case "$ENV" in
  dev)  BASE_URL="https://api-dev.snugd.ai" ;;
  qa)   BASE_URL="https://api-qa.snugd.ai" ;;
  prod) BASE_URL="https://api.snugd.ai" ;;
  *)    echo "Unknown env: $ENV"; exit 1 ;;
esac

FAILED=0

check() {
  local name="$1"
  shift
  echo -n "${name}... "
  if "$@" 2>/dev/null; then
    echo "OK"
  else
    echo "FAIL"
    FAILED=1
  fi
}

echo "=== Smoke testing ${ENV} at ${BASE_URL} ==="

# 1. Health check
check "Health check" bash -c "
  curl -sf '${BASE_URL}/health' | python3 -c \"
import sys,json; d=json.load(sys.stdin); assert d['status']=='healthy', f'unhealthy: {d}'\"
"

# 2. Apartments stats endpoint
check "Apartments stats" bash -c "
  curl -sf '${BASE_URL}/api/apartments/stats' | python3 -c \"
import sys,json; d=json.load(sys.stdin); assert d.get('total_apartments',0)>=0, 'bad stats'\"
"

# 3. Apartments list endpoint
LIST_FILE=$(mktemp)
curl -sf "${BASE_URL}/api/apartments/list?limit=1" > "$LIST_FILE" 2>/dev/null || echo '{}' > "$LIST_FILE"
check "Apartments list" python3 -c "
import json
d = json.load(open('${LIST_FILE}'))
assert 'apartments' in d
"

# 4. True cost data present (if DB has data)
check "True cost field" python3 -c "
import json
apts = json.load(open('${LIST_FILE}')).get('apartments', [])
if not apts:
    print('SKIP (no apartments)', end='')
else:
    assert 'true_cost_monthly' in apts[0], 'true_cost_monthly missing'
"
rm -f "$LIST_FILE"

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "=== All smoke tests passed for ${ENV} ==="
else
  echo "=== SOME SMOKE TESTS FAILED for ${ENV} ==="
  exit 1
fi
