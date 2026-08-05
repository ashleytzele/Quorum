# Phase 3 — Audio-first capture + template selection in the UI

**Date:** 2026-08-05
**Status:** Design, approved (awaiting spec review)
**Context:** Third sub-project of the MeeTeam/Quorum ↔ Meetily merge. Phase 1 (local
review engine) and Phase 2 (Supabase notes in, minutes out) are done and merged.
Supabase **stays** — an earlier "go fully local" idea was rejected. Phase 3 makes the
tool usable for **online meetings** (record any Zoom/Meet/Teams call), and surfaces
**template choice** and **minutes status** in the MeeTeam UI so the admin picks the
output format when creating a meeting instead of via a terminal flag.

This is the **first phase that touches the MeeTeam repo** (`~/Desktop/Github/MeeTeam`,
a static SPA + Supabase) and adds Supabase schema.

## Why

- Meetings are increasingly online. The pipeline only needs an audio *file*; it does
  not care in-person vs. online. What was missing is a repeatable way to capture an
  online call's audio — **both sides** — into one file.
- "Weekly vs interview" (which output template) was a terminal flag (`-t`). The admin
  who creates the meeting in MeeTeam should choose it there; the pipeline should honor
  it automatically. And rather than hardcode two options, the dropdown should reflect
  **every** template that exists in the meetily repo, so new templates need no UI edit.
- The admin should see, per meeting, whether its minutes have been produced yet.

## Decisions (settled in brainstorming)

- **Audio-first, no live transcript.** Real-time/streaming transcription is explicitly
  out — chunked whisper is less accurate (worse for the accented/manglish case) and
  the meeting platforms already provide live captions. Record, then process.
- **Recording stays Mac-driven.** MeeTeam is a static site + Supabase with **no
  compute**; whisper and OpenAI run on the Mac. A browser "Generate" button would need
  a Mac-watches-Supabase bridge — rejected as out of scope. The UI holds *configuration*
  (template) and *displays results* (status); it does not trigger compute.
- **Template registry is a synced convenience mirror.** Template JSON files on the Mac
  remain the source of truth. A small Supabase `templates` table mirrors their
  stem/name/description so the browser dropdown can list them. The Mac syncs it.
- **"Recording status" = minutes status.** The only thing the cloud can truthfully know
  without a Mac→Supabase heartbeat is whether minutes were published. So status is
  derived from existing fields (`minutes_final`, `is_active`): "Awaiting minutes" vs
  "Minutes ready". No new status column, no heartbeat. A distinct live
  "recording/processing now" state was considered and deferred.

## Scope

Three areas. Each part is additive; existing flows keep working.

### A. `record.sh` — capture an online meeting to a file (meetily repo, Mac)

A small shell script. Records the macOS **Aggregate Device** via ffmpeg avfoundation
to a timestamped file, prints the next command.

- Resolve the Aggregate device's ffmpeg **index by name at runtime** (avfoundation
  indices shift between reboots/device changes) by parsing
  `ffmpeg -f avfoundation -list_devices true -i ""`. Device name is configurable via an
  env var / a constant at the top (default `Aggregate Device`); error clearly if not
  found, listing the audio devices seen.
- `ffmpeg -f avfoundation -i ":<idx>"` → `recordings/meeting_<YYYY-MM-DD_HHMMSS>.m4a`
  (AAC, keep source channels — downmix happens later in `retranscribe.sh`, which already
  does `-ar 16000 -ac 1`). `Ctrl-C` stops cleanly (ffmpeg finalizes the file on SIGINT).
- On stop, print the produced path and the exact next command, e.g.
  `./review.py --meeting <id> recordings/meeting_<ts>.m4a`.
- `recordings/` is created if missing; `*.m4a` is already gitignored.
- **No change** to `review.py` / `retranscribe.sh` for this part — they already accept
  any ffmpeg-readable file and downmix to 16 kHz mono for whisper.

