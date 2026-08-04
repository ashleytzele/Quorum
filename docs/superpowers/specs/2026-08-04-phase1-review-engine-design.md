# Phase 1 — Weekly Review Engine (`review.py`)

**Date:** 2026-08-04
**Status:** Design, awaiting approval
**Context:** First sub-project of the MeeTeam/Quorum ↔ Meetily full merge. See "Phasing" below.

## Why

Today the weekly review is produced by hand: Claude reads the pre-meeting notes
and the whisper transcript, follows the `weekly_review.json` (v2) template, and
writes `weekly_review_YYYY-MM-DD.md`. Claude is going away. Without automation,
the reviews simply stop.

Phase 1 replaces that hand process with **one local command** that runs the same
pipeline end to end using the OpenAI API for the generation step. Everything else
(recording, transcription, glossary) stays local and unchanged.

## Phasing (whole merge, for context — only Phase 1 is in scope here)

1. **Phase 1 — review engine (THIS SPEC).** Standalone local CLI: recording +
   notes → transcript → OpenAI → review `.md`. Works on plain files, no UI, no
   Supabase.
2. **Phase 2 — wire into Quorum.** Trigger from the app; pre-meeting notes come
   from MeeTeam's store instead of local files; finished review lands in
   Minutes/History.
3. **Phase 3 — fully local (drop Supabase).** Deferred; only if true offline is
   wanted after 1+2 prove out.

Supabase stays as-is through Phases 1 and 2.

## Scope of Phase 1

Make the `meetily` folder a real git repo, and add one Python orchestrator that
reuses the tools already here.

### Repo hygiene (part of this phase)
- `git init` (done).
- `.gitignore` excludes the large binaries that must never be committed:
  `*.m4a`, `*.wav`, `*.bin` (whisper/VAD models), `.env`. Keep scripts, glossary,
  template JSON, specs, and generated `.md` reviews.
- `README.md`: what the repo is, how to run `review.py`, the phase plan.

### The command
```
review.py <recording.m4a> <note-file>... [-t template.json] [--clean] [--dry-run] [-o out.md]
```
- `<recording.m4a>` — the Meetily recording (or a recording folder, same as
  `retranscribe.sh` accepts).
- `<note-file>...` — one or more pre-meeting `.docx` / `.pptx` / `.pdf` files.
  Optional — an interview run typically has none.
- `-t template.json` — which summary template to use. Default `weekly_review.json`
  (the weekly review). Pass `-t interview_review.json` for a candidate interview
  record. The template is just a different set of sections/instructions; the
  pipeline is identical.
- `--clean` — passed straight through to `retranscribe.sh` (denoise/normalize).
- `--dry-run` — build and print the full assembled prompt, then stop. No OpenAI
  call, no token spend. Used to eyeball the prompt and as the built-in check.
- `-o out.md` — output path. Default `weekly_review_YYYY-MM-DD.md` (date from the
  recording's own timestamp, not the wall clock).

### Pipeline (in order)
1. **Transcribe.** Shell out to `./retranscribe.sh [--clean] <recording>`, which
   writes `<audio>.manglish.txt` (plain, deduplicated, timestamp-stripped lines).
   Skip this step if that file already exists and is newer than the audio.
2. **Read notes.** Extract plain text from each note file via `markitdown` (one
   dependency covers docx + pptx + pdf). *Fallback if minimal deps preferred:*
   `textutil` (docx, built-in) + `unzip` (pptx, built-in) + `pypdf` (pdf). This
   whole step is deleted in Phase 2 (notes come from MeeTeam).
3. **Build the prompt** from `weekly_review.json`:
   - **System prompt** = the template's `description` + each section's `title` +
     `instruction` + `format`/`item_format`, assembled into "produce these
     sections following these instructions" guidance. The v2 instructions are
     already written as LLM directions ("GROUND EVERYTHING", "TRUST THE NOTES",
     the confidence rule), so this is near-verbatim.
   - **User content** = the notes (clearly labelled **GROUND TRUTH — trust on
     conflict**) + the transcript **prefixed with line numbers** (`1: ...`,
     `2: ...`), so the model's `(lines 52–63)` citations reference real lines in
     `.manglish.txt`. Without line numbers the citations are fiction.
4. **Call OpenAI.** Chat completion. Model is a single top-of-file constant
   `MODEL = "gpt-4o-mini"` — confirm the exact ID against the OpenAI dashboard;
   changing it is one line. Key read from `OPENAI_API_KEY` env var or a gitignored
   `.env`. Never hardcoded, never committed.
5. **Write** the returned markdown to the output path.

## Non-goals (explicitly deferred)
- No web UI — Phase 2.
- No Supabase / MeeTeam integration — Phase 2.
- No local LLM — using OpenAI per decision.
- No changes to whisper / `retranscribe.sh` internals — reused as-is.
- No OCR or exotic doc formats — only the docx/pptx/pdf actually used.

## Data flow
```
recording.m4a ─► retranscribe.sh ─► <audio>.manglish.txt (line-numbered in prompt)
note files ─────► markitdown ─────► notes text (GROUND TRUTH)
                                          │
weekly_review.json (v2) ─► system prompt  ▼
                              └────────► OpenAI (MODEL) ─► weekly_review_YYYY-MM-DD.md
```

## Error handling
- Missing recording / note file → clear message, exit non-zero (mirrors
  `retranscribe.sh` style).
- Missing `OPENAI_API_KEY` → fail early with instructions, before transcribing.
- `retranscribe.sh` failure → propagate its exit code and stderr, don't call
  OpenAI.
- OpenAI error (auth, rate, network) → print the error, keep the transcript and
  the assembled prompt on disk so the run can be retried without re-transcribing.

## Testing / check (ponytail: one runnable check)
- `--dry-run` builds the full prompt and prints it — no API call. This is the
  primary check: run it and confirm the prompt contains every template section,
  the notes marked GROUND TRUTH, and the transcript line-numbered.
- One small `test_review.py` asserting the prompt-builder output: all section
  titles present, notes block labelled ground truth, transcript lines carry
  `N:` prefixes. No framework — plain `assert` in `__main__` or a single
  `test_*.py`.

## Open items
- Exact OpenAI model ID ("the mini") — placeholder `gpt-4o-mini`, confirm from
  dashboard.
- `markitdown` vs the built-in `textutil`/`unzip`/`pypdf` fallback — default
  `markitdown`; switch is contained to step 2.
