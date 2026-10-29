#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

PYTHON="${PYTHON:-python3}"
if [ -f ".venv311/bin/python" ]; then
    PYTHON=".venv311/bin/python"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
fi

exec "$PYTHON" scripts/stop_live_demo.py "$@"
