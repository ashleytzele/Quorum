#!/usr/bin/env bash
# Record an online meeting's audio (both sides) to a file the pipeline reads.
# Needs a macOS Aggregate Device that combines VB-Cable (far end) + your mic.
# See README "Recording an online meeting" for the one-time Audio MIDI Setup.
set -euo pipefail

DEVICE_NAME="${RECORD_DEVICE:-Aggregate Device}"
OUTDIR="$(cd "$(dirname "$0")" && pwd)/recordings"

# ffmpeg avfoundation indices shift between reboots — resolve by name every run.
# ponytail: ffmpeg -list_devices always exits non-zero (it's not a real capture,
# just enumeration) — swallow that expected failure so set -e doesn't trip on it.
list_audio() {
  ffmpeg -f avfoundation -list_devices true -i "" 2>&1 \
    | awk '/AVFoundation audio devices:/{a=1;next} /AVFoundation video devices:/{a=0} a' \
    || true
}

if [[ "${1:-}" == "--list" ]]; then
  echo "Audio input devices ffmpeg sees:"; list_audio; exit 0
fi

IDX="$(list_audio | sed -n -E "s/.*\[([0-9]+)\] ${DEVICE_NAME}\$/\1/p" | head -1)"
if [[ -z "$IDX" ]]; then
  echo "Audio device '${DEVICE_NAME}' not found. Devices seen:" >&2
  list_audio >&2
  echo "Set RECORD_DEVICE=... or build the Aggregate Device (see README)." >&2
  exit 1
fi

mkdir -p "$OUTDIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
OUT="$OUTDIR/meeting_${TS}.m4a"
echo "Recording '${DEVICE_NAME}' (index ${IDX}) -> ${OUT}"
echo "Press Ctrl-C to stop."
ffmpeg -hide_banner -loglevel warning -f avfoundation -i ":${IDX}" -c:a aac "$OUT"

echo
echo "Saved ${OUT}"
echo "Next: ./review.py --meeting <meeting-id> \"${OUT}\""
