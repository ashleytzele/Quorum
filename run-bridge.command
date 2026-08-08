#!/usr/bin/env bash
# Double-click to run the MeeTeam generate bridge at http://localhost:8899
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating .venv and installing deps…"
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements-local.txt
fi
set -a; [ -f .env ] && . ./.env; set +a
echo "Bridge on http://localhost:8899 — keep this window open while using MeeTeam."
exec ./.venv/bin/python local/bridge.py
