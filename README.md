# meetily review pipeline

Turn a recording + optional pre-meeting notes into a structured markdown review
(weekly team review or candidate interview record), fully local except the one
OpenAI generation call.

## Setup
    pip install -r requirements.txt
    export OPENAI_API_KEY=sk-...        # or keep it in a .env you source

## Use
    # weekly review (default template)
    ./review.py "Meeting 31:6:2026.m4a" notes1.docx notes2.pdf --clean

    # interview record
    ./review.py interview.m4a -t interview_review.json

    # see the exact prompt without spending a token
    ./review.py interview.m4a -t interview_review.json --dry-run

Output: `<template-stem>_<date>.md` (e.g. `weekly_review_2026-07-31.md`), or
pass `-o out.md`.

## Quorum integration (Phase 2)
Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `.env` (Supabase → Settings → API,
the `service_role` key).

    # generate from a Quorum meeting's submitted notes
    ./review.py --meeting <meeting-id> "Meeting.m4a"

    # ...read/edit the produced weekly_review_<date>.md, fixing any dropped project...

    # publish the reviewed file as that meeting's minutes (archives it to History)
    ./review.py --publish <meeting-id> weekly_review_<date>.md

## Recording an online meeting (Zoom / Meet / Teams)
The pipeline only needs an audio file, so any online call works once you can
record both sides into one file.

**One-time setup (Audio MIDI Setup.app):**
1. **Multi-Output Device** = `VB-Cable` + your headphones. Set the meeting app's
   speaker (or the system output) to it — the far-end audio goes into VB-Cable and
   you still hear it.
2. **Aggregate Device** = `VB-Cable` + your microphone. This is what gets recorded,
   so one file carries both the far end and your voice.

**Each meeting:**

    ./record.sh                     # Ctrl-C to stop; writes recordings/meeting_<ts>.m4a
    ./review.py --meeting <id> recordings/meeting_<ts>.m4a

`RECORD_DEVICE="My Aggregate" ./record.sh` if your device has another name;
`./record.sh --list` shows what ffmpeg sees.

**Verify once:** record ~15s while you talk and a video clip plays, then
`./review.py <that-file> --dry-run` and confirm both voices appear in the transcript
before trusting it on a real meeting.

## Writing the notes — the ONE habit that matters
Start each notes document with the **project name as the first heading**, e.g.
`# DataAnalyzerProMax`, then the details. One document = one project.

This is not optional polish. The weekly template runs a **two-pass** generation
(first the model lists the projects, then writes one section each — see the
`enumerate` key in `weekly_review.json`), which stops projects being merged or
fragmented. But the enumerate pass can only keep a project it can NAME. Verified
on 2026-07-31 with `gpt-4o-mini`:

- unnamed project doc → still dropped or shattered into feature-fragments
- **named project doc + two-pass → all 5 projects kept, correctly** ✅

Each run prints `projects (N): ...` before writing — glance at it. If a project
is missing or a feature is masquerading as a project, that's your cue to fix the
heading in that notes doc. `gpt-4o-mini` is the default and is as good as
`gpt-4o` here, so no cheap model upgrade helps — naming does.

## Pieces
- `retranscribe.sh` — local whisper.cpp + glossary; writes `<audio>.manglish.txt`.
- `glossary.txt` — whisper proper-noun prompt (keep < ~900 chars).
- `weekly_review.json` / `interview_review.json` — output templates (sections).
- `review.py` — orchestrator. `MODEL` at the top selects the OpenAI model.

## Phases
1. This CLI (done).
2. Wire into MeeTeam/Quorum: notes from its store, review into Minutes/History.
3. Fully local (drop Supabase) — later, only if true offline is needed.
See `docs/superpowers/specs/`.