**One-time manual setup (documented in README; verified together, not scripted):**
In **Audio MIDI Setup**, build:
1. a **Multi-Output Device** = `VB-Cable` + your headphones — set the meeting app's (or
   system) *output* to it, so the far-end audio goes into VB-Cable **and** you still hear it;
2. an **Aggregate Device** = `VB-Cable` + your **Microphone** — this is what `record.sh`
   records, so one file carries both the far-end and your voice.
The existing Aggregate Device reports only 2 input channels, which suggests it is *not*
currently combining VB-Cable + mic; it will be rebuilt. A **15-second test recording**
(talk while a clip plays) run through `review.py --dry-run` confirms both voices appear
in the transcript before the setup is trusted on a real meeting.

### B. Template registry + selection (spans meetily, Supabase, MeeTeam)

**Supabase — new table:**
```
templates (
  stem        text primary key,   -- filename without .json, e.g. 'weekly_review'
  name        text not null,       -- from the JSON's "name" field, e.g. 'Weekly Review v2'
  description text,                 -- from the JSON's "description" field (may be long)
  updated_at  timestamptz default now()
)
```
Read-access for authenticated users (dropdown). Write is service-role only (the Mac
sync). RLS consistent with the rest of the app; the exact policy is an implementation
detail (mirror how `meetings`/`notes` are secured).

**Supabase — new column on `meetings`:**
```
alter table meetings add column template text;   -- the chosen stem; null = default
```
Null/absent template → the pipeline default (`weekly_review`). No backfill needed;
existing meetings behave as before.

**meetily — `review.py --sync-templates` (+ a helper in `quorum.py`):**
- New mode `review.py --sync-templates`: scan local `*.json` templates (the same files
  `-t` accepts — a template is a JSON with top-level `name` + `sections`), read each
  one's `stem`/`name`/`description`, and **upsert** them into `templates` via a new
  `quorum.sync_templates(rows) -> list`. Requires the Supabase env like other Supabase
  modes; needs no OpenAI key. Prints how many were synced.
- The same upsert runs automatically at the start of each `--meeting` **generate** (best
  effort — a sync failure warns but does not block generation), so the registry never
  goes stale.
- `quorum.get_meeting(id)` (or extend the existing fetch) returns the meeting row so
  `review.py` can read its `template` stem.

**meetily — template resolution in `review.py --meeting <id>`:**
- Precedence: explicit `-t` flag **wins** (override); else the meeting's `template`
  stem → `<stem>.json`; else the existing `DEFAULT_TEMPLATE` (`weekly_review.json`).
- If the resolved `<stem>.json` does not exist locally → exit with a clear message that
  lists the available template stems (the Mac's files are the source of truth; a meeting
  can point at a stem whose file was deleted).
- Local-file mode (no `--meeting`) is **unchanged** — `-t` / default as today.

**MeeTeam — `web/admin.html`:**
- A **Template `<select>`** (`id="m-template"`) beside the existing Model select
  (`m-model`, line ~82), bound as `fTemplate = getElementById('m-template')` (mirrors
  `fModel`, line ~221). Populate its options on load from
  `supa.from('templates').select('stem,name').order('name')` — option label = `name`,
  value = `stem`. Include a blank/"Default (weekly)" option mapping to null.
- Add `template: fTemplate.value || null` to the `payload` (line ~300) and to the
  autosave input listener list (line ~306). Set `fTemplate.value` when a meeting loads
  (near line ~265, beside `fModel`/`fOrg`).
- Follows the existing debounce-autosave pattern exactly; no new save mechanism.

### C. Minutes-status badge (MeeTeam, read-only)

In the meeting-tab render in `web/admin.html` (~line 247–252, beside the existing
`modelBadge`), add a status pill derived from existing fields:
- `minutes_final` empty/null **and** `is_active` true → **"Awaiting minutes"** (muted).
- `minutes_final` non-empty → **"Minutes ready"** (accent/positive).
Pure presentation from data already loaded; no query change, no schema change. History
view already lists archived meetings, so no change needed there.

## Data flow (generate, online meeting, end to end)

