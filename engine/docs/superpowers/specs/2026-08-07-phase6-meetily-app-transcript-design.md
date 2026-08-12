# Phase 6 — Read official Meetily's transcript

**Date:** 2026-08-07
**Status:** Design, approved (awaiting spec review)
**Context:** Sixth sub-project, and the one that unifies the whole product. The user runs
three systems: the **official Meetily desktop app** (`com.meetily.ai`) which records +
live-transcribes; **our engine** (this repo: `review.py` + templates) which turns a
transcript + notes into structured minutes; and **MeeTeam/Quorum** which holds pre-meeting
notes and minutes history. Decided division of labor: **the Meetily app is the capture +
transcription front-end; our engine reads its transcript** (rather than transcribing audio
itself). This phase builds that seam — a read-only adapter over the app's SQLite plus a
`review.py` mode — so the three systems compose into one pipeline on the command line.

## Why

Official Meetily already does the hard capture work and exposes it in a local SQLite
(`~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite`): per meeting it
stores the full transcript. Our `retranscribe.sh`/local recording duplicates capture we no
longer need for app-recorded meetings. Reading the app's transcript is structurally the same
move Phase 2 made for Supabase — consume an external store — but simpler: a local, read-only
SQLite, no network, no auth. Once `review.py` can take that transcript, it already knows how
to fold in MeeTeam notes (`--meeting`) and publish minutes back (`--publish`), so the full
three-way pipeline falls out with no new capture code.

## Confirmed data model (read from the live DB)

- `meetings(id TEXT pk, title, created_at, updated_at, folder_path)` — `folder_path` points
  at the recording dir (`~/Movies/meetily-recordings/…`). 11 rows in the user's DB.
- `transcript_chunks(meeting_id pk, meeting_name, transcript_text, model, model_name,
  chunk_size, overlap, created_at)` — **`transcript_text` is the full assembled transcript**,
  timestamped per line (`[00:07] specifically in my opinion.`). Present for most meetings
  (9 of 11).
- `transcripts(id pk, meeting_id, transcript, timestamp, summary, action_items, key_points,
  audio_start_time, audio_end_time, duration, speaker, …)` — 374 rows: the per-chunk
  transcript pieces with timing; `speaker` is mostly blank. Used as the FALLBACK to assemble
  a transcript when a meeting lacks a `transcript_chunks` row.
- The app's own `summary_processes`/`transcripts.summary` (its LLM summaries) are IGNORED —
  our engine produces the structured minutes.

## Decisions (settled in brainstorming)

- **Meetily app = capture; our engine reads its transcript** (not re-transcribe). Re-running
  our `retranscribe.sh` on the app's `folder_path` audio for higher accuracy was considered
  (option 2) and deferred — `folder_path` is captured so it stays possible later.
- **Read-only.** The adapter opens the SQLite with `?mode=ro`; it never writes to the app's
  data. This is the user's live meeting history — treat it as sacred.
- **CLI-first.** A `meetily_app.py` adapter + two `review.py` flags. No front-end picker this
  phase (the Phase-5 GUI or MeeTeam could list app meetings later).
- **Transcript kept verbatim** (with the `[MM:SS]` timestamps). `review.py` line-numbers the
  transcript anyway and treats it as the secondary source; the timestamps are harmless and
  can aid line cites. No stripping.

## Scope

### New module: `meetily_app.py`
Read-only helpers over the app's SQLite, isolated like `quorum.py`.

- `_db_path() -> Path` — `MEETILY_APP_DB` env override, else the default
  `~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite`. `SystemExit` with a
  clear message if the file doesn't exist.
- `_connect(db_path)` — `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`, read-only.
- `list_meetings(db_path=None) -> list[dict]` — `[{id, title, created_at, folder_path}]`,
  newest-first by `created_at`.
- `get_transcript(meeting_id, db_path=None) -> str` — return `transcript_chunks.transcript_text`
  for the meeting; if absent/empty, assemble from `transcripts` (text ordered by
  `audio_start_time`, each line prefixed with `speaker` only when non-blank). `SystemExit`
  if the meeting id matches nothing or yields an empty transcript.
- `_assemble_from_chunks(rows) -> str` — PURE helper (list of `(speaker, text)` →
  joined transcript), unit-testable without a DB.

### `review.py` — two additive modes
- `--list-meetily` (utility, early-return like `--sync-templates`): print each app meeting as
  `<id>  <YYYY-MM-DD>  <title>` (via `_list_meetily_meetings()`), then return. No OpenAI key
  needed.
- `--meetily-app <meeting-id>` (transcript source): the transcript comes from
  `_transcript_via_meetily_app(<id>)` instead of `transcribe(recording)`; the `recording`
  positional becomes **optional** in this mode. Everything downstream is unchanged — notes
  fold (local + `--meeting`), template resolution, two-pass, write, optional Phase-4 status
  writes (gated on `--meeting`, unaffected).
- Thin wrappers `_transcript_via_meetily_app(id)` and `_list_meetily_meetings()` (`import
  meetily_app` inside) are the stub seams tests patch — no SQLite in unit tests.
- **Guard update:** the "a recording is required" check becomes "a recording OR
  `--meetily-app` is required." Output filename: `<stem>_<date>.md` where `<date>` =
  `_date_from(recording)` when a recording is given, else today's date (app-transcript runs
  have no local audio filename to derive from).

### Composition (no new code — falls out of the above)
```
./review.py --list-meetily                                        # discover the app meeting id
./review.py --meetily-app <app-id> notes.md -t weekly_review.json # app transcript + local notes
./review.py --meetily-app <app-id> --meeting <quorum-id>          # app transcript + Quorum notes -> minutes .md
./review.py --publish <quorum-id> weekly_review_<date>.md         # -> Quorum minutes/history
```

## Non-goals (deferred)
- No re-transcription of the app's `folder_path` audio (option 2, deferred).
- No writes to the app's SQLite — strictly read-only.
- No front-end picker (GUI/MeeTeam) this phase.
- No speaker diarization handling beyond passing through a non-blank `speaker` label.
- No import of the app's own summaries — our templates produce the minutes.
- Phase-5 local recording is left in place but dormant for app-captured meetings.

## Error handling
- Missing DB (app not installed / path wrong) → `SystemExit` naming the expected path and the
  `MEETILY_APP_DB` override.
- `--meetily-app <id>` with an unknown id or a meeting that has no transcript yet → clear
  `SystemExit` (don't spend an OpenAI call on an empty transcript).
- `--list-meetily` with an empty DB → print a "no meetings found" line, exit 0.
- The read-only connection means a bug can never corrupt the user's meeting history.

## Testing / check
- **`meetily_app.py` (pytest, offline):** build a tiny temp SQLite with the relevant tables
  and rows in a fixture, then test: `get_transcript` returns `transcript_chunks.transcript_text`;
  falls back to assembling from `transcripts` (ordered, speaker-prefixed) when no chunk;
  `SystemExit` on unknown id / empty transcript; `list_meetings` newest-first; `_db_path`
  env override and missing-file `SystemExit`; `_assemble_from_chunks` pure. All read-only,
  no dependency on the real app DB.
- **`review.py` (extend `test_review.py`):** `--meetily-app <id>` uses the stubbed transcript
  and does NOT call `transcribe` (and needs no recording); `--list-meetily` prints via the
  stub and returns; the recording-or-meetily-app guard; app-transcript run composes with
  local notes and (stubbed) `--meeting` notes. Phase 1–5 tests stay green.
- **Manual E2E:** `./review.py --list-meetily` shows real app meetings; pick one; generate
  with local notes; eyeball the minutes.

## Config / migration
- No schema change (read-only), no `.env` change (OpenAI key as today; no Supabase needed
  unless `--meeting`/`--publish` are used). `MEETILY_APP_DB` optional override.
- No new dependency — `sqlite3` is stdlib.

## Open items
- Whether to strip `[MM:SS]` timestamps from the transcript before generation (default: keep
  — decide if the model output shows timestamp noise).
- Whether `--list-meetily` should also show which meetings already have a `transcript_chunks`
  row vs. only `transcripts` (nice-to-have; skip for v1).
