# Meeting Models — Design

**Date:** 2026-07-06
**Status:** Approved (pending spec review)

## Problem

Today the app runs one workflow: each team's members submit their own pre-meeting
notes, files, and meeting notes; the admin reviews, presents, and exports. Some
meetings (e.g. VIP / executive meetings) need the admin to author everything
centrally without relying on members. We want the operating model to be selectable
per meeting.

## Models

Each meeting picks one model at creation (and editable anytime afterward):

- **Model 1 — Team self-serve** (`model = 'team'`, default): teams author their own
  content; admin reviews/presents/exports. Current behavior, unchanged.
- **Model 2 — Admin-run / VIP** (`model = 'admin'`): admin authors everything for all
  teams. The meeting is **hidden from members entirely** (they can't see or query it).
- **Model 3 — Hybrid** (`model = 'hybrid'`): teams submit AND the admin can edit/complete
  any team's content. Members see and participate as in Model 1.

Out of scope: Model 4 (live scribe / delegated live note-taking). Deferred.

## Core insight

There are only two underlying capabilities:
1. *Teams author their own content* — already exists.
2. *Admin can author any team's content* — new.

Every model is a combination of (1)/(2) plus member-visibility. Building capability (2)
once yields Models 2 and 3; the difference between them is only whether members can see
the meeting and whether they still submit.

## Data model

- Add column `meetings.model text not null default 'team'` with
  `check (model in ('team','admin','hybrid'))`. Adding the column with a default
  backfills existing rows to `'team'`, so current meetings and behavior are unaffected.

## Row-Level Security (DB migrations, admin-approved)

Mirrors the existing `admin writes teams` policy pattern (uses `is_admin()`).

1. **`admin writes notes`** — `for all to authenticated using (is_admin()) with check (is_admin())`
   on `public.notes`. Lets the admin author any team's pre-notes and meeting notes.
2. **`admin writes submissions`** — same shape on `public.submissions`. Lets the admin
   add/remove files and links for any team.
3. **Hide VIP from members** — replace the `read meetings` SELECT policy qual with
   `(model <> 'admin' OR is_admin())`. Members cannot query `admin`-model meetings;
   they disappear from members' meeting tabs and history. Admin still sees all.
4. **Storage** — verify the `submissions` bucket's `storage.objects` policies allow an
   admin to upload/delete in any team's path. If team-scoped, add an `is_admin()`
   exception. (To be confirmed against actual policies during implementation.)

Existing policies (`team rw notes`, `team rw submissions`, `admin read notes`,
`admin read submissions`) remain; the new admin-write policies are additive.

## Client changes

### `team.html` — reusable editor, now admin-on-behalf capable
- Read two optional URL params: `meeting` (which meeting) and `team` (which team).
- Effective team: if the user is admin **and** `team` is set, edit that team's content
  (`effectiveTeamId = team param`); otherwise `me.team_id` as today.
- Effective meeting: `meeting` param if present, else remembered `selectedMeeting()`
  (same pattern already used by present.html / minutes.html).
- When editing on behalf of a team, show a banner: *"Editing as **{Team}** · admin"*.
- All editors (pre-note, meeting notes), upload/link, and submit toggle operate on
  `effectiveTeamId` unchanged. Admin writes are permitted by the new RLS policy.

### `admin.html` — model selector + Edit action
- **Model dropdown** in the Meeting details card (Team self-serve / Admin-run · VIP /
  Hybrid), saved to `meetings.model`. Editable anytime.
- Meeting tabs show a small badge for non-`team` models (e.g. "VIP", "Hybrid") so the
  admin can tell them apart at a glance.
- Team rows / drawer: for `admin` and `hybrid` meetings, expose an **"Edit"** action
  that opens `team.html?meeting=<id>&team=<teamId>`. For `team` meetings, keep the
  current read-only **"View"** drawer.

### Unchanged
Present (incl. pre-flight checklist), Export→auto-archive, History, and the member
experience for `team`/`hybrid` meetings are untouched.

## Decisions (confirmed)

- Model is **editable anytime** from the meeting card, not only at creation.
- In hybrid, admin editing is **last-write-wins** over a member's submission (shared
  editor); the banner makes the acting-team explicit.
- Member visibility for VIP is enforced in **RLS**, not client filtering.

## Testing / verification

Verified via the existing headless-Chrome + CDP harness against the live project:
- Model column default: existing meetings read back as `'team'`.
- Admin-write RLS: as admin, upsert a note and insert a submission for a **non-own**
  team → succeeds; as a plain member, the same write for another team → blocked.
- VIP hidden: as a member, `openMeetings()` and history queries exclude `admin`-model
  meetings; as admin, they appear.
- Admin-on-behalf editing: `team.html?meeting=&team=` loads the target team, shows the
  banner, and saves notes/files to that team.
- Regression: a `team`-model meeting behaves exactly as before for members and admin.

## Rollout notes

- Remove `dev-login.html` and its hardcoded password before production (pre-existing
  item, unrelated but tracked).
