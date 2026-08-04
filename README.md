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
