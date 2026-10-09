#!/bin/bash
#
# Update a single key inside an AWS Secrets Manager secret, then restart the
# ECS services that read it.
#
#   ./scripts/update-secret.sh qa OPENAI_API_KEY
#   ./scripts/update-secret.sh qa OPENAI_API_KEY --restart worker,beat
#
# The value is read from the terminal with echo off. It is never passed as an
# argument (argv is visible in `ps` and lands in shell history), never printed,
# and never written to a file outside a 0700 temp dir that is removed on exit
# including on failure.
#
# ECS injects Secrets Manager values at container start, so updating the secret
# changes nothing until the tasks are replaced. That is what --restart is for;
# forgetting it is the usual reason "I rotated the key and it still fails".

set -euo pipefail

ENV="${1:-}"
KEY="${2:-}"
RESTART=""

shift 2 2>/dev/null || true
while [ $# -gt 0 ]; do
  case "$1" in
    --restart) RESTART="${2:-}"; shift 2 ;;
    --restart=*) RESTART="${1#*=}"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$ENV" ] || [ -z "$KEY" ]; then
  cat >&2 <<USAGE
Usage: $0 <env> <KEY_NAME> [--restart svc1,svc2]

  env        qa | prod
  KEY_NAME   the field inside snugd/<env>/secrets, e.g. OPENAI_API_KEY
  --restart  comma-separated ECS services to force-redeploy afterwards
             (api, worker, beat). Required for the change to take effect.

Example:
  $0 qa OPENAI_API_KEY --restart worker
USAGE
  exit 2
fi

case "$ENV" in
  qa|prod) ;;
  *) echo "env must be 'qa' or 'prod' (got '$ENV')" >&2; exit 2 ;;
esac

AWS_REGION="${AWS_REGION:-us-east-1}"
SECRET_ID="snugd/${ENV}/secrets"
CLUSTER="snugd-${ENV}"

if [ "$ENV" = "prod" ]; then
  # prod has never been stood up; fail loudly rather than creating a secret
  # that nothing reads and everyone later assumes is live.
  if ! aws secretsmanager describe-secret --secret-id "$SECRET_ID" \
        --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "ERROR: $SECRET_ID does not exist. prod is not provisioned." >&2
    exit 1
  fi
fi

WORK="$(mktemp -d)"
chmod 700 "$WORK"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

echo "Secret:  $SECRET_ID"
echo "Key:     $KEY"
printf 'Paste the new value (input hidden), then press Enter: '
# -r so backslashes survive; -s so it is not echoed to the terminal or history.
IFS= read -rs VALUE
echo
if [ -z "$VALUE" ]; then
  echo "ERROR: empty value, nothing written." >&2
  exit 1
fi

echo "Fetching current secret..."
aws secretsmanager get-secret-value --secret-id "$SECRET_ID" \
  --region "$AWS_REGION" --query SecretString --output text > "$WORK/current.json"

# The value goes in via the environment, not argv, so it stays out of `ps`.
KEY="$KEY" NEW_VALUE="$VALUE" python3 - "$WORK/current.json" "$WORK/next.json" <<'PY'
import json, os, sys

src, dst = sys.argv[1], sys.argv[2]
key, value = os.environ["KEY"], os.environ["NEW_VALUE"]

with open(src) as fh:
    data = json.load(fh)
if not isinstance(data, dict):
    sys.exit("Secret is not a JSON object; refusing to overwrite it.")

existed = key in data
data[key] = value

with open(dst, "w") as fh:
    json.dump(data, fh)

# Report shape, never contents.
print(f"  {'updated' if existed else 'ADDED (key was not present)'}: {key}")
print(f"  secret now has {len(data)} keys")
PY

unset VALUE

echo "Writing new version..."
aws secretsmanager put-secret-value --secret-id "$SECRET_ID" \
  --region "$AWS_REGION" --secret-string "file://$WORK/next.json" \
  --query 'VersionId' --output text | sed 's/^/  new version: /'

if [ -n "$RESTART" ]; then
  echo "Restarting: $RESTART"
  IFS=',' read -ra SERVICES <<< "$RESTART"
  for SVC in "${SERVICES[@]}"; do
    SVC="$(echo "$SVC" | tr -d '[:space:]')"
    [ -z "$SVC" ] && continue
    aws ecs update-service --cluster "$CLUSTER" --service "$SVC" \
      --force-new-deployment --no-cli-pager --query 'service.serviceName' \
      --output text | sed 's/^/  redeploying: /'
  done
  echo "Waiting for services to stabilise..."
  # shellcheck disable=SC2086
  aws ecs wait services-stable --cluster "$CLUSTER" --services ${RESTART//,/ }
  echo "Done."
else
  echo
  echo "NOTE: no services restarted. ECS reads secrets at container start, so"
  echo "      the old value stays live until you redeploy. Re-run with"
  echo "      --restart worker  (or whichever services read this key)."
fi

echo
echo "If this value was ever pasted into a chat, a ticket, or a shell that"
echo "keeps history, treat it as exposed: issue a replacement and revoke it."
