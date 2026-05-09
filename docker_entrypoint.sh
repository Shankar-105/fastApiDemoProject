#!/bin/bash
# Docker entrypoint: conditionally run startup script based on BENCHMARK_MODE_ENABLED config
set -e

# Load .env file if it exists
if [ -f /code/.env ]; then
    set -a
    source /code/.env
    set +a
fi

# Read BENCHMARK_MODE_ENABLED from config.py (Pydantic BaseSettings loads from .env)
# Use Python to safely evaluate the config
BENCHMARK_ENABLED=$(python3 -c "
from app.config import settings
print('true' if settings.benchmark_mode_enabled else 'false')
" 2>/dev/null || echo "false")

echo "Docker Entrypoint: Startup Script Selection"
echo "────────────────────────────────────────────"

if [ "$BENCHMARK_ENABLED" = "true" ]; then
    echo "✅ BENCHMARK_MODE_ENABLED=true → Running startup_benchmark.sh"
    echo "   (Observability OFF, aggressive tuning for k6 load testing)"
    exec /bin/bash /code/startup_benchmark.sh
else
    echo "✅ BENCHMARK_MODE_ENABLED=false → Running startup_dev.sh"
    echo "   (Observability ON, for development)"
    exec /bin/bash /code/startup_dev.sh
fi
