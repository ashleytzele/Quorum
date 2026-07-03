#!/bin/bash
# Double-click to run Meeting Minutes over http://localhost (folder picker is
# reliable here, unlike opening index.html directly as a file://).
cd "$(dirname "$0")" || exit 1
PORT=8000
python3 -m http.server "$PORT" --directory web >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
open "http://localhost:$PORT/index.html"
echo "Meeting Minutes is running at http://localhost:$PORT"
echo "Keep this window open during your meeting. Close it (or press Ctrl+C) to stop."
trap 'kill $SERVER_PID 2>/dev/null' EXIT
wait $SERVER_PID
