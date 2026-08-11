#!/usr/bin/env bash
# Elite Marcom website — start the local server (reuses the existing .venv)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Environment not found. Run ./install.sh once first." >&2
  exit 1
fi

# load .env if present (development convenience)
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

echo "Starting Elite Marcom website at http://127.0.0.1:${EM_PORT:-8847}/"
exec ./.venv/bin/python -m uvicorn server.main:app --host "${EM_HOST:-127.0.0.1}" --port "${EM_PORT:-8847}"
