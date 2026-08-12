# Phase 2 — Quorum Integration (Supabase notes in, minutes out)

**Date:** 2026-08-04
**Status:** Design, awaiting approval
**Context:** Second sub-project of the MeeTeam/Quorum ↔ Meetily merge. Phase 1
(the local `review.py` engine) is done and merged. Phase 2 connects it to
Quorum's data so notes stop being hand-collected and the finished review lands
in Quorum's Minutes/History.

## Why

Today `review.py` reads pre-meeting notes from local `.docx`/`.pdf` files and
writes the review to a local `.md`. But Quorum already collects those notes:
each team submits `content` + files into the `submissions` table before a
meeting. And the finished review IS the meeting minutes, which Quorum stores in
`meetings.minutes_final` and shows in History. Phase 2 closes both seams:
Quorum's submissions become the review's input, and the review becomes the
meeting's minutes.

## Decisions (settled in brainstorming)

- **The Mac stays the hub.** Quorum is a static SPA + Supabase with no compute;
  whisper and the OpenAI key are local. So `review.py` runs locally and syncs
  with Supabase — it does NOT move into the browser or a server.
- **File-based draft → preview → publish.** No MeeTeam frontend changes. Generate
  writes a local `.md` (the admin's preview — and they may edit it to fix a
  dropped project or wording); a separate publish step pushes that file to
  `minutes_final` and archives the meeting. Preview happens on the Mac, where the
  admin already is.
- **Service-role key in `.env`.** The local script authenticates to Supabase with
  the `service_role` key (bypasses RLS, full read/write), kept in the gitignored
  `.env` beside `OPENAI_API_KEY`. Acceptable because it's the admin's own machine
  and the key is never committed.

## Quorum data model (confirmed against MeeTeam schema doc)

The pre-meeting notes TEXT and the pre-meeting FILES live in two different
tables — an important correction from the first draft:

- `notes` — `id`, `meeting_id`, `team_id`, **`pre_note text`** (the pre-meeting
  note → the GROUND-TRUTH text input), `content text` (during-meeting notes the
  admin would otherwise hand-assemble into minutes — NOT used as input; the
  review replaces it), `submitted bool`, `unique(meeting_id, team_id)`.
- `submissions` — `id`, `meeting_id`, `team_id`, `file_path`, `file_name`,
  `mime`, `url` (set when `mime='link'`), `created_at`. Pre-meeting FILES + LINKS.
  Files live in the private `submissions` storage bucket.
- `meetings` — `id`, `title`, `meeting_date`, `org`, `is_active` (false =
  archived to History), `minutes_final text` (the finished minutes markdown),
  `created_at`, `model` (`admin` = VIP). **The output target.**
- Finalizing in the app = `update meetings set minutes_final=…, is_active=false`.
  The publish step does exactly this.

So the review's ground-truth INPUT = every team's `notes.pre_note` for the
meeting, PLUS the text of each `submissions` file (downloaded + extracted) and
each link's URL. `teams.name` labels each team's block.

## Scope of Phase 2

Two new capabilities on the local tool. No changes to Phase 1's local-file flow —
it stays working.

### New module: `quorum.py`
Thin Supabase helpers, isolated so `review.py`'s core stays free of network I/O.
Uses the `supabase` Python client with `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
from the environment / `.env`.

- `fetch_notes(meeting_id: str) -> str` — read all `notes` rows for the meeting
  and collect each team's `pre_note` (labeled with `teams.name`); read all
  `submissions` rows, download each `file_path` from the `submissions` bucket and
  extract its text via the existing markitdown path, and include each link
  submission's `url`. Returns one combined ground-truth notes string (same shape
  `read_notes` produces), each piece under a `--- <team / file_name> ---` header.
- `publish_minutes(meeting_id: str, markdown: str) -> None` — `update meetings`
  set `minutes_final = markdown`, `is_active = false` where `id = meeting_id`.
- `_combine_inputs(pre_notes, file_texts, links) -> str` — the PURE assembly
  step (team pre_notes + extracted file texts + link URLs → one labeled string),
  unit-testable without network.

### `review.py` — two new modes (additive; existing CLI unchanged)
- `--meeting <id>` (generate from Quorum): notes come from
  `quorum.fetch_notes(<id>)` instead of (or in addition to) local note args. The
  recording is still the local audio positional; transcription + two-pass
  generation are unchanged; output is the local `.md` as today.
- `--publish <id> <review.md>` (publish mode): read the `.md`, call
  `quorum.publish_minutes(<id>, text)`, print confirmation. No recording needed
  in this mode.

Typical flow:
```
review.py --meeting <id> "Meeting.m4a"        # notes from Quorum -> local review .md
#   ...read/edit the .md: fix any dropped project, tweak wording...
review.py --publish <id> weekly_review_<date>.md   # push to minutes_final + archive
```

## Non-goals (deferred)
- No MeeTeam frontend changes (no in-app preview/edit) — that was the rejected
  heavier option.
- No auto-finalize — publish is always a deliberate second command.
- No moving compute off the Mac; no dropping Supabase — that is Phase 3.
- No recording upload to Supabase — the recording stays local.

## Config
- `.env` gains `SUPABASE_URL` (same value as the app's `config.js` `SUPA_URL`)
  and `SUPABASE_SERVICE_KEY` (the `service_role` key from Supabase → Settings →
  API). Both read from the environment; `.env` stays gitignored.
- `requirements.txt` gains `supabase`.

## Error handling
- Missing `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` in a Supabase mode → fail early
  with a clear message, before transcribing.
- `--meeting <id>` with no submissions → clear message (nothing to ground on),
  non-zero exit, no OpenAI spend.
- `--publish` of a missing/empty `.md`, or a meeting id that matches no row →
  clear message, non-zero exit, and do NOT archive.
- Publish is idempotent-ish: re-publishing overwrites `minutes_final`; if the
  meeting is already archived, still allow overwriting the minutes.

## Testing / check
- `_combine_inputs(pre_notes, file_texts, links)` — pure; unit-test that it
  merges team pre_notes + file text + link URLs with headers and handles empty
  inputs.
- A `--dry-run` on `--meeting` should print the assembled prompt WITHOUT
  publishing and (to avoid a live Supabase call in tests) is exercised with
  the fetch layer stubbed.
- Publish path: unit-test the payload builder / argument validation
  (meeting id + non-empty markdown required) with the network call stubbed.
- Manual end-to-end: generate for a real meeting id, eyeball the `.md`, publish,
  confirm it appears in Quorum History.

## Open items
- Whether to include only `submitted=true` `notes` rows, or all of them
  (default: all rows that have a non-empty `pre_note`).
- Whether `--meeting` should also accept extra local note files additively
  (low cost to allow; default: allow).
