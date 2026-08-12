# Quorum

Composed, precise meeting software where the tool disappears into the task. Teams submit pre‑meeting prep ahead of time; the admin reviews, records, generates structured minutes, presents a clean deck, and exports — with a full History archive. One indigo accent over warm‑gray OKLCH neutrals, two co‑equal light/dark themes.

> This repository is the **Quorum web app** (a static SPA + Supabase). It pairs with the **meetily engine** (a local Python repo) for AI minute generation, and optionally the official **Meetily desktop app** for capture/transcription. See [Architecture](#architecture).

---

## What it does

Quorum turns scattered pre‑meeting prep and note‑taking into one shared, structured flow:

1. **Create** a meeting — title, date, template, and mode.
2. **Collect / author** — in **Team** mode each team submits its own pre‑meeting note + files; in **Admin** mode you author everything yourself.
3. **Record** the meeting audio (on the Admin console) — saved to Supabase.
4. **Generate** minutes from the recording (+ the submitted notes and files) against your chosen template.
5. **Review & export** — edit the draft, Print / Save PDF, then **Finalize & archive** to History.

Status is **derived from what you do** — `Collecting → Recorded → Draft → Published` — never a manual flag.

## Architecture

Quorum is one product across three cooperating pieces:

| Piece | Repo / app | Role |
|-------|-----------|------|
| **Quorum web app** | this repo | The human layer: meetings, submissions, review, present, history. Static SPA served locally + **Supabase** (auth / DB / storage). |
| **meetily engine** | `~/Desktop/Ospit/meetily` (local) | The brain: `review.py` turns a transcript + notes into templated minutes; `quorum.py` reads Quorum's notes and publishes minutes; `local/bridge.py` is a small Flask bridge the web app calls to generate. |
| **Meetily desktop app** | `com.meetily.ai` (optional) | Records + live‑transcribes into a local SQLite; the engine can read that transcript. Browser Record / Import cover the cases where you don't use it. |

**AI generation is opt‑in and local.** The web app health‑checks the bridge (`localhost:8899`); if it's down, generation is disabled with a clear message and the structured (non‑AI) flow still works.

## Pages

| File | Purpose |
|------|---------|
| `web/index.html` | Sign in (email + password; account auto‑created on first sign‑in) |
| `web/admin.html` | Admin console — configure the meeting, review submissions, **record**, present/export |
| `web/team.html` | Team workspace — submit the pre‑meeting note + files, capture meeting notes (autosaves) |
| `web/minutes.html` | Draft & export — **generate** from a recording, edit, Print/PDF, Finalize |
| `web/present.html` | Projection deck — a committed always‑on‑stage presentation view |
| `web/history.html` | Archive of finalized meetings — submissions, files, and final minutes |
| `web/route.html`, `web/dev-login.html` | Auth redirect / local dev sign‑in |

Shared: `config.js` (Supabase + bridge URLs) · `supa.js` (client + helpers) · `auth.js` · `lib.js` (pure helpers, unit‑tested in `lib.test.js`) · `ui.js` (in‑app dialogs/toasts) · `theme.js` (light/dark).

## Design system

The visual system is documented in **[DESIGN.md](DESIGN.md)** and the product intent in **[PRODUCT.md](PRODUCT.md)**. In short: one indigo accent (action / selection / state only), warm‑gray OKLCH neutrals, a single humanist‑grotesk UI font (serif reserved for the exported minutes “paper”, mono for the note editor), fast state‑only motion, and WCAG AA as a floor in **both** themes.

## Running locally

1. **Configure** `web/config.js` with your Supabase URL + anon key and the bridge URL (`http://localhost:8899`).
2. **Start it** — double-click `engine/run-quorum.command`. It serves `web/` on `http://localhost:8000`, starts the AI bridge on `http://localhost:8899` (it shells `review.py`), and opens the admin console. Without the bridge, everything except AI generation works.
3. Sign in at `http://localhost:8000/` (or `dev-login.html` for a quick local admin session).

Supabase provides auth, the `meetings` / `teams` / `notes` / `submissions` tables, and a `submissions` storage bucket (recordings live under a `recordings/<meeting_id>/` prefix).

## Tests

```bash
node --test lib.test.js      # pure helpers (status derivation, minutes markdown, file classification)
```

The engine has its own Python suite (`pytest`) in the meetily repo.

---

*Formerly “MeeTeam.” The product is now uniformly **Quorum**.*
