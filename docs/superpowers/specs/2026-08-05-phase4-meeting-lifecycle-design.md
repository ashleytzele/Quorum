# Phase 4 — Meeting lifecycle (the spine)

**Date:** 2026-08-05
**Status:** Design, approved (awaiting spec review)
**Context:** Fourth sub-project of the MeeTeam/Quorum ↔ Meetily merge. Phases 1–3 built the
pieces (review engine; Supabase notes-in/minutes-out; audio capture + template selection).
Each stage of a meeting works, but a meeting is still a *thin record* (title, notes,
minutes) with no notion of *process* — so the flow feels disconnected: the handoff lives in
the terminal, no screen shows a meeting's whole state, and two MeeTeam features
(during-meeting notes, VIP authoring) don't connect to the pipeline. Phase 4 makes the
meeting a **lifecycle object** with an explicit status, turning MeeTeam into the dashboard
and Meetily into the worker that reports progress back.

This phase touches both repos (meetily + MeeTeam) and adds one Supabase column.

## Why

The four gaps the user named all trace to one root cause — the meeting has no status:
1. **Handoff/trigger** — going from a MeeTeam meeting to minutes means leaving the app,
   copying the meeting id, and running two Mac commands.
2. **No overview** — nothing shows notes-in / recorded / drafted / published in one place.
3. **Live notes / Present unused** — teams' during-meeting notes (`notes.content`) are
   ignored by the AI minutes.
4. **VIP / solo** — the admin-authors-everything path was never defined for the pipeline.

One explicit `status` field, written by whichever tool owns each stage, closes all four.

## Decisions (settled in brainstorming)

- **Dashboard + command-hint depth (NOT a daemon).** The browser has no compute and can't
  reach the Mac, and the recording is local. So there is **no** in-app "Generate" button and
  **no** `--watch` worker. Instead: MeeTeam shows each meeting's live status and the exact
  `./review.py --meeting <id> <recording>` command (id pre-filled, copyable); the admin still
  runs it on the Mac. Cheap, no long-running process.
- **During-meeting notes feed the minutes.** `fetch_notes` additionally pulls each team's
  `notes.content` as ground-truth input alongside `notes.pre_note`. Captures typed
  decisions/action-items that audio garbles.
- **VIP uses the same pipeline, minus the team-collection stage.** VIP content is authored
  through the same `team.html` editor (embedded as an iframe in `admin.html`), so it is
  already a `notes` row and `fetch_notes` reads it with no special-casing. The only
  lifecycle difference is VIP skips `collecting` (setup → ready).
- **The draft stays local.** Generation writes the `.md` on the Mac (previewed/edited there,
  as today); it is NOT uploaded. `draft` status just means "a draft exists on the admin's
  Mac, pending publish."

## Data model change

One new column on `meetings`:

```sql
alter table meetings add column status text default 'setup';
```

Adding a column with a default backfills existing rows to `'setup'`; a one-time reclassify
gives them a truthful state (see Config/migration). Six states and who advances each:

| Status | Meaning | Advanced by |
|--------|---------|-------------|
| `setup` | created, being configured | MeeTeam — on insert |
| `collecting` | teams submitting pre-notes + files (Team meetings) | MeeTeam — admin "Open for submissions" (or on first save of a Team meeting) |
| `ready` | notes in, awaiting recording + generate | MeeTeam — admin "Ready to record"; VIP jumps here from `setup` |
| `processing` | the Mac is generating | Meetily — at `--meeting` generate start |
| `draft` | draft minutes on the admin's Mac, awaiting publish | Meetily — on generate success |
| `published` | `minutes_final` set, `is_active=false`, in History | Meetily — on `--publish` |

Transitions:
- MeeTeam (admin.html): `setup → collecting` (open submissions), `collecting → ready`
  (ready to record), `ready → collecting` (reopen). VIP: `setup → ready` directly.
- Meetily: `(any) → processing → draft` during a `--meeting` generate; `draft → published`
  on `--publish`. The Mac's writes are authoritative for its three states and may advance
  from whatever the current status was (e.g. a re-generate goes `published`? no — see below).
