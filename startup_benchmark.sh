#!/bin/bash
# Benchmark startup script — optimized for raw throughput testing with k6 / load testing
# Use this ONLY for benchmarking on localhost or isolated test environments
# This Mode disables observability and tunes for maximum RPS
set -e

echo "🏃 FastAPI Benchmark Mode"
echo "────────────────────────────────────────"

# Run migrations
alembic upgrade head

# Multi-worker for parallel request handling
GUNICORN_WORKERS=$(python3 -c "from app.config import settings; print(settings.gunicorn_workers)")
HTTP_TOOL=$(python3 -c "from app.config import settings; print(settings.uvicorn_http)")
UVICORN_LOOP=$(python3 -c "from app.config import settings; print(settings.uvicorn_loop)")

echo "Settings:"
echo "  Mode: Benchmark (observability disabled)"
echo "  Workers: $GUNICORN_WORKERS"
echo "  Loop: $UVICORN_LOOP (or asyncio fallback on Windows)"
echo "  HTTP: $HTTP_TOOL (or h11 fallback)"
echo "────────────────────────────────────────"

# Start with optimized settings (no access logs, just errors for cleanliness)
exec gunicorn app.main:app \
  -k app.utils.tuned_worker.TunedUvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers $GUNICORN_WORKERS \
  --timeout 120 \
  --keep-alive 5 \
  --backlog 2048 \
  --error-logfile - \
  --access-logfile /dev/null