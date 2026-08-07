# Phase 5 — Local GUI (single-user, no cloud)

**Date:** 2026-08-07
**Status:** Design, approved (awaiting spec review)
**Context:** Fifth sub-project. Phases 1–4 built a pipeline (`review.py`) plus a
Supabase-backed multi-user web app (MeeTeam/Quorum) with a browser↔Mac handoff. But in
actual use it's a single operator, so the whole cloud/web/handoff layer is overhead. The
fully-local pipeline already exists (Phase 1 local-file mode); this phase gives it a small
**local web GUI** so notes, recording, generation, and past minutes all live in one place on
the Mac — no Supabase, no meeting-id copying, no handoff card.

This phase adds a new `local/` app to the meetily repo. It does not touch Supabase or the
MeeTeam repo, and leaves `review.py`'s CLI (incl. the Supabase modes) unchanged.

## Why

Established with the user: team members do **not** submit remotely — it's effectively one
person. So the multi-user justification for the web/Supabase layer doesn't hold for this
use. The pipeline is already local (`./review.py <rec> <notes.md…> -t <template>`); what's
missing is a comfortable UI for note-entry, in-app recording, one-click generate, and
browsing past minutes — without a terminal.

## Decisions (settled in brainstorming)

- **Local web app, not a native desktop app.** A Python (Flask) backend serves one HTML
  page at `localhost`; launched by `./run-local.command`, opens in the browser. Reuses the
  existing Python stack; no Electron/Tauri/packaging.
- **In-app recording (Record/Stop buttons).** The backend spawns/stops ffmpeg on the macOS
  Aggregate device — no terminal step. One recording at a time.
- **Flask** (one new dependency) for routing/JSON — far less code than hand-rolled
  `http.server`.
- **Reuse MeeTeam's `styles.css`** (copied into the app) so it looks premium + theme-aware
  for free.
- **Plain-folder storage, no SQLite.** Everything on disk, inspectable, and read directly by
  `review.py`.

## Architecture

```
meetily/
  local/
    serve.py              # Flask backend (localhost-only)
    static/
      index.html          # the single page
      app.js              # fetch() calls to the API
      styles.css          # copied from MeeTeam web/styles.css
  run-local.command       # sources .env, launches serve.py, opens the browser
  requirements-local.txt  # flask (pipeline deps already in requirements.txt)
  meetings/               # DATA ROOT (gitignored)
    <slug>/
      meta.json           # {title, date, template, created}
      notes/*.md          # pre-meeting notes, one file per project
      recording.m4a       # captured in-app
      minutes.md          # generated; editable in the GUI
```

- `serve.py` binds **127.0.0.1 only** (never 0.0.0.0) — not exposed on the network; no auth
  (single user, local).
- It **shells out to the existing `review.py`** for generation (local-file mode) and spawns
  **ffmpeg** for recording — it does not reimplement the pipeline.
- `run-local.command` does `set -a; . ./.env; set +a; python local/serve.py` so
  `OPENAI_API_KEY` is inherited and passed to the `review.py` subprocess (no dotenv dep).
- **Status is derived from files**, not stored: no `recording.m4a` → "Ready to record";
  recording but no `minutes.md` → "Recorded"; `minutes.md` present → "Minutes ready".

## Backend API (`serve.py`, JSON over localhost)

- `GET /` → `static/index.html`; `GET /static/*` → assets.
- `GET /api/templates` → `[{stem, name, description}]` — scan the repo's `*.json` for objects
  with top-level `name` + `sections` (local listing ignores the Supabase `registry` marker;
  it wants every real template).
- `GET /api/meetings` → `[{id, title, date, template, status}]` (id = folder slug), newest
  first.
- `POST /api/meetings` `{title, template}` → create `<slug>/` + `meta.json`, return it.
- `GET /api/meetings/<id>` → `{meta, notes:[{name,content}], minutes}` (minutes = "" if none).
- `PUT /api/meetings/<id>` `{title?, template?}` → update `meta.json`.
- `PUT /api/meetings/<id>/notes/<name>` `{content}` → write `notes/<name>.md` (create if new;
  `<name>` sanitized to a safe filename).
