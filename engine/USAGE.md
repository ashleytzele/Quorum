# How to use it — step by step

Three systems, one flow: **Meetily app** records + transcribes → **this engine** turns the
transcript + team notes into templated minutes → **Quorum** holds the notes and the
finished minutes.

There are two ways to run it: the **integrated flow** (everything in Quorum, one button), or
the **command line** (no Quorum). Both use the same engine.

---

## A. Integrated flow — everything in Quorum (recommended)

### One-time setup (already done on this machine)
1. `.env` in the repo root has `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
2. The Supabase schema is applied — `docs/supabase-phase3.sql` and `docs/supabase-phase4.sql`
   were run once in the Supabase dashboard.
3. The Meetily desktop app (`/Applications/meetily.app`) is installed and records fine (it uses
   CoreAudio — no Audio MIDI setup needed).

### Each session — start it (double-click; leave the window open)
**`engine/run-quorum.command`** → the app on `http://localhost:8000` and the bridge on
`http://localhost:8899`, then opens the admin console. First run builds `.venv` and installs
deps; after that it's instant.

### Running a meeting
1. **Before** — in Quorum, create the meeting; your team members submit their pre-meeting
   notes (and, during the meeting, their live notes). More contributors = more accurate minutes.
2. **During** — open the **Meetily app** and hit **Record**. Stop when the meeting ends.
   (That's the only time you touch the Meetily app — 2 clicks.)
3. **After** — in Quorum, open the meeting's **Minutes** page (`localhost:8000/minutes.html`).
   In the **"Generate from Meetily"** card:
   - pick the **Recording** (auto-matched to the meeting by date — change it if needed),
   - click **Generate** — the bridge pulls that recording's transcript + the team's notes and
     produces the minutes, filling the editor.
   - **review and edit** the minutes (the AI occasionally needs a fix).
   - click **Finalize & archive** — publishes to `minutes_final` and moves the meeting to
     **History**.

> The **Generate from Meetily** card only appears when `run-bridge.command` is running. If the
> bridge is off, the page still works with Quorum's built-in structured minutes.

---

## B. Command line — no Quorum (the same engine)

```bash
# find the Meetily app recording you want
./review.py --list-meetily

# generate from that transcript + LOCAL note files:
./review.py --meetily-app <recording-id> notes1.md notes2.md -t weekly_review.json

# OR generate from that transcript + the meeting's Quorum team notes:
./review.py --meetily-app <recording-id> --meeting <quorum-meeting-id>

# then publish the reviewed .md back to Quorum (minutes + archive):
./review.py --publish <quorum-meeting-id> weekly_review_<date>.md
```

You can also transcribe a **local recording** instead of using the Meetily app:

```bash
./record.sh                                   # capture an online meeting (needs the Aggregate device)
./review.py "meeting.m4a" notes.md -t weekly_review.json
```

Templates: `weekly_review.json` (by-project weekly review) and `interview_review.json`
(neutral candidate record). Pass with `-t`, or set a meeting's template in Quorum's admin
dropdown and omit `-t`.

---

## C. Local GUI — solo, no cloud (optional third door)

```bash
./run-local.command        # opens http://localhost:8765
```
Create a meeting, write notes, Record/Stop, Generate, edit minutes — all stored as plain files
under `meetings/`. No Supabase, no Quorum.

---

## Running the tests
```bash
./.venv/bin/python -m pytest test_bridge.py test_review.py test_quorum.py test_meetily_app.py test_local.py -q
# Quorum:  cd <Quorum repo> && node --test lib.test.js
```

## Where things live
- `review.py` — the engine (transcript + notes → templated minutes). `retranscribe.sh` = local whisper.
- `quorum.py` — Quorum/Supabase (team notes in, minutes out). `meetily_app.py` — read the Meetily app's transcript (read-only).
- `local/bridge.py` — the Quorum "Generate" bridge. `local/serve.py` — the solo local GUI.
- `record.sh` — capture an online meeting locally. `*.json` — templates. `docs/` — specs, plans, SQL.
- `samples/` — your example inputs/outputs (gitignored).
