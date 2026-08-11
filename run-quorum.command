#!/usr/bin/env bash
# Double-click to run Quorum. Starts BOTH pieces and opens the Admin console:
#   • Quorum web app  → http://localhost:8000   (served from QUORUM_WEB_DIR)
#   • Generate bridge → http://localhost:8899   (this repo)
# Keep this window open while you work. Close it (or press Ctrl-C) to stop both.
#
# ponytail: the web folder defaults to the usual location; override if you moved it:
#   QUORUM_WEB_DIR=/path/to/Quorum/web ./run-quorum.command
set -u
cd "$(dirname "$0")" || exit 1

WEB_DIR="${QUORUM_WEB_DIR:-$HOME/Desktop/Github/MeeTeam/web}"
WEB_PORT="${QUORUM_WEB_PORT:-8000}"
BRIDGE_PORT=8899
pause(){ read -r -p "Press Return to close this window. " _; }

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

# 1) Web app — static server with no-store headers so edits always show on reload.
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
WEB_PID=$!

# 2) Generate bridge (AI minutes). The app degrades gracefully if this is down.
QUORUM_ORIGIN="${QUORUM_ORIGIN:-http://localhost:$WEB_PORT}" ./.venv/bin/python local/bridge.py >/dev/null 2>&1 &
BRIDGE_PID=$!

trap 'echo; echo "Stopping Quorum…"; kill "$WEB_PID" "$BRIDGE_PID" 2>/dev/null' EXIT INT TERM

# Wait for the web server, then open the browser.
for _ in $(seq 1 25); do curl -sf -o /dev/null "http://localhost:$WEB_PORT/index.html" && break; sleep 0.3; done
# Bridge readiness (non-fatal).
BRIDGE_STATE="offline — start it later if you want AI generation"
for _ in $(seq 1 25); do curl -sf -o /dev/null "http://localhost:$BRIDGE_PORT/health" && { BRIDGE_STATE="ready"; break; }; sleep 0.3; done

open "http://localhost:$WEB_PORT/admin.html"
echo
echo "  Quorum is running ─────────────────────────────"
echo "   • Web app    http://localhost:$WEB_PORT   (Admin console)"
echo "   • Generator  http://localhost:$BRIDGE_PORT   [$BRIDGE_STATE]"
echo "  ────────────────────────────────────────────────"
echo "  Keep this window open. Close it (or Ctrl-C) to stop both."
echo
wait
