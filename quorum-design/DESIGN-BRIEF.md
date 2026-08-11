# Quorum — Design Improvement Brief

## What this app is
Quorum is a lightweight web app for running recurring team meetings.
- **Admins** configure a meeting, review each team's submissions, then **present** and **export minutes**.
- **Team members** submit pre-meeting notes + files and capture meeting notes.
- Two meeting **modes**: **Team** (each team self-submits) and **VIP** (the admin authors everything solo, no teams).
- Extras: a full-screen **Present** slideshow, a printable **Minutes** document, and a searchable **History** archive. Admins can create teams and **invite members by email**.

## Tech & how to work with these files (read carefully)
- Plain **static HTML + one shared `styles.css` + vanilla JS**. No build step, no framework, no bundler.
- The backend is **Supabase**; the files `supa.js`, `auth.js`, `config.js`, `lib.js` are **plumbing — do not redesign them**.
- All pages share `styles.css` (design tokens are defined in `:root` at the top — colors, radii, shadows, fonts). Prefer improving the design **there** plus light HTML polish.
- **CRITICAL — do not break the JavaScript:** the JS selects elements by their `id` and by specific class names. **Preserve every `id="..."` attribute and these functional class names**, or the app stops working:
  `meeting-tabs`, `meeting-tab`, `mt-dot`, `mt-sub`, `mt-date`, `mt-flag`, `notes-split`, `pane`, `md-editor`, `subpanel`, `segmented`, `dropzone`, `filelist`, `file-item`, `drawer`, `drawer-overlay`, `roster`, `hitem`, `htitle`, `hdel`, `hlist`, `pf-card`/`pf-item`/`pf-start`/`pf-team` (the present checklist), `detail-file`, `notes-yes`/`notes-no`, `status`/`pill`, `embed` (VIP embed mode), plus every element `id` (e.g. `m-title`, `m-date`, `m-model`, `invite-emails`, `team-rows`, `vip-frame`, `history-search`, `pre-note`, `notes`, `submit-toggle`, `notes-submit-toggle`).
  You may freely restyle, re-space, add wrapper elements, and refine markup **around** these hooks — just keep the hooks themselves.
- Keep it **self-contained**: no new dependencies beyond the current CDN scripts (`supabase-js`, `markdown-it`) and Google Fonts.

## The pages (all should be improved)
1. **`index.html`** — login / create-account (email + password).
2. **`admin.html`** — admin dashboard: *Meeting details* card (title/date/org + **Mode** dropdown), a row of **meeting tabs** (each with a mode tag Team/VIP + a submitted-count), the **Teams** table (Team · Files · Pre-meeting · Notes · View), a slide-in **team drawer** (rename/delete team, **Members** roster with add-by-email + Joined/Pending, submitted files, notes preview), and **Export / Present** buttons. For VIP meetings the Teams table is replaced by an embedded single-editor workspace (`#vip-workspace` iframe).
3. **`team.html`** — member workspace: *Pre-meeting submission* (segmented: Markdown editor w/ live preview | file & link upload, plus a Draft/Submitted toggle) and *Meeting notes* (Markdown editor w/ preview + its own submitted toggle). Also renders **embedded** inside admin for VIP meetings (add `?embed=1`; the `.embed` class strips its own topbar/nav).
4. **`present.html`** — full-screen **dark** slideshow with a pre-flight "What to present" checklist overlay, then swipeable slides (title, team update, one slide per file/link). Keyboard nav.
5. **`minutes.html`** — a clean, **printable** minutes document (print-to-PDF).
6. **`history.html`** — left list of past meetings (with a **search** box and a hover **trash icon** per item) + a detail panel (notes / files / final minutes).

## Current look (starting point)
Clean, light theme; indigo accent `#3b4dd8`; rounded cards with soft shadows; Hanken Grotesk (UI) + Source Serif (document). It works but reads a little generic/templated.

## What I want improved
> Edit this section with your taste — the notes below are a starting point.
- A more **distinctive, premium SaaS** feel — stronger visual hierarchy, more intentional typography scale and spacing rhythm, less "default template."
- **Color direction:** _[keep indigo / propose a new palette / add a brand color — your call]_.
- **Dark mode:** _[yes, add a proper dark theme / no, keep light]_.
- More refined **components**: buttons, inputs, selects, cards, the meeting tabs, badges/pills (Team/VIP/Draft/Submitted/Pending/Joined), the team drawer, the Markdown editor split, the members roster, the history list.
- Better **empty states**, **status indicators**, and **loading/saved** feedback.
- A more inviting **login** page.
- Make **Present** feel like a real, polished deck.
- Fully **responsive** (works down to mobile widths; the editor split already collapses under ~1160px).

## Deliverable
Updated **HTML + `styles.css`** that drop straight back into the same flat file structure (all files sit in one folder; pages reference `styles.css`, `supa.js`, etc. by relative name). Don't change routes, functionality, ids, or data attributes.
