#!/bin/bash
set -e

SERVICE_TYPE=${SERVICE_TYPE:-api}

# An explicit command wins over SERVICE_TYPE dispatch.
#
# Without this the case statement below runs regardless, and an ECS
# containerOverrides command is silently discarded — a one-off
# `python -c "..."` task starts a Celery worker instead, then sits there
# consuming queues. scripts/deploy.sh's `scrape` command has been passing such
# an override since it was written, so it never did what it claimed.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

case "$SERVICE_TYPE" in
  api)
    echo "Starting FastAPI API server..."
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    echo "Starting Celery worker..."
    exec celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance
    ;;
  beat)
    echo "Starting Celery beat scheduler..."
    exec celery -A app.celery_app beat --loglevel=info
    ;;
  migrate)
    echo "Running Alembic migrations..."
    exec alembic upgrade head
    ;;
  *)
    echo "Unknown SERVICE_TYPE: $SERVICE_TYPE"
    echo "Valid values: api, worker, beat, migrate"
    exit 1
    ;;
esac
