#!/bin/bash
# Production/default startup script — balanced for real-world traffic
set -e

# Activate virtual environment if available
if [ -f "/app/venv/bin/activate" ]; then
  source /app/venv/bin/activate
elif [ -f "./venv/bin/activate" ]; then
  source ./venv/bin/activate
fi

# Ensure local venv binaries are used when the script is executed directly
export PATH="/app/venv/bin:$PATH"

# start_prod.sh
echo "⚙️  FastAPI Production Server"
echo "────────────────────────────────────────"

# Port Cleanup: Ensure 8000 is free
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️ Port 8000 is busy, cleaning up existing processes..."
    fuser -k 8000/tcp || true
    sleep 2
fi

# Run migrations
alembic upgrade head

# Production settings: observability ON
export BENCHMARK_MODE_ENABLED=false

# Use auto detection for max compatibility across platforms
export UVICORN_LOOP="auto"
export UVICORN_HTTP="auto"
export UVICORN_TIMEOUT_KEEP_ALIVE=5

# the azure vm is a basic tier vm which only supports a max of 2 workers
export GUNICORN_WORKERS=${GUNICORN_WORKERS:-2}
export GUNICORN_TIMEOUT=120
export GUNICORN_KEEPALIVE=5
export GUNICORN_BACKLOG=2048

echo "Settings:"
echo "  Mode: Production (observability enabled)"
echo "  Workers: $GUNICORN_WORKERS"
echo "  Loop: auto (uvloop on Linux/macOS, asyncio on Windows)"
echo "  HTTP: auto"
echo "────────────────────────────────────────"

# Start with balanced settings (error log only, not access log)
exec gunicorn app.main:app \
  -k app.utils.tuned_worker.TunedUvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers "$GUNICORN_WORKERS" \
  --timeout 120 \
  --keep-alive 5 \
  --backlog 2048 \
  --error-logfile -
