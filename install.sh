#!/usr/bin/env bash
# Elite Marcom website — one-time dependency installation (POSIX)
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for cand in python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11+ is required. Please install it and re-run install.sh" >&2
  exit 1
fi

echo "Using $($PY --version)"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r requirements.txt
echo
echo "Dependencies installed. Start the website with: ./start-local.sh"
