#!/usr/bin/env bash
# Re-transcribe a Meetily recording with VAD + a glossary prompt.
#
# Meetily runs whisper.cpp with neither. On Manglish meeting audio that costs
# you most of the transcript: without VAD the decoder falls into repetition
# loops ("Thanks. Thanks. Thanks.") and swallows whole minutes; without a
# prompt it invents plausible English for local proper nouns.
#
# Writes <recording>.manglish.txt next to the audio. Touches no database.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Model is overridable via WHISPER_MODEL — the CLI keeps the accurate large-v3 default;
# the MeeTeam bridge sets a faster model (large-v3-turbo) for interactive record/import.
MODEL="${WHISPER_MODEL:-$HOME/Library/Application Support/com.meetily.ai/models/ggml-large-v3-q5_0.bin}"
VAD="$DIR/ggml-silero-v5.1.2.bin"
GLOSSARY="$DIR/glossary.txt"

# --clean: denoise + normalize before transcribing. For quiet/noisy recordings
# (e.g. a phone on a table in a loud room). Skip it on already-clean audio — the
# filter can pump up background hiss and add artifacts. ponytail: opt-in, not default.
CLEAN=0; FILEARG=""
for a in "$@"; do
  if [ "$a" = "--clean" ]; then CLEAN=1; else FILEARG="$a"; fi
done
[ -n "$FILEARG" ] || { echo "usage: $(basename "$0") [--clean] <recording-folder|audio-file>" >&2; exit 1; }

# ponytail: large-v3, not turbo. Turbo benchmarks better on Singlish corpora
# but collapsed into "Thank you." x10 on this actual audio. Measured, not assumed.
[ -f "$MODEL" ] || { echo "missing model: $MODEL" >&2; exit 1; }

if [ -d "$FILEARG" ]; then AUDIO="$FILEARG/audio.mp4"; else AUDIO="$FILEARG"; fi
[ -f "$AUDIO" ] || { echo "no audio found at: $AUDIO" >&2; exit 1; }

[ -f "$VAD" ] || curl -fsSL -o "$VAD" \
  https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin

PROMPT="$(grep -v '^#' "$GLOSSARY" | tr '\n' ' ')"
[ "${#PROMPT}" -lt 900 ] || echo "warn: glossary is ${#PROMPT} chars; whisper truncates ~224 tokens" >&2

TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT
# ponytail: single-pass loudnorm (not 2-pass) is close enough here; afftdn nf=-25
# plus a 90–7500 Hz voice band strip steady room noise. Recovered ~57s of a 66s
# clip that raw gave up on at ~11s (measured). Only runs under --clean.
AF=""
[ "$CLEAN" -eq 1 ] && AF="-af highpass=f=90,lowpass=f=7500,afftdn=nf=-25,loudnorm=I=-18:TP=-1.5"
ffmpeg -v error -y -i "$AUDIO" $AF -ar 16000 -ac 1 -c:a pcm_s16le "$TMPD/a.wav"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMPD/a.wav" | cut -d. -f1)

# ponytail: 60s independent windows. Whisper conditions each window on the text
# it just produced, so on noisy audio one repeated phrase feeds itself and eats
# the rest of the file — a 13-min meeting collapsed to 16 unique lines repeated
# 575 times. Restarting every 60s bounds a loop to one window instead of all of
# them (measured on that file: 16 unique lines -> 54). Cost is a hard cut at each
# boundary, which can clip a sentence. Raise WINDOW if that bothers you more than
# the loops do.
# WINDOW overridable via WHISPER_WINDOW. Smaller = tighter loop-bounding but more model
# reloads (slower); larger = far fewer reloads (faster) at some risk of a longer runaway.
WINDOW="${WHISPER_WINDOW:-60}"
OUT="${AUDIO%.*}.manglish.txt"

# Post-processing shared by both passes: drop blank lines, strip the [timestamp]
# prefix, and collapse consecutive duplicate lines.
_dedupe() { grep -ve '^[[:space:]]*$' \
  | awk '{ t=$0; sub(/^\[[^]]*\][[:space:]]*/,"",t); if (t!=prev) print; prev=t }'; }

if [ -n "${WHISPER_SINGLE_PASS:-}" ]; then
  # SINGLE-PASS (opt-in, e.g. the interactive MeeTeam bridge): one whisper-cli call over
  # the whole file — one model load instead of one per 60s window, so far faster on long
  # audio. --carry-initial-prompt still carries the glossary across the whole file. Trade-off:
  # no per-window loop-bounding, so noisy audio CAN repetition-collapse (see the windowed
  # note below). The CLI default stays windowed; opt in only when speed beats that risk.
  whisper-cli -m "$MODEL" -f "$TMPD/a.wav" -l en -np \
    --vad -vm "$VAD" -sns \
    --prompt "$PROMPT" --carry-initial-prompt 2>/dev/null | _dedupe > "$OUT"
else
  {
    off=0
    while [ "$off" -lt "${DUR:-0}" ]; do
      # --carry-initial-prompt: without it the glossary applies only to the first
      # 30s window and decays to nothing over a long meeting.
      whisper-cli -m "$MODEL" -f "$TMPD/a.wav" -l en -np \
        --vad -vm "$VAD" -sns \
        --prompt "$PROMPT" --carry-initial-prompt \
        -ot $((off * 1000)) -d $((WINDOW * 1000)) 2>/dev/null
      off=$((off + WINDOW))
    done
  } | _dedupe > "$OUT"
fi

echo "wrote $OUT  ($(wc -l < "$OUT" | tr -d ' ') lines)"