- **Guard:** a `--publish` always sets `published`. A `--meeting` generate sets
  `processing`/`draft` regardless of prior state (re-running on an already-published meeting
  is allowed and returns it to `draft` until re-published — consistent with Phase 2's
  "re-publishing overwrites").

`is_active` and `minutes_final` remain the source of truth for archive/History (Phase 2
unchanged); `status` is the finer-grained lifecycle layered on top. `published` ⇔
`is_active=false` with `minutes_final` set.

## Scope

### A. Supabase
- Add `meetings.status text default 'setup'` + the one-time reclassify (Config/migration).
- Extend `docs/supabase-phase3.sql` lineage with a `docs/supabase-phase4.sql` for the record.

### B. Meetily (the worker) — `quorum.py` + `review.py`
- **`fetch_notes` also reads `notes.content`.** For each notes row, emit the team's
  `pre_note` (as today, `--- <team> (pre-meeting note) ---`) AND, when non-empty, its
  `content` under `--- <team> (during-meeting note) ---`. Select `pre_note, content,
  teams(name)`. `_combine_inputs` already drops blanks; extend its `pre_notes` handling or
  add a parallel `during_notes` list — the combined string keeps the same shape.
- **Relax the empty-notes guard.** `fetch_notes` currently `sys.exit`s when the combined
  input is empty. Change: when empty, print a clear WARNING to stderr and return `""` (do
  NOT exit) — so a recording-only or VIP-no-notes meeting generates from the transcript
  alone. `review.py --meeting` already folds Quorum notes additively with local notes and
  passes notes to `build_prompt`, which tolerates empty notes (Phase 1 behavior).
- **`quorum.set_meeting_status(meeting_id, status) -> list`** — `update meetings set
  status=<status> where id=<id>`; returns updated rows. No-op-safe.
- **`quorum.publish_minutes`** additionally sets `status='published'` alongside the existing
  `minutes_final` + `is_active=false` update (one statement).
- **`review.py --meeting` status writes (best-effort).** At generate start (right after the
  Quorum fetch, before `transcribe()`), set `processing`; after the `.md` is written, set
  `draft`. Both wrapped like the Phase-3 auto-sync: `try/except`, warn on failure, never
  block generation. Thin `_set_status_via_quorum(id, status)` wrapper is the test stub point.
  Skipped in `--dry-run` and when `--meeting` is absent (local-file mode writes no status).

### C. MeeTeam (the dashboard) — `web/lib.js`, `web/admin.html`, `web/styles.css`, `lib.test.js`
- **Generalize the status helper.** Replace Phase-3's two-state `minutesStatus(m)` with
  `meetingStatus(m) -> { key, label, cls }` covering all six states. Read `m.status`; if
  absent (un-migrated row), derive: `!is_active` → published; non-empty `minutes_final` →
  draft; else `collecting`. Keep it in `web/lib.js`, unit-tested in `lib.test.js` for each
  state + the derive fallback. Update the badge call site in `admin.html` `renderTabs` to use
  `meetingStatus`. (`history.html` may adopt it too — optional, its meetings are all
  `published`.)
- **Status pill styling.** Extend `web/styles.css` `.mt-status-*` (Phase 3 added `-ready` /
  `-pending`) to the six `cls` values, reusing existing OKLCH tokens (`--ok`/`--ok-50`
  green for published; `--accent-*` for processing/draft; `--muted-bg`/`--text-2` for
  setup/collecting/ready), theme-aware.
- **Handoff command card.** In the admin meeting detail, when the selected meeting's status
  is `setup`/`collecting`/`ready` (i.e. not yet processed), show a small card with: the
  meeting id, the exact command `./review.py --meeting <id> <recording>`, and a **Copy**
  button (copies the command). Hidden for `processing`/`draft`/`published`.
- **Status controls.** A single primary action button whose label + target depends on the
  current status: `setup → "Open for submissions"` (→collecting), `collecting → "Ready to
  record"` (→ready), `ready → "Reopen"` (→collecting). VIP (`model==='admin'`) offers
  `setup → "Ready to record"` (→ready). The Mac-owned states (`processing`/`draft`/
  `published`) show no control (status is informational there). Writing status =
  `supa.from('meetings').update({ status }).eq('id', mId)`, mirroring the existing
  archive-button pattern.
