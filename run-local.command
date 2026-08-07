#!/usr/bin/env bash
# Double-click to launch the local GUI at http://localhost:8765
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating .venv and installing deps…"
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements-local.txt
fi
set -a; [ -f .env ] && . ./.env; set +a
( sleep 1; open "http://localhost:8765" ) &
exec ./.venv/bin/python local/serve.py
