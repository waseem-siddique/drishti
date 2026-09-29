#!/usr/bin/env bash
# DRISHTI launcher
#   ./run.sh                -> http://127.0.0.1:8000
#   ./run.sh 9000           -> custom port
#   ./run.sh 8000 reseed    -> rebuild the demo dataset
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8000}"
EXTRA=""
if [ "${2:-}" = "reseed" ]; then EXTRA="--reseed"; fi

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "Python 3.9+ is required but was not found on PATH." >&2
  exit 1
fi

echo "Starting DRISHTI on port ${PORT} ..."
exec "$PY" backend/app.py --port "$PORT" $EXTRA
