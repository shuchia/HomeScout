#!/bin/bash
set -euo pipefail

# Promote code between environments via fast-forward merge.
# Usage: ./scripts/promote.sh <target>
#   ./scripts/promote.sh qa    — merge main → release/qa
#   ./scripts/promote.sh prod  — merge release/qa → release/prod

TARGET=${1:?Usage: promote.sh <qa|prod>}
CURRENT=$(git branch --show-current)

case "$TARGET" in
  qa)
    echo "Promoting main → release/qa..."
    git checkout release/qa
    git merge main --ff-only
    git push origin release/qa
    ;;
  prod)
    echo "Promoting release/qa → release/prod..."
    git checkout release/prod
    git merge release/qa --ff-only
    git push origin release/prod
    echo ""
    echo "Prod deploy requires approval in GitHub Actions."
    echo "Check: https://github.com/shuchia/HomeScout/actions"
    ;;
  *)
    echo "Unknown target: $TARGET"
    echo "Usage: promote.sh <qa|prod>"
    exit 1
    ;;
esac

# Return to original branch
git checkout "$CURRENT"
echo "Done. Back on $CURRENT."
