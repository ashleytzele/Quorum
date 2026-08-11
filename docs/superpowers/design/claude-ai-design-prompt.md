# claude.ai/design prompt — Hosted Meeting App

Paste the block below into claude.ai/design. It produces the 5 screens as a
self-contained visual prototype. The **Required element IDs** section is the
important part — it makes the design's markup line up with the backend wiring so
integration is copy-paste, not rework.

---

## PROMPT (copy from here)

Design a clean, professional web app called **"Quorum"** for a company to
run recurring team meetings. Plain **HTML and CSS only** — no React, no frameworks,
no build tools. Each screen is a separate self-contained HTML page. Use placeholder
/ dummy data to show the look (no real backend — it's a visual prototype).

**Aesthetic:** calm, modern corporate SaaS. Generous white space, a neutral base
(white / slate greys) with a single confident accent color, strong readable
typography, subtle rounded cards and soft shadows. Accessible contrast. Fully
responsive (looks good on a laptop and a phone). Avoid a generic Bootstrap look —
make it feel intentional and premium.

Design these **5 pages**:

1. **Login** (`index.html`) — centered card: product name, one email input, a
   "Send me a login link" button, and a small status message line. That's it.

2. **Team dashboard** (`team.html`) — the page a team member sees. Top bar shows the
   team name and the active meeting title. Two panels:
   - **Files:** a drag-and-drop upload area ("Drop documents or pictures here"), and
     below it a list of uploaded files, each with a small "Remove" button.
   - **Notes:** a large Markdown textarea with a live-rendered preview beside/below
     it, and a subtle "Saved" status indicator.

3. **Admin dashboard** (`admin.html`) — top: a small form to set the meeting
   Title / Date / Organization. Middle: a table of teams, each row showing the team
   name, a file count, and a notes status (✓ notes / — no notes). Bottom: two primary
   buttons, "Present" and "Export minutes".

4. **Present** (`present.html`) — a full-bleed slideshow stage (dark or white) that
   fills the screen, with a small hint that arrow keys navigate and F is fullscreen.
   One clean content area centered — it will hold slides. Minimal chrome.

5. **Minutes** (`minutes.html`) — a formal document view: a header area with fields
   for Organization / Title / Date and a "Decisions" textarea, a "Generate" and a
   "Print / Save PDF" button, and below it a nicely typeset document area styled like
   printed meeting minutes (serif or clean sans, readable measure, section headings).

**Required element IDs** — the markup MUST include exactly these ids (the app's
JavaScript targets them):

- Login: form `id="login-form"`, email input `id="email"`, status `id="login-msg"`.
- Team: `id="team-name"`, `id="meeting-title"`, file input `id="file-input"`,
  file list `id="file-list"`, notes textarea `id="notes"`, preview `id="notes-preview"`,
  save status `id="save-status"`.
- Admin: meeting form `id="meeting-form"` with inputs `id="m-title"`, `id="m-date"`,
  `id="m-org"`; team table body `id="team-rows"`; buttons `id="present-btn"`,
  `id="minutes-btn"`.
- Present: `<div class="reveal" id="deck"><div class="slides" id="slides"></div></div>`.
- Minutes: decisions textarea `id="decisions"`, buttons `id="generate"` and
  `id="print"`, document area `id="minutes"`.

Keep all CSS in a single shared stylesheet so the pages feel like one product. Do not
add login providers, real uploads, or any backend code — just the visuals with the
ids above.

## PROMPT (end)

---

## UPDATE PROMPT (v2) — paste into the SAME claude.ai/design chat

Building on the current Quorum design — **keep the same look, layout language, colors,
and single shared stylesheet** — make these changes and add one new page. Still HTML/CSS
only, dummy data, no backend.

### Change — Team dashboard (`team.html`)
Restructure into three clearly separated sections:

1. **Pre-meeting submission (what you're presenting)** — a labeled section giving the
   user two ways to provide their material, shown as a small toggle or two sub-cards:
   - **Type a note** — a Markdown textarea with a live-rendered preview.
   - **Upload files** — the existing drag-and-drop area + file list with Remove.

   This section shows an autosave indicator **and** a **"Mark as submitted"** toggle
   with a status label that reads **Draft** or **Submitted**.

2. **Meeting notes (for the minutes)** — a *separate* Markdown textarea with live
   preview and a "Saved" indicator. Label it clearly as the note that goes into the
   meeting minutes (distinct from the presentation note above).

3. A top-bar link/button to **History** (goes to `history.html`).

### Change — Admin dashboard (`admin.html`)
- Make each team row **clickable** (or add a "View" button per row). Selecting a team
  opens a **detail panel** (side drawer or modal) showing that team's **submitted files**
  (a list, each openable) and a **rendered preview of their notes**.
- Add a **"Preview slideshow"** button (near Present / Export minutes) that opens the
  full combined presentation preview.

### New page — Team history (`history.html`)
Read-only page for a team member to look back at past meetings:
- Top bar with the team name and a link back to the dashboard.
- A **list of past meetings** (title + date), newest first.
- Selecting a meeting reveals a **detail view** with three parts: this team's
  **submitted notes** (rendered), their **submitted files** (list, openable), and the
  meeting's **final minutes** (rendered, with a "Save PDF" affordance).

### Additional required element IDs (must appear exactly)
- Team pre-meeting note: textarea `id="pre-note"`, preview `id="pre-note-preview"`,
  submitted toggle `id="submit-toggle"`, status `id="submit-status"`.
- Keep the existing meeting-notes ids: `id="notes"`, `id="notes-preview"`, `id="save-status"`.
- Keep the existing file ids: `id="file-input"`, `id="file-list"`.
- Team nav link to history: `id="history-link"`.
- Admin: each team row/button carries a `data-team-id` attribute; detail panel
  `id="team-detail"`, files list `id="detail-files"`, notes preview `id="detail-notes"`;
  preview button `id="preview-slideshow-btn"`.
- History: team name `id="team-name"`, meetings list `id="history-list"`, detail
  container `id="history-detail"`, notes `id="history-notes"`, files `id="history-files"`,
  minutes `id="history-minutes"`.

## UPDATE PROMPT (end)

---

## After you design it

Send me the generated HTML/CSS (paste it, or share the artifact). I'll drop the pages
into `web/`, keep your look untouched, and wire each id to Supabase (auth, uploads,
notes, present, minutes) per the build plan. If an id is missing or renamed, I'll
reconcile it — but matching the list above means near-zero rework.