- **During-meeting notes UI unchanged** — `team.html` already writes `notes.content`; no
  edit needed there (the value now simply flows into the minutes via B).

## Data flow (end to end, Team meeting)

```
MeeTeam: create meeting (status=setup) -> "Open for submissions" (collecting)
Teams: submit pre_note + files; during the meeting, type notes.content        (collecting)
MeeTeam: admin "Ready to record" (ready)  -- shows: ./review.py --meeting <id> <rec>
Mac: ./record.sh -> recording
Mac: ./review.py --meeting <id> <rec>
        status=processing
        fetch_notes(id): pre_note + content (per team) + submission files/links
        transcribe -> two-pass generate (meeting's template) -> weekly_review_<date>.md
        status=draft
...admin previews/edits the .md on the Mac...
Mac: ./review.py --publish <id> <file>.md
        minutes_final set, is_active=false, status=published
MeeTeam: dashboard shows "Published"; History shows the meeting.
```

VIP: create (setup) → "Ready to record" (ready) → same Mac flow. VIP content is the admin's
own `notes` row (authored via the embedded `team.html`), read by `fetch_notes` like any team.

## Non-goals (deferred)

- No Mac daemon / `--watch`; no in-app "Generate" button (compute stays Mac-initiated).
- No uploading the draft `.md` to Supabase — the draft is previewed/edited locally.
- No Present-mode changes; no live transcript.
- No new recording entity in Supabase; recordings stay local.
- No auto-advance of `collecting → ready` on a timer or submission-count — the admin decides.

## Error handling

- All Meetily status writes are **best-effort**: `try/except`, warn to stderr, never block a
  generate or publish. A Supabase hiccup must not cost the admin their minutes.
- `fetch_notes` empty input no longer exits — it warns and returns `""` (recording-only path).
  `--publish` still refuses empty markdown and a no-match meeting id (Phase 2 unchanged).
- `meetingStatus` on an unknown/absent status value falls back to the derive rule, never
  throws; the pill always renders something sane.
- Status controls: a failed `update` surfaces the same way the existing admin autosave does;
  no partial-state corruption (status is a single column write).

## Testing / check

- **Meetily (pytest, offline):**
  - `fetch_notes` now includes `content`: unit-test `_combine_inputs` (or its extension) with
    pre_note + content + files + links, asserting both note headers appear and blanks drop.
  - Empty-notes relaxation: `fetch_notes` with no notes/submissions returns `""` and warns
    (does not `SystemExit`) — network stubbed.
  - `quorum.set_meeting_status` payload/no-op guard (network stubbed).
  - `review.py --meeting` sets `processing` then `draft` via the `_set_status_via_quorum`
    stub (assert the two calls, in order); `--dry-run` and local-file mode set no status;
    a status-write failure does not abort the generate.
  - `publish_minutes` includes `status='published'` in its update payload.
  - Phase 1–3 suites stay green.
- **MeeTeam (`node --test lib.test.js`):**
  - `meetingStatus` returns the right `{label,cls}` for all six explicit states and for the
    three derive-fallback cases (no status + archived / + minutes / + neither).
- **Manual E2E:** run the SQL; walk a Team meeting through the full lifecycle (open → collect
  → ready → generate → publish) and a VIP meeting (setup → ready → generate → publish),
  confirming the pill and command card reflect each stage and the during-meeting `content`
  appears in the generated minutes.

## Config / migration

- One-time Supabase SQL (`docs/supabase-phase4.sql`), run in the dashboard:
  ```sql
  alter table meetings add column if not exists status text default 'setup';
  update meetings set status = case
      when is_active = false then 'published'
      when minutes_final is not null and minutes_final <> '' then 'draft'
      else 'collecting'
    end;
  ```
- No `.env` change (Phase 2 Supabase creds already present).
- No new dependency.

## Open items

- Whether a Team meeting should auto-enter `collecting` on first save, or require the "Open
  for submissions" click (default: require the click — explicit, one button).
- Exact copy/wording of the pill labels and the command-card ("Generate minutes" vs
  "Record & generate") — cosmetic, decide during MeeTeam implementation.
- Whether `history.html` adopts `meetingStatus` (all its meetings are `published`, so low
  value) — optional.
