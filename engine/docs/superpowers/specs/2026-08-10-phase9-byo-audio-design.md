# Phase 9 — Bring-your-own-audio for MeeTeam Generate (record in-browser or import a file)

**Date:** 2026-08-10
**Status:** Design, approved (awaiting spec review)
**Context:** Phase 7 put a "Generate with Meetily" button in MeeTeam that pulls a transcript
from the Meetily app. But that forces the admin to record in a separate app. This phase lets
the admin **provide the audio directly** — either **record it in the browser** (with a device
picker) or **import an audio file** — so nothing but MeeTeam is needed for an in-person
meeting, and any pre-recorded file works too. The engine transcribes the audio locally (the
Phase-1 local-file path) and generates as usual.

## Why

The Meetily-app route is great when the admin already uses that app, but the "go to the other
app to record" step is the one remaining seam. Browsers can record from a chosen microphone
(`getUserMedia` + `MediaRecorder`) and list input devices (`enumerateDevices`) — on localhost,
which is a secure context — so the admin can record inside MeeTeam. And an **import** covers
anything already recorded (a Zoom file, Voice Memos, the Meetily app's own file). Both are just
"an audio file the bridge transcribes," so they share one backend and one code path after upload.

## Decisions (settled in brainstorming)

- **Both Record and Import**, plus the existing Meetily-recording option — three audio sources
  in the Generate card, one shared "transcribe + generate" backend.
- **The engine transcribes the audio** (`review.py` local-file mode → `retranscribe.sh` →
  whisper). Slower than the Meetily-app route (which pre-transcribed) — a minute or two, all
  local — but no app dependency. The UI says "Transcribing + generating…".
- **Browser recording captures the selected microphone.** Perfect for in-person (the room
  mic). For an online call the mic won't capture the far end unless the admin routes system
  audio into a virtual input — documented, not solved here (a browser page can't grab system
  audio without that). Import covers the online case (record the call elsewhere, drop the file).
- **The audio is transient.** The bridge saves the upload to a temp file, transcribes, and
  deletes it. No audio is stored in Supabase or committed. (`retranscribe.sh` may write a
  sidecar transcript next to the temp file; that's cleaned up too.)
- **`review.py`/`quorum.py`/`meetily_app.py` unchanged.** The bridge just calls `review.py`
  with an audio path instead of `--meetily-app`.

## Architecture

Same shape as Phase 7: MeeTeam (localhost) → local bridge (localhost:8899) → shells
`review.py`. The only new backend piece is a multipart endpoint that accepts an audio upload.

### Bridge — `local/bridge.py`
- `POST /generate-audio` (multipart/form-data; + `OPTIONS` preflight):
  fields `meeting_id`, `template` (optional), and file part `audio`.
  1. Reject (400) if `meeting_id` or the `audio` file is missing.
  2. Save the upload to a temp file, preserving a **safe** suffix from the client filename
     (whitelist audio extensions: `.m4a .mp3 .wav .webm .mp4 .ogg .aac .flac`; default `.webm`
     for a browser blob). Never trust/join the client filename into a path.
  3. Run `review.py <tempaudio> --meeting <meeting_id> [-t <template>.json] -o <tmp.md>`
     (cwd=repo root, inherited env; this transcribes the audio AND folds in the Quorum notes).
  4. Return `{ok, markdown, projects, warnings}` on success (returncode 0 + non-empty output),
     else 500 with `review.py`'s stderr. Always delete the temp audio, its sidecar, and the
     temp `.md` in a `finally`.
- Reuses the existing CORS `after_request`, `_parse_projects`, and the temp/commit-on-success
  pattern. A pure `_generate_audio_argv(python, review_py, audio, meeting_id, template, out)`
  is the unit-test seam.
- Guard: only one audio generation at a time is NOT required (each request is independent and
  runs its own subprocess) — but transcription is slow, so the frontend disables Generate
  during the run (as Phase 7 already does).

### MeeTeam — `web/minutes.html`
The Phase-7 "Generate from Meetily" card gains an **audio source** control:
- A small selector (radio/segmented): **Meetily recording** · **Record** · **Import**.
- **Meetily recording** (existing): the recording `<select>` (auto-matched); Generate → the
  existing `POST /generate` (JSON `{meeting_id, meetily_id, template}`).
- **Record**: a **device** `<select>` populated from
  `navigator.mediaDevices.enumerateDevices()` (kind `audioinput`; labels appear after a
  one-time mic-permission prompt), and **● Record / ■ Stop** using
  `getUserMedia({audio:{deviceId}})` + `MediaRecorder`. On stop, hold the recorded `Blob`.
  Generate → `POST /generate-audio` (multipart: the blob + `meeting_id` + `template`).
- **Import**: `<input type="file" accept="audio/*">`. On pick, hold the `File`. Generate →
  `POST /generate-audio` (multipart: the file + `meeting_id` + `template`).
- After either audio route returns, fill the editable `#ai-minutes` box + preview + status,
  exactly as Phase 7 (the `minutesMarkdown()` override still routes Finalize to the AI minutes).
- The card is still health-gated on the bridge; **Record/Import work even if there are no
  Meetily recordings** (the bridge being up is enough).

## Data flow (record-in-browser)
```
MeeTeam minutes page (localhost:8000), bridge up
  choose "Record" -> pick input device (enumerateDevices)
  ● Record (getUserMedia + MediaRecorder) ... ■ Stop  -> audio Blob (webm/mp4)
  click Generate
    -> POST /generate-audio  (multipart: audio blob, meeting_id, template)
       bridge: save temp.webm
            -> review.py temp.webm --meeting <q> -t <tpl> -o tmp.md
                 transcribe locally (retranscribe.sh/whisper) + fetch_notes(q) + template
            -> {markdown, projects}   (temp files deleted)
  -> fills the minutes editor -> review -> Finalize & archive (existing)
```
Import is identical from "click Generate" on, with a `File` instead of a recorded `Blob`.

## Non-goals (deferred)
- No system-audio capture in the browser (mic only; online calls use Import or a virtual input).
- No storing the audio anywhere persistent — transient temp on the Mac, deleted after.
- No change to the Meetily-app route or to `review.py`/`quorum.py`/`meetily_app.py`.
- No progress bar for transcription (just a "Transcribing + generating…" state); no chunked/live transcript.
- No upload size cap beyond Flask's default request limits (local, single admin) — documented.

## Error handling
- Missing `meeting_id`/`audio` → 400. Unsupported/absent audio → `review.py`/ffmpeg surfaces a
  clear error → 500 with stderr shown in the card.
- Any exception in `/generate-audio` returns a JSON 500 (so CORS header + `{error}` reach the
  browser — same wrap as Phase 7's `/generate`).
- Browser: `getUserMedia` denied or no input devices → the Record controls show a clear message
  and the admin can still use Import or the Meetily route. `MediaRecorder` unsupported → hide
  Record, keep Import.
- Temp files always cleaned up (`finally`), even on failure.

## Testing / check
- **Bridge (pytest, offline):** `_generate_audio_argv` pure (audio + `--meeting` + `-t` + `-o`);
  `POST /generate-audio` with a small in-memory file part and `subprocess.run` stubbed to write
  the `-o` file → returns markdown + projects; missing `audio`/`meeting_id` → 400; stubbed
  non-zero `review.py` → 500 + stderr, temp cleaned; OPTIONS preflight + CORS header present.
  No real whisper/OpenAI/Supabase in unit tests.
- **MeeTeam:** any extracted pure helper (e.g. pick the POST target by source, or the safe
  suffix) unit-tested in `lib.test.js`; the MediaRecorder/enumerateDevices/file-input DOM
  wiring is **browser-verified** (can't unit-test getUserMedia).
- **Manual E2E:** (1) Record in the browser (pick the mic, 15s, Stop) → Generate → minutes
  appear → Finalize. (2) Import a `.m4a`/`.mp3` → Generate → minutes appear.

## Config / migration
- No schema change, no new Python dependency (Flask handles multipart; `review.py` already
  transcribes local files). `.env` unchanged. `run-bridge.command` unchanged.
- Requires the local whisper stack `review.py` already uses (`whisper-cli`, the model,
  ffmpeg, the VAD model) — already present.

## Open items
- Whether to keep the Meetily-recording source at all once Record/Import exist (default: keep
  it — zero cost, and it's instant since the app already transcribed). 
- Exact `MediaRecorder` mime (`audio/webm` vs `audio/mp4` on Safari) — feature-detect and pick a
  supported one; ffmpeg handles both. Decide in the frontend task.
- Flask default max upload size — fine for typical meeting audio; note it and raise
  `MAX_CONTENT_LENGTH` only if a long recording is rejected.
