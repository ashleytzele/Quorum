# Hosted Meeting App — Design Spec (v2, multi-team)

**Date:** 2026-07-03
**Status:** Draft for review
**Supersedes:** the local single-machine tool (`2026-07-03-meeting-minutes-app-design.md`), whose pure logic (`classifyFile`, `isAccepted`, `buildMinutesMarkdown`) and slideshow renderer are reused.

## Purpose

A hosted web app (one URL every team opens) where each team logs in, uploads its
files, and writes its own notes before a meeting. At the meeting the admin presents
the combined slideshow and exports one formal Minutes-of-Meeting (MoM) PDF for the
manager.

## Users & roles

- **Team member** — logs in, lands on their team's page, uploads files and writes
  notes for the active meeting. Can only see/edit their own team's data.
- **Admin** — creates the meeting, sees all teams and their submission status, runs
  the present view, and exports the combined MoM.
- **Manager** — receives the MoM PDF. (No login needed in v1.)

## Access & hosting

- **Frontend:** static HTML/CSS/JS (no build step), hosted free on Netlify or Vercel.
  Designed in claude.ai/design, integrated here.
- **Backend:** **Supabase** (managed) provides Auth, Postgres database, and file
  Storage. No custom server to write or maintain.
- **Libraries via CDN:** `@supabase/supabase-js`, `markdown-it`, `reveal.js`.

## The meeting lifecycle (async — v1)

1. **Admin** creates a meeting (title, date, org) → it becomes the *active* meeting.
2. **Before:** each team logs in, uploads files, writes notes for the active meeting.
   All async, any time before the meeting.
3. **At the meeting:** admin opens the **Present** view — the app pulls every team's
   files from Storage and builds one slideshow (one team title page, then a page per
   file, reusing the local tool's flat page-per-file layout).
4. **After:** admin opens **Minutes** — the app pulls every team's notes and fills the
   MoM template (Header · Team updates · Decisions), then prints to PDF for the manager.

Live co-editing during the meeting (real-time sync) is **v2**, not v1.

## Data model (Supabase)

Tables (Postgres):

- `teams` — `id uuid pk`, `name text unique`
- `profiles` — `id uuid pk → auth.users`, `team_id uuid → teams`, `role text default 'member'` (`'member'|'admin'`)
- `meetings` — `id uuid pk`, `title text`, `meeting_date date`, `org text`, `is_active bool default true`, `created_at timestamptz default now()`
- `notes` — `id uuid pk`, `meeting_id uuid → meetings`, `team_id uuid → teams`, `content text default ''`, `updated_at timestamptz default now()`, `unique(meeting_id, team_id)`
- `submissions` — `id uuid pk`, `meeting_id uuid → meetings`, `team_id uuid → teams`, `file_path text`, `file_name text`, `mime text`, `created_at timestamptz default now()`

Storage:

- One **private** bucket `submissions`. File path convention:
  `{meeting_id}/{team_id}/{filename}`.

Security (Row-Level Security — required, this is a multi-tenant app):

- A team member can read/write only rows where `team_id` = their `profiles.team_id`
  (notes, submissions), and can upload only into `.../{their team_id}/...` in Storage.
- Admin can read all teams' notes and submissions.
- All authenticated users can read `teams` and the active `meeting`.
- Exact policies are in the plan.

## Screens

1. **Login** — email magic-link (Supabase Auth). No passwords.
2. **Team dashboard** (member) — active meeting header; drag-drop/upload files
   (documents + pictures only); list of this team's uploaded files with remove;
   a notes editor with live Markdown preview; autosave.
3. **Admin dashboard** — meeting settings (title/date/org, create/activate); a table
   of teams showing files count + notes status; buttons: **Present**, **Export minutes**.
4. **Present** — the slideshow built from all teams' files (reused flat page-per-file
   deck; fullscreen; arrow keys).
5. **Minutes** — the combined MoM rendered from all teams' notes; **Print / Save PDF**.

## Reused from the local tool

- Pure functions `classifyFile`, `isAccepted`, `buildMinutesMarkdown` (already tested).
- The slideshow rendering approach (one page per file; images inline; PDFs embedded;
  docx as a link) — adapted to read files from Supabase Storage URLs instead of a
  local folder.
- The "documents + pictures only" acceptance rule.
- The "No updates this week" empty-note fallback in the minutes.

## Out of scope for v1 (later)

- Real-time live co-editing during the meeting.
- AI note summarization.
- DOCX export (PDF only).
- Manager login / a manager portal.
- Per-meeting history browsing UI (data is kept; no browse screen yet).
- Team self-signup / org management (teams + admin are seeded by hand in v1).

## Assumptions to confirm

- **Supabase** is acceptable (third-party managed cloud; free tier). — *assumed yes*
- **Async before-meeting** for v1; live editing is v2. — *assumed yes*
- **One combined MoM** exported by the admin. — *assumed yes*
- Teams and the admin are **seeded manually** in Supabase for v1 (no self-signup). — *assumed yes*
- Frontend is **plain HTML/CSS/JS** (no React) to match the project and keep zero build. — *assumed yes*
