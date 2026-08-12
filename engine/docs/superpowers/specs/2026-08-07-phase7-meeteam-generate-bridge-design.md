# Phase 7 — Generate minutes inside MeeTeam (local bridge)

**Date:** 2026-08-07
**Status:** Design, approved (awaiting spec review)
**Context:** The culmination of the merge. The three systems now exist and all the plumbing
is built (Phases 1–6): read team notes from MeeTeam/Supabase (`quorum.py`), read the
transcript from the official Meetily app's SQLite (`meetily_app.py`), generate templated
minutes (`review.py`), publish minutes back (MeeTeam's own Finalize). Phase 7 puts a real
**"Generate with Meetily"** button inside MeeTeam's admin minutes page so the admin does the
whole post-meeting job in one place — no terminal, no app-switching for the generate step.

## The settled model (why it's shaped this way)

Investigated and confirmed: the official Meetily desktop app (`/Applications/meetily.app`,
Tauri/Rust, CoreAudio capture) exposes **no HTTP/WebSocket API** — its frontend↔backend is
internal Tauri commands. So we cannot start/stop its recording or tap its live transcript
from outside; its only external seam is its **read-only SQLite** (already used in Phase 6).

Therefore the user-facing model is **cockpit + dumb recorder**, joined at one seam:
- **MeeTeam = the cockpit.** Create meeting, team submits notes, and (Phase 7) Generate →
  review → Finalize — all in MeeTeam.
- **Meetily app = a tape recorder.** Two clicks during the meeting (record / stop); the admin
  never "works" in it.
- **They meet only at Generate**, where a local bridge pulls the recording's transcript +
  the team's notes and produces the minutes.

Rejected (with reasons, so they stay rejected): record-from-MeeTeam (no API — would need UI
automation or a forked Rust app), live-transcript-in-MeeTeam (same wall; only viable via
SQLite polling and not worth it), and redirect/deep-link stitching between the two apps
(automates nothing — recording still starts manually — while adding fragile moving parts).

## Architecture — a local bridge MeeTeam calls

MeeTeam is a static SPA with no compute; the transcript SQLite, Supabase service key, and the
OpenAI call all live on the admin's Mac. So a small **local Flask server (`local/bridge.py`,
bound `127.0.0.1`)** does the work, and MeeTeam's admin page `fetch()`es it. The admin already
serves MeeTeam locally (`run.command`, `localhost:8000`), so both are localhost and the
browser can reach the bridge; a CORS allowance lets the MeeTeam origin call it.

The bridge is thin — it **shells the existing `review.py`** (which already composes
`--meetily-app` + `--meeting` + template); it does not re-implement anything.

## Scope

### New module: `local/bridge.py` (Flask, 127.0.0.1)
- `GET /health` → `{"ok": true}` — so MeeTeam can detect whether the helper is running
  (graceful degrade).
- `GET /recordings` → `meetily_app.list_meetings()` (`[{id,title,created_at}]`) — feeds the
  MeeTeam recording picker / auto-match.
- `POST /generate` `{meeting_id, meetily_id, template?}` → run
  `review.py --meetily-app <meetily_id> --meeting <meeting_id> [-t <template>.json] -o <tmp>`
  with `cwd`=repo root and inherited env (OpenAI + Supabase from `.env`); read the produced
  markdown; return `{ok, markdown, projects, warnings}`. Omitting `template` lets `review.py`
  use the meeting's stored `meetings.template` (Phase 3). Temp-file + return only on success;
  a `review.py` failure returns 500 with its stderr (no partial minutes).
- **CORS:** an `after_request` sets `Access-Control-Allow-Origin` to the configured MeeTeam
  origin (default `http://localhost:8000`, overridable via `MEETEAM_ORIGIN`), plus the
  `OPTIONS` preflight. Bind `127.0.0.1` only — never exposed off-machine.
- Reuses `quorum.py`, `meetily_app.py`, `review.py` unchanged. A `_generate_argv(...)` pure
  helper (like Phase 5) is the unit-test seam; `subprocess.run` is stubbed in tests.
- Launched by **`run-bridge.command`** (sources `.env`, `exec .venv/bin/python local/bridge.py`).

### MeeTeam frontend: `web/minutes.html` (+ `web/config.js`)
The admin minutes page gains an AI path beside the existing client-side `generate()`:
- **Bridge URL** from `config.js` (`window.BRIDGE_URL = 'http://localhost:8899'`).
- On load, `GET {BRIDGE_URL}/health`; if unreachable, the AI button is hidden/disabled with a
  hint ("start the local Meetily helper") — the existing structured minutes flow is untouched.
- A new **"Generate with Meetily"** button: fetch `/recordings`, **auto-select** the recording
  whose title/date best matches this meeting (a small `<select>` lets the admin override), then
  `POST /generate {meeting_id: meeting.id, meetily_id, template: meeting.template}`.
- The returned markdown goes into a new **editable `#ai-minutes` textarea** (shown when AI
  minutes exist) and is rendered as the preview in `#d-body` (via the existing `markdown-it`).
  It shows `projects (N)` + any warnings.
