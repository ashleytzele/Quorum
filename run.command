#!/bin/bash
# Double-click to run Meeting Minutes over http://localhost (folder picker is
# reliable here, unlike opening index.html directly as a file://).
cd "$(dirname "$0")" || exit 1
PORT=8000
# Serve web/ with no-store headers so edits always show up on a normal reload
# (plain http.server lets the browser cache JS/CSS, which hides changes).
{ python3 - "$PORT" <<'PY'
import sys, http.server, socketserver
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory="web", **k)
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()
socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer(("", int(sys.argv[1])), Handler).serve_forever()
PY
} >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
open "http://localhost:$PORT/index.html"
echo "Meeting Minutes is running at http://localhost:$PORT"
echo "Keep this window open during your meeting. Close it (or press Ctrl+C) to stop."
trap 'kill $SERVER_PID 2>/dev/null' EXIT
wait $SERVER_PID
