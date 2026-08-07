#!/usr/bin/env bash
# Double-click to launch the local GUI at http://localhost:8765
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
( sleep 1; open "http://localhost:8765" ) &
exec /tmp/rvenv/bin/python local/serve.py