```
[Zoom/Meet/Teams] --audio--> Multi-Output(VB-Cable+headphones) --> you hear it
                                     |
                              VB-Cable (far end)
                                     +  Mic (you)   == Aggregate Device
                                     |
   ./record.sh  --ffmpeg--> recordings/meeting_<ts>.m4a
                                     |
   admin picks Template in MeeTeam ----> meetings.template = '<stem>'  (Supabase)
                                     |
   ./review.py --meeting <id> recordings/meeting_<ts>.m4a
        - auto-upsert templates registry (best effort)
        - fetch_notes(id)  (Phase 2)         -> ground-truth notes
        - read meetings.template -> <stem>.json   (or -t override / default)
        - transcribe(file) -> transcript
        - two-pass generate -> weekly_review_<date>.md   (local preview)
   ...admin eyeballs/edits the .md...
   ./review.py --publish <id> <file>.md  -> minutes_final set, is_active=false (Phase 2)
                                     |
   MeeTeam admin tab shows "Minutes ready"; History shows the meeting.
```

## Non-goals (deferred)

- Live / streaming transcript in any surface.
- Browser-triggered recording or generation (no compute bridge).
- A distinct "recording in progress / processing" status (needs a Mac→Supabase
  heartbeat) — only "minutes status" is shown.
- Uploading recordings to Supabase — recordings stay local.
- Auto-detecting a call has started / auto-record.
- Per-template schema editing in the browser — templates are authored as JSON on the Mac.

## Error handling

- `record.sh`: Aggregate device name not found → list the avfoundation audio devices and
  exit non-zero. `recordings/` missing → create it. ffmpeg missing → clear message.
- `--sync-templates`: missing Supabase env → same early failure as other Supabase modes.
  A malformed template JSON (no `name`) → skip it with a warning, sync the rest.
- Auto-sync inside `--meeting` generate: failure **warns and continues** (never blocks a
  generate over a registry hiccup).
- `--meeting` with a `template` stem whose `<stem>.json` is absent → exit non-zero,
  listing available stems. Never silently fall back to the default in that case.
- MeeTeam dropdown: `templates` empty or fetch fails → the select still offers "Default
  (weekly)"; the app never hard-breaks over an empty registry.

## Testing / check

- **meetily (pytest, offline):**
  - Template resolution precedence: `-t` override > meeting `template` stem > default;
    unknown stem → SystemExit listing valid stems. Pure function, unit-tested.
  - `quorum.sync_templates` payload builder (stem/name/description rows from parsed
    JSONs) — pure assembly, unit-tested with the network stubbed (same pattern as Phase
    2's `_combine_inputs`).
  - `--sync-templates` and the auto-sync-on-generate wiring exercised via the existing
    stub seams (`_fetch_via_quorum`-style indirection), no live Supabase.
  - Phase 1 + Phase 2 suites stay green.
- **record.sh:** a `--list`/dry mode or a shellcheck-clean script with a documented
  manual 15-second capture test (both-voices-in-transcript) — the audio path is verified
  by the manual test, not automated.
- **MeeTeam:** `web/lib.js` has `lib.test.js`; add a unit test for the status-badge
  helper (given `{minutes_final, is_active}` → label) if the logic is extracted into
  `lib.js`. Dropdown population + payload wiring verified manually in the browser.
- **Manual E2E:** record a short real online call → pick a template in MeeTeam →
  `review.py --meeting <id> <file>` → confirm the right template was used and status
  flips to "Minutes ready".

## Config / migration

- `.env` already has `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (Phase 2).
- One-time Supabase (dashboard SQL, provided at implementation): create `templates`
  table + policies; `alter table meetings add column template text`.
- One-time macOS: build the Multi-Output + Aggregate devices (manual, documented).
- `record.sh` device name overridable via env/constant.

## Open items

- Exact RLS policy wording for `templates` (mirror existing tables at implementation).
- Whether the blank dropdown option reads "Default (weekly)" or "— none —"; cosmetic,
  decide during MeeTeam implementation.
