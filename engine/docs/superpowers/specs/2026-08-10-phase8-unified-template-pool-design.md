# Phase 8 — Unified template pool (include the Meetily app's templates)

**Date:** 2026-08-10
**Status:** Design, approved (awaiting spec review)
**Context:** The official Meetily desktop app ships a set of meeting-note templates (Daily
Standup, Project Sync, Psychiatric Session Note (SOAP+AI Hybrid), Retrospective, Client/Sales
Meeting, Standard Meeting Notes, Weekly Progress Review). Verified on disk: they use the
**exact same JSON schema as our own templates** (`{name, description, sections:[{title,
instruction, format, item_format?}]}`), so `review.py` can drive them unchanged. The user
wants all of them selectable in MeeTeam and used to generate the minutes. This phase widens
`review.py`'s template *source* to the union of our repo templates + the Meetily app's
template folders. MeeTeam needs no change — it already lists whatever `--sync-templates`
uploads and stores the chosen stem.

## Why

Today the template pool is only our two repo templates (`weekly_review`, `interview_review`,
marked `registry:true`). The Meetily app has 7 more, same format, that the user already knows
and wants — Daily Standup, Retrospective, a clinical SOAP note, etc. Since the schemas match,
"including them" is just teaching `review.py` two more folders to read templates from.

## Confirmed on disk

- **Our repo templates** (source of truth for the pipeline): `weekly_review.json`,
  `interview_review.json` — carry `registry:true` (the Phase-3 marker that keeps repo cruft
  out of the sync).
- **Meetily app BUNDLED** (`/Applications/meetily.app/Contents/Resources/templates/*.json`):
  `daily_standup`, `project_sync`, `psychatric_session` (sic), `retrospective`,
  `sales_marketing_client_call`, `standard_meeting` — 6 files, all `name`+`sections`,
  schema-compatible (some use `item_format`/`example_item_format`, which `build_prompt`
  already tolerates/ignores).
- **Meetily app USER** (`~/Library/Application Support/meetily/templates/*.json`):
  `weekly_progress_review` (+ any the user creates in the app).
- No stem collisions across the three sources.

## Decisions

- **Union of three sources**, deduped by stem, with **precedence repo > user > bundled** (a
  repo template wins if a stem ever clashes — our curated ones stay authoritative).
- **The `registry:true` marker gate applies ONLY to the repo folder** (to keep repo cruft
  out). The Meetily app folders are curated, so **every** valid `name`+`sections` JSON there
  is included — no marker required.
- **App folders are env-overridable and optional.** Missing folder (app not installed, or a
  different install path) → that source contributes nothing; it never errors. Defaults:
  `MEETILY_APP_TEMPLATES` (bundled) = the `/Applications/meetily.app/.../templates` path;
  `MEETILY_APP_USER_TEMPLATES` = `~/Library/Application Support/meetily/templates`.
- **MeeTeam is untouched.** Its dropdown reads the synced `templates` table; once the union
  is uploaded, all 9 appear. Selecting one stores its stem on `meetings.template` (Phase 3),
  and `review.py --meeting` resolves that stem from whichever folder holds it.
- **Read-only on the app's files** — the app bundle and its template dir are only ever read.

## Scope (meetily repo only)

`review.py` gains a small template-source layer (or a tiny `templates.py` helper — decide in
the plan); no changes to `quorum.py`, `meetily_app.py`, `local/`, or MeeTeam.

- **`_template_dirs() -> list[(dir, requires_marker)]`** — the ordered sources: the repo dir
  (`requires_marker=True`), the app user dir, the app bundled dir (both `False`). Skips dirs
  that don't exist.
- **`all_templates() -> list[dict]`** — scan each source's `*.json`; for each valid
  `name`+`sections` object, include `{stem, name, description}` — but from the repo dir only
  those with `registry` truthy. Dedupe by `stem`, first source wins (repo > user > bundled).
- **`--sync-templates`** uploads `all_templates()` to Supabase (was: repo-only). MeeTeam
  dropdown then lists all 9.
- **`resolve_template(explicit, meeting_template, ...)`** — when resolving a `meeting_template`
  stem, search the same ordered sources for `<stem>.json` and return the first hit; unknown
  stem → the existing clear error, now listing stems from all sources.
- **The auto-sync on `--meeting` generate** (Phase 4) uses `all_templates()` too, so the
  registry stays current as the user adds app templates.

## Non-goals (deferred)
- No MeeTeam frontend change (dropdown already reads the registry).
- No editing/creating templates from our tools — authoring stays in the app or by hand.
- No converting the app's own summaries; we only borrow its template *definitions*.
- No writing to the app's template folders (read-only).
- No two-pass `enumerate` added to the app templates — they generate single-pass (only
  `weekly_review` opts into two-pass via its `enumerate` key; unchanged).

## Error handling
- A source folder that doesn't exist is silently skipped (app not installed / moved).
- A malformed JSON in any folder is skipped with a stderr warning (as today).
- `resolve_template` on a stem present in none of the folders → `SystemExit` listing the
  available stems across all sources (so the user sees the full pool).
- `--sync-templates` with an empty union (no valid templates anywhere) → prints `synced 0`,
  exits 0.

## Testing / check
- **pytest, offline (extend `test_review.py`):**
  - `all_templates()` with tmp dirs: repo dir contributes only `registry:true` files; app
    dirs contribute all valid ones; dedupe-by-stem precedence repo > user > bundled; missing
    dir skipped; malformed JSON skipped.
  - `resolve_template` finds a stem that lives only in an app dir; unknown stem → SystemExit
    listing all stems.
  - `--sync-templates` uploads the union (via the existing `_sync_templates_via_quorum` stub).
  - Phase 1–7 tests stay green; existing `_read_template_meta` behavior (repo marker) preserved.
- **Manual E2E:** `./review.py --sync-templates` → the Supabase `templates` table (and thus
  MeeTeam's dropdown) lists all 9; pick "Retrospective (Agile)" on a meeting and generate →
  the minutes follow that template's sections.

## Config / migration
- No schema change (the `templates` table + `meetings.template` already exist). No new
  dependency. `.env` unchanged. Optional `MEETILY_APP_TEMPLATES` / `MEETILY_APP_USER_TEMPLATES`
  overrides.

## Open items
- Whether the repo `registry` marker rule should also relax now that the root is tidy
  (default: keep it — cheap safety against future stray repo JSONs).
- Filename typo `psychatric_session.json` is the app's own; we surface it by the template's
  `name` ("Psychiatric Session Note …"), so the stem typo is cosmetic.