- **`minutesMarkdown()` is overridden** so that when `#ai-minutes` is populated, Finalize
  publishes THAT markdown (the admin's reviewed/edited AI minutes); otherwise it returns the
  existing structured assembly. So the **existing Finalize** (`minutes_final=…`,
  `is_active=false`) publishes the AI minutes with zero new publish path.

No change to the team-facing pages; teams keep submitting notes as before.

## Data flow

```
MeeTeam admin: open meeting (team notes already submitted)
  page load -> GET localhost:8899/health  (button lights up if helper running)
Admin clicks "Generate with Meetily"
  -> GET /recordings -> pick/auto-match the Meetily app recording
  -> POST /generate {meeting_id (quorum), meetily_id, template}
       bridge runs: review.py --meetily-app <m> --meeting <q> -t <tpl> -o tmp.md
         review.py: quorum.fetch_notes(q) [team pre+during notes]
                  + meetily_app.get_transcript(m) [the recording's transcript]
                  + two-pass template generation
       -> {markdown, projects, warnings}
  -> fills #ai-minutes (editable) + preview in #d-body
Admin reviews/edits, clicks Finalize (existing)
  -> supa update meetings set minutes_final=<ai markdown>, is_active=false
MeeTeam History shows the AI minutes.
```

## Non-goals (deferred)
- No recording control from MeeTeam, no live transcript in MeeTeam (no app API — settled).
- No redirects/deep-links between the apps.
- No exposing the bridge beyond `127.0.0.1`; no auth (single admin, local).
- No change to `review.py`/`quorum.py`/`meetily_app.py` (bridge shells them).
- No new minutes storage — reuse `minutes_final` + Finalize.
- No hosted-MeeTeam→localhost bridging (admin runs MeeTeam locally via `run.command`; mixed
  content / private-network blocks make a hosted HTTPS page → http localhost unreliable — out
  of scope, documented as a requirement).

## Error handling
- **Bridge not running** → `/health` fails → AI button hidden/disabled with a clear hint; the
  structured minutes flow still works. Never a broken-looking page.
- **`/generate` failure** (missing transcript, no OpenAI key, bad meetily_id) → 500 with
  `review.py`'s stderr; MeeTeam shows the message and leaves the current minutes untouched
  (no wipe).
- **No recordings** → `/recordings` returns `[]`; the UI says "no Meetily recordings found".
- **CORS**: only the configured MeeTeam origin is allowed; a mismatched origin fails loudly in
  the console (documented so the admin sets `MEETEAM_ORIGIN` if they serve MeeTeam on another
  port).
- The bridge is read-only on the Meetily DB (via `meetily_app`) and only writes minutes
  through MeeTeam's own Finalize — it never mutates Supabase directly except via `review.py`'s
  existing, tested paths.

## Testing / check
- **`local/bridge.py` (pytest, offline):** `create_app()` factory; `/health` → 200 `{ok}`;
  `/recordings` via a stubbed `meetily_app.list_meetings`; `/generate` builds the right argv
  (`_generate_argv` pure) and, with `subprocess.run` stubbed to write the `-o` file, returns
  the markdown + parsed `projects`; a stubbed non-zero `review.py` → 500 with stderr and no
  partial result; the CORS header is present on responses and `OPTIONS` preflight returns the
  allow headers. No real review.py/OpenAI/Supabase/Meetily DB in unit tests.
- **MeeTeam:** `web/lib.js` has `lib.test.js` — if a title/date match helper is extracted into
  `lib.js`, unit-test it (given recordings + a meeting → best match). The DOM wiring
  (health-gate, button, textarea, `minutesMarkdown` override) is browser-verified.
- **Manual E2E:** start `run-bridge.command` + `run.command`; open a real meeting in MeeTeam
  admin minutes; Generate with Meetily; confirm the AI minutes (from a real recording's
  transcript + team notes) fill the editor; edit; Finalize; confirm History shows them.

## Config / migration
- No Supabase schema change. `.env` already has `OPENAI_API_KEY` + `SUPABASE_*` (Phases 2–4)
  and the bridge reads the Meetily DB read-only (Phase 6). `MEETILY_APP_DB` / `MEETEAM_ORIGIN`
  optional overrides.
- `config.js` gains `BRIDGE_URL`. `requirements-local.txt` already has flask.
- `run-bridge.command` added (mirrors `run-local.command`).

## Open items
- Bridge port (proposal `8899`) and whether to fold it into the Phase-5 `local/serve.py` (a
  second blueprint) vs. a separate file — separate `bridge.py` is cleaner; decide at
  implementation.
- The title/date match heuristic's exact rule (nearest date within N days, then title
  similarity) — tune during implementation; the admin can always override via the dropdown.
- Whether to show the AI minutes as a raw-markdown textarea only, or also keep the structured
  fields visible — default: AI textarea + live preview, structured fields hidden while AI
  minutes are active.