- `GET /api/record/status` → `{recording: bool, meeting_id|null}`.
- `POST /api/meetings/<id>/record/start` → resolve the Aggregate device index (Python port of
  `record.sh`'s `ffmpeg -list_devices` + parse), `Popen` ffmpeg → `<id>/recording.m4a`; refuse
  (409) if a recording is already running. Device name overridable via `RECORD_DEVICE`.
- `POST /api/meetings/<id>/record/stop` → send SIGINT to the ffmpeg process, wait, verify the
  file is non-empty; return `{ok, bytes}`.
- `POST /api/meetings/<id>/generate` → build argv `[python, review.py, <recording>,
  <notes/*.md…>, -t <template.json>, -o <id>/minutes.md]`, run it (inherit env for the API
  key), capture stdout; return `{ok, projects:[…], minutes, warnings}` (parse the
  `projects (N): …` line; surface stderr warnings). 400 if no recording yet.
- `PUT /api/meetings/<id>/minutes` `{content}` → overwrite `minutes.md` (the edited draft).

**Recording process management:** a single module-level record of `{proc, meeting_id,
out_path}`. Only one active recording process at a time (single user). `start` rejects if one
is live; `stop` SIGINTs and clears it. ffmpeg finalizes a valid `.m4a` on SIGINT (as in
`record.sh`).

## Frontend (`static/index.html` + `app.js`)

One page, MeeTeam styling:
- **Left sidebar:** meeting list (title · date · status pill), "New meeting".
- **Right panel** for the selected meeting:
  - title + **template dropdown** (from `/api/templates`), autosaved to `meta.json`.
  - **Notes editor:** a list of project notes (one `.md` each); add a project, edit its
    markdown (autosave). This is the pre-meeting-notes entry.
  - **● Record / ■ Stop** — toggles `record/start`/`stop`, polls `record/status`, shows
    elapsed/"recording…".
  - **Generate** — calls `generate`, shows the `projects (N)` line + any warnings, then the
    minutes.
  - **Minutes:** rendered + an editable textarea with **Save** (`PUT …/minutes`) — the
    preview/edit step (the AI sometimes needs a fix, e.g. a dropped project).

No framework — vanilla `fetch`, matching MeeTeam's plain-JS style.

## Non-goals (deferred)

- No auth, no network exposure (localhost only, single user).
- No Supabase/MeeTeam involvement; `review.py`'s `--meeting`/`--publish` modes untouched.
- No Present mode, no live transcript, no multi-user.
- No packaged `.app` — the `.command` launcher is the install.
- No SQLite — folders + `meta.json` are the store.
- No delete-meeting in v1 (delete the folder in Finder); can add later.

## Error handling

- `record/start` when one is already running → 409 with a clear message; device-not-found →
  clear error listing the audio devices seen (as `record.sh` does).
- `record/stop` with no active recording → 409; empty/absent output file → error (recording
  failed), don't leave a phantom "recorded" state.
- `generate` with no recording → 400; a `review.py` non-zero exit → return its stderr so the
  UI shows what failed (missing `OPENAI_API_KEY`, bad template, etc.); the meeting keeps its
  prior minutes (no partial overwrite — write `minutes.md` only on success).
- All filesystem writes stay within `meetings/<id>/`; `<id>` and note `<name>` are sanitized
  (no path traversal).

## Testing / check

- **Backend (pytest, offline):** pure/logic units, no live ffmpeg/OpenAI —
  - meeting create → folder + `meta.json` written; list → derived `status` per file presence.
  - templates listing filters to `name`+`sections` objects (a plain non-template JSON is
    excluded); does NOT require the `registry` marker.
  - the generate **argv builder** (recording + sorted note files + `-t template` + `-o
    minutes`) as a pure function.
  - the ffmpeg-device-index **parser** against a sample `-list_devices` string (finds the
    Aggregate index; errors when absent) — the same logic `record.sh` proved manually.
  - note/minutes read+save round-trip within a tmp meetings root; path-traversal attempt on
    `<id>`/`<name>` is rejected.
- **Manual E2E:** `./run-local.command` → create a meeting, add a project note, Record ~15s,
  Stop, Generate, confirm the minutes render and Save-edit works.

## Config / migration

- `requirements-local.txt` = `flask`; `requirements.txt` (openai, markitdown) still needed for
  `review.py`. `.env` (OPENAI_API_KEY) as today — sourced by `run-local.command`.
- `.gitignore` gains `meetings/` (personal notes, recordings, minutes) and keeps `*.m4a`.
- One-time macOS: the Aggregate device (VB-Cable + mic) from Phase 3 — same setup, now driven
  by the GUI instead of `record.sh`.

## Open items

- Default port (proposal: 8765) — cosmetic.
- Whether `record.sh` stays as a CLI alternative (yes — leave it; the GUI reuses the same
  device logic, not the script itself).
- Rendering minutes markdown in-page (MeeTeam bundles `markdown-it`) vs. showing raw — decide
  in the frontend task; raw textarea + a rendered preview is the target.
