#!/usr/bin/env bash
# Double-click to run Quorum. Starts BOTH pieces and opens the Admin console:
#   • Quorum web app  → http://localhost:8000   (served from QUORUM_WEB_DIR)
#   • Generate bridge → http://localhost:8899   (this repo)
# Already-running servers are reused (not fought over). Close this window
# (or Ctrl-C) to stop whatever THIS launcher started.
#
# ponytail: the web app is expected to sit NEXT TO this engine folder (…/web beside …/engine).
# Override if it's elsewhere:  QUORUM_WEB_DIR=/path/to/web ./run-quorum.command
set -u
cd "$(dirname "$0")" || exit 1
SELF_DIR="$(pwd)"

WEB_DIR="${QUORUM_WEB_DIR:-$(cd "$SELF_DIR/../web" 2>/dev/null && pwd)}"
WEB_PORT="${QUORUM_WEB_PORT:-8000}"
BRIDGE_PORT=8899
pause(){ read -r -p "Press Return to close this window. " _; }
up(){ curl -sf -o /dev/null "http://localhost:$1/$2"; }   # up <port> <path>

if [ ! -d "$WEB_DIR" ]; then
  echo "Can't find the Quorum web folder: $WEB_DIR"
  echo "Set QUORUM_WEB_DIR to your Quorum repo's web/ folder, then try again."
  pause; exit 1
fi

# First run: bootstrap the Python venv the bridge needs.
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating .venv and installing deps (one-time)…"
  python3 -m venv .venv        || { echo "Couldn't create .venv."; pause; exit 1; }
  ./.venv/bin/pip install -q -r requirements-local.txt || { echo "Dependency install failed."; pause; exit 1; }
fi
set -a; [ -f .env ] && . ./.env; set +a

WEB_PID=""; BRIDGE_PID=""

# 1) Web app — reuse if a server already answers on the port, else start our own.
if up "$WEB_PORT" "index.html"; then
  WEB_STATE="already running (reused)"
else
  python3 - "$WEB_PORT" "$WEB_DIR" <<'PY' >/dev/null 2>&1 &
import sys, http.server, socketserver
port, root = int(sys.argv[1]), sys.argv[2]
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=root, **k)
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0"); super().end_headers()
socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer(("", port), H).serve_forever()
PY
  WEB_PID=$!; WEB_STATE="started"
fi

# 2) Generate bridge — reuse if up, else start (app degrades gracefully if absent).
if up "$BRIDGE_PORT" "health"; then
  :
else
  QUORUM_ORIGIN="${QUORUM_ORIGIN:-http://localhost:$WEB_PORT}" ./.venv/bin/python local/bridge.py >/dev/null 2>&1 &
  BRIDGE_PID=$!
fi

# Stop ONLY what this launcher started (never kill servers we reused).
cleanup(){ echo; echo "Stopping Quorum (services this launcher started)…"
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null
  [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null; }
trap cleanup EXIT
trap 'exit 0' INT TERM

# Wait for the web server to answer, then open the browser.
for _ in $(seq 1 25); do up "$WEB_PORT" "index.html" && break; sleep 0.3; done
if up "$BRIDGE_PORT" "health"; then BRIDGE_STATE="ready"; else BRIDGE_STATE="offline — AI generation off"; fi

open "http://localhost:$WEB_PORT/admin.html"
echo
echo "  Quorum is running ─────────────────────────────"
echo "   • Web app    http://localhost:$WEB_PORT   ($WEB_STATE)"
echo "   • Generator  http://localhost:$BRIDGE_PORT   [$BRIDGE_STATE]"
echo "  ────────────────────────────────────────────────"
echo "  Keep this window open. Close it (or Ctrl-C) to stop."
echo

# Hold the window open even if both were reused (nothing of ours to wait on).
while :; do sleep 3600; done
