# claude.ai/design prompt — Hosted Meeting App

Paste the block below into claude.ai/design. It produces the 5 screens as a
self-contained visual prototype. The **Required element IDs** section is the
important part — it makes the design's markup line up with the backend wiring so
integration is copy-paste, not rework.

---

## PROMPT (copy from here)

Design a clean, professional web app called **"Meeting Minutes"** for a company to
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

## After you design it

Send me the generated HTML/CSS (paste it, or share the artifact). I'll drop the pages
into `web/`, keep your look untouched, and wire each id to Supabase (auth, uploads,
notes, present, minutes) per the build plan. If an id is missing or renamed, I'll
reconcile it — but matching the list above means near-zero rework.
