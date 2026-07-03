# Meeting Minutes App — Design Spec

**Date:** 2026-07-03
**Status:** Draft for review

## Purpose

An **admin-only, single-machine web app** to run recurring team meetings. It turns
short context notes submitted by each team into a presentable slideshow, lets the
admin capture notes live during the meeting, and produces a formal Minutes-of-Meeting
(MoM) PDF for the manager afterward.

The app runs on the one meeting laptop. There is no remote viewing, no login, no server, no database.

## Users

- **Admin (primary):** one facilitator who runs the app during the meeting.
- **Teams / department admins:** submit a short context note per project before the
  meeting (a file dropped in a folder). Their during-meeting updates are captured by
  the admin in the app.
- **Manager:** receives the MoM PDF after.

## The flow

### BEFORE — Slideshow from submitted notes
- Each team submits one or more files of **any type** (doc, text, image, PDF) into its
  own subfolder under `team/`.
- Admin opens the app, picks the `team/` folder (native folder input), and the app
  compiles the submissions into a **reveal.js slideshow** — one section per team,
  `---` splits slides within a Markdown/text file.
- The team list is **editable**: a team is just a subfolder, so adding/renaming a
  folder adds/renames a team. No in-app team management to build.
- Admin presents fullscreen. Manager sees where each team stands.
- Projects with visual artifacts (a live website, a chart flow) are screen-shared
  separately by the team — **out of scope for this app**.

### DURING — Note capture
- A capture pane with one section per team.
- Admin types short notes as discussion happens; a live preview shows the formatted
  result.

### AFTER — Formal Minutes of Meeting
- One click arranges the captured notes into a fixed **MoM template**.
- **Manual fill, no AI** — notes are short and some projects have none, so there is
  nothing meaningful to summarize automatically. The admin tidies wording by hand.
- Empty sections render as **"No updates this week"** rather than breaking.
- Export via native `window.print()` → **PDF**, styled formally by print CSS.

## Data model — just files

```
team/
  Solution-Consultant/
    update.docx          ← rendered as a clickable filename
    screenshot.png       ← rendered inline
  Tech/
    notes.md             ← rendered inline
  R&D/
    roadmap.pdf          ← embedded inline
```

- Read with a native folder input (`<input type="file" webkitdirectory>`), so the app
  works by double-clicking `index.html` — no server, no secure-context requirement.
- **Rendering by file type:**
  - Markdown / text (`.md`, `.txt`) → rendered inline via `markdown-it`.
  - Images (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`) → shown inline.
  - PDF (`.pdf`) → embedded inline (`<embed>`), viewable in the slideshow.
  - Anything else (`.docx`, `.xlsx`, …) → a clickable filename that opens in the OS.
    The app does not build a document viewer for these.
- The generated MoM can be saved by the admin as a `.md`/PDF via the browser; the app
  does not manage a meetings archive in v1.

## MoM template sections

1. **Header** — organization, meeting title, date
2. **Team updates** — one block per Team 
3. **Decisions**.


## Stack — build on existing pieces, not from zero

- **`reveal.js`** — slideshow generation and present mode. Team Markdown is injected
  inline as `<section data-markdown>` (read as text, not fetched) so it works from a
  local folder without a server.
- **`markdown-it`** — renders the live preview of during-notes and project briefs.
- **Vanilla JS**, no framework, no build step.
- **One CSS file** with two modes: on-screen theme + a formal `@media print` style for
  the PDF.

Delivery: a single `index.html` plus `reveal.js`, `markdown-it`, and `style.css`,
opened directly in **Chrome or Edge**.

## Explicitly out of scope for v1 (add when actually needed)

- AI summarization / "polish" of notes — nothing to summarize; add a Claude-API polish
  button later if notes grow.
- DOCX export — PDF only for now; add a doc-generation library later if the manager
  needs to edit.
- Remote live-sync, accounts, database, backend server.
- Tool integrations (Jira, Sheets, email delivery).
- Carrying over previous meetings' open action items.

## Open questions / assumptions to confirm

- Browser is Chrome/Edge on the meeting laptop (assumed). Yes
- Teams submit **one file per team**; folder is assembled before the meeting by
  whoever runs it (assumed). Yes
- PDF is an acceptable deliverable to the manager for v1 (assumed). Yes
