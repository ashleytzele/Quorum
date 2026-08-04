# Phase 1 — Weekly/Interview Review Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One local command turns a recording + optional notes into a structured markdown review (weekly or interview), replacing the hand-written workflow, using local whisper for transcription and the OpenAI API for generation.

**Architecture:** A single Python orchestrator `review.py` that shells out to the existing `retranscribe.sh` for transcription, reads note files with `markitdown`, turns a chosen JSON template into an OpenAI chat prompt (transcript fed line-numbered so citations are real), calls OpenAI, and writes the result. Pure functions (`build_prompt`, `number_lines`, `needs_transcribe`) carry the logic and the tests; I/O (whisper, markitdown, OpenAI) is thin and imported lazily so tests and `--dry-run` need no network or heavy deps.

**Tech Stack:** Python 3 (stdlib argparse/json/subprocess/pathlib), `openai` SDK, `markitdown`, existing `retranscribe.sh` (whisper.cpp).

## Global Constraints

- Language: Python 3 single-file script (`review.py`); no framework, no server.
- `MODEL = "gpt-4o-mini"` as a top-of-file constant — placeholder for "the mini"; confirm exact ID from the OpenAI dashboard, one-line change.
- API key from `OPENAI_API_KEY` env var (or gitignored `.env`); never hardcoded, never committed.
- Heavy/network imports (`openai`, `markitdown`) are imported INSIDE the functions that use them, so `--dry-run` and unit tests run with neither installed.
- Transcript is fed to OpenAI with line numbers (`N: ...`) — the templates cite `(lines X-Y)` and those must reference real lines.
- Default template `weekly_review.json`; `-t interview_review.json` for interviews. Output default name is `<template-stem>_<date>.md` (date from the recording's file mtime, not wall clock).
- Reuse `retranscribe.sh` unchanged. Skip transcription if a `.manglish.txt` newer than the audio already exists.
- Test runner: `pytest`. Tests live in `test_review.py` beside `review.py`.

---

### Task 1: Scaffolding + prompt builder core

**Files:**
- Create: `review.py`
- Create: `test_review.py`
- Create: `requirements.txt`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `number_lines(text: str) -> str` — each line prefixed `"{n}: "`, 1-based.
  - `build_prompt(template: dict, transcript: str, notes: str) -> list[dict]` — returns OpenAI `messages`: `[{"role":"system","content":...}, {"role":"user","content":...}]`. System = template description + every section's title/format/instruction/item_format. User = optional GROUND-TRUTH notes block + line-numbered transcript.

- [ ] **Step 1: Write `requirements.txt`**

```
openai
markitdown
```

- [ ] **Step 2: Write the failing tests**

Create `test_review.py`:

```python
import json
from review import number_lines, build_prompt


def test_number_lines():
    assert number_lines("hello\nworld") == "1: hello\n2: world"


def test_build_prompt_includes_sections_notes_and_numbered_transcript():
    template = {
        "name": "T",
        "description": "DESC-TEXT",
        "sections": [
            {"title": "Alpha", "instruction": "do alpha", "format": "string"},
            {"title": "Beta", "instruction": "do beta", "format": "list",
             "item_format": "| A | B |"},
        ],
    }
    msgs = build_prompt(template, "hello\nworld", "NOTE ONE")
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert "DESC-TEXT" in system
    assert "Alpha" in system and "Beta" in system
    assert "do alpha" in system and "do beta" in system
    assert "| A | B |" in system            # item_format carried through
    assert "GROUND TRUTH" in user and "NOTE ONE" in user
    assert "1: hello" in user and "2: world" in user


def test_build_prompt_omits_notes_block_when_empty():
    template = {"name": "T", "description": "D",
                "sections": [{"title": "X", "instruction": "i", "format": "string"}]}
    user = build_prompt(template, "line one", "")[1]["content"]
    assert "GROUND TRUTH" not in user
    assert "1: line one" in user
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest test_review.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'review'` (or ImportError for the functions).

- [ ] **Step 4: Write minimal implementation**

Create `review.py`:

```python
#!/usr/bin/env python3
"""Recording + notes -> structured review (weekly or interview) via local
whisper + the OpenAI API. See docs/superpowers/specs for the design."""

from pathlib import Path


def number_lines(text: str) -> str:
    return "\n".join(f"{i}: {ln}" for i, ln in enumerate(text.splitlines(), 1))


def build_prompt(template: dict, transcript: str, notes: str) -> list[dict]:
    sys_parts = [
        template["description"],
        "",
        "Produce these sections in order, following each instruction exactly. "
        "Output GitHub-flavored markdown. Use each section's title as a heading.",
    ]
    for s in template["sections"]:
        sys_parts.append(f"\n## {s['title']}  (format: {s['format']})")
        sys_parts.append(s["instruction"])
        if s.get("item_format"):
            sys_parts.append(f"Row/item format:\n{s['item_format']}")
    system = "\n".join(sys_parts)

    user_parts = []
    if notes.strip():
        user_parts.append(
            "=== GROUND TRUTH: pre-meeting notes "
            "(trust these over the transcript on any conflict) ===")
        user_parts.append(notes.strip())
        user_parts.append("")
    user_parts.append("=== TRANSCRIPT (cite line numbers, e.g. (lines 12-18)) ===")
    user_parts.append(number_lines(transcript))
    user = "\n".join(user_parts)

    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest test_review.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add review.py test_review.py requirements.txt
git commit -m "feat: review.py prompt builder core + tests"
```

---

### Task 2: Note extraction

**Files:**
- Modify: `review.py`
- Modify: `test_review.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `read_notes(paths: list[str]) -> str` — concatenates each note file's text (via `markitdown`), each preceded by a `--- filename ---` header; returns `""` for an empty list. `markitdown` is imported inside the function.

- [ ] **Step 1: Write the failing test**

Add to `test_review.py`:

```python
from review import read_notes


def test_read_notes_empty_returns_empty_string():
    assert read_notes([]) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_review.py::test_read_notes_empty_returns_empty_string -v`
Expected: FAIL — `ImportError: cannot import name 'read_notes'`.

- [ ] **Step 3: Write minimal implementation**

Add to `review.py`:

```python
def read_notes(paths: list[str]) -> str:
    if not paths:
        return ""
    from markitdown import MarkItDown
    md = MarkItDown()
    chunks = []
    for p in paths:
        chunks.append(f"--- {Path(p).name} ---")
        chunks.append(md.convert(p).text_content.strip())
    return "\n\n".join(chunks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_review.py::test_read_notes_empty_returns_empty_string -v`
Expected: PASS.

- [ ] **Step 5: Manually verify real extraction (no test — needs a real file)**

Run: `pip install markitdown && python3 -c "from review import read_notes; print(read_notes(['Lifeguard Interview Questions.docx'])[:200])"`
Expected: prints the first ~200 chars of the docx text (proves markitdown reads docx).

- [ ] **Step 6: Commit**

```bash
git add review.py test_review.py
git commit -m "feat: read_notes via markitdown"
```

---

### Task 3: Transcription wrapper

**Files:**
- Modify: `review.py`
- Modify: `test_review.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `needs_transcribe(audio: Path, transcript: Path) -> bool` — True if transcript missing, or (audio exists and) transcript older than audio; False if transcript exists and audio missing.
  - `transcribe(recording: str, clean: bool) -> str` — resolves the audio path (a folder means `<folder>/audio.mp4`, matching `retranscribe.sh`), runs `./retranscribe.sh [--clean] <recording>` only when `needs_transcribe`, then returns the `.manglish.txt` text. Transcript path is `<audio-parent>/<audio-stem>.manglish.txt` (mirrors `retranscribe.sh`'s `${AUDIO%.*}.manglish.txt`).

- [ ] **Step 1: Write the failing test**

Add to `test_review.py`:

```python
import os
from pathlib import Path
from review import needs_transcribe


def test_needs_transcribe(tmp_path):
    audio = tmp_path / "a.m4a"
    audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"

    # transcript missing -> must transcribe
    assert needs_transcribe(audio, transcript) is True

    # transcript newer than audio -> skip
    transcript.write_text("y")
    newer = audio.stat().st_mtime + 10
    os.utime(transcript, (newer, newer))
    assert needs_transcribe(audio, transcript) is False

    # transcript older than audio -> must transcribe
    older = audio.stat().st_mtime - 10
    os.utime(transcript, (older, older))
    assert needs_transcribe(audio, transcript) is True

    # audio gone, transcript present -> trust transcript, skip
    audio.unlink()
    assert needs_transcribe(audio, transcript) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_review.py::test_needs_transcribe -v`
Expected: FAIL — `ImportError: cannot import name 'needs_transcribe'`.

- [ ] **Step 3: Write minimal implementation**

Add to `review.py` (add `import subprocess` at the top with the other imports):

```python
import subprocess


def needs_transcribe(audio: Path, transcript: Path) -> bool:
    if not transcript.exists():
        return True
    if not audio.exists():
        return False
    return transcript.stat().st_mtime < audio.stat().st_mtime


def _audio_path(recording: str) -> Path:
    rec = Path(recording)
    return (rec / "audio.mp4") if rec.is_dir() else rec


def transcribe(recording: str, clean: bool) -> str:
    audio = _audio_path(recording)
    transcript = audio.parent / (audio.stem + ".manglish.txt")
    if needs_transcribe(audio, transcript):
        script = Path(__file__).resolve().parent / "retranscribe.sh"
        cmd = [str(script)] + (["--clean"] if clean else []) + [str(recording)]
        subprocess.run(cmd, check=True)
    return transcript.read_text()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_review.py::test_needs_transcribe -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add review.py test_review.py
git commit -m "feat: transcribe wrapper + skip-if-fresh"
```

---

### Task 4: OpenAI call, CLI, dry-run, README

**Files:**
- Modify: `review.py`
- Modify: `test_review.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `build_prompt` (T1), `read_notes` (T2), `transcribe` (T3).
- Produces:
  - `call_openai(messages: list[dict], model: str) -> str` — one chat completion, returns the content. `openai` imported inside.
  - `main(argv=None) -> None` — argparse CLI: `recording`, `notes*`, `-t/--template` (default `weekly_review.json` beside the script), `--clean`, `--dry-run`, `-o/--out`, `--model` (default `MODEL`). Dry-run prints the messages and returns without importing/calling OpenAI. Non-dry-run with no `OPENAI_API_KEY` exits early (before transcribing).

- [ ] **Step 1: Write the failing test**

Add to `test_review.py`:

```python
import json
from review import main


def test_dry_run_prints_prompt_without_api_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    template = tmp_path / "t.json"
    template.write_text(json.dumps({
        "name": "T", "description": "D",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    audio = tmp_path / "a.m4a"
    audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"
    transcript.write_text("hello world")
    newer = audio.stat().st_mtime + 10
    os.utime(transcript, (newer, newer))   # fresh -> transcribe() won't shell out

    main([str(audio), "-t", str(template), "--dry-run"])

    out = capsys.readouterr().out
    assert "SYSTEM" in out
    assert "1: hello world" in out          # line-numbered transcript in the prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_review.py::test_dry_run_prints_prompt_without_api_key -v`
Expected: FAIL — `ImportError: cannot import name 'main'`.

- [ ] **Step 3: Write minimal implementation**

Add to `review.py` (add `import argparse, json, os, sys, datetime` at the top):

```python
import argparse
import datetime
import json
import os
import sys

MODEL = "gpt-4o-mini"  # "the mini" — confirm exact id from OpenAI dashboard
DEFAULT_TEMPLATE = "weekly_review.json"


def call_openai(messages: list[dict], model: str) -> str:
    from openai import OpenAI
    client = OpenAI()  # reads OPENAI_API_KEY from env
    resp = client.chat.completions.create(model=model, messages=messages)
    return resp.choices[0].message.content


def _date_from(recording: str) -> str:
    audio = _audio_path(recording)
    target = audio if audio.exists() else Path(recording)
    return datetime.date.fromtimestamp(target.stat().st_mtime).isoformat()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Recording + notes -> markdown review.")
    ap.add_argument("recording", help="audio file or Meetily recording folder")
    ap.add_argument("notes", nargs="*", help="pre-meeting .docx/.pptx/.pdf files")
    ap.add_argument("-t", "--template",
                    default=str(Path(__file__).resolve().parent / DEFAULT_TEMPLATE))
    ap.add_argument("--clean", action="store_true", help="denoise before transcribing")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the prompt and stop; no OpenAI call")
    ap.add_argument("-o", "--out", help="output .md path")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args(argv)

    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set. export it, or put it in a .env you source.")

    template = json.loads(Path(args.template).read_text())
    transcript = transcribe(args.recording, args.clean)
    notes = read_notes(args.notes)
    messages = build_prompt(template, transcript, notes)

    if args.dry_run:
        for m in messages:
            print(f"\n===== {m['role'].upper()} =====\n{m['content']}")
        return

    result = call_openai(messages, args.model)
    stem = Path(args.template).stem
    out = args.out or f"{stem}_{_date_from(args.recording)}.md"
    Path(out).write_text(result)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_review.py::test_dry_run_prints_prompt_without_api_key -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m pytest test_review.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Write `README.md`**

```markdown
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
```

- [ ] **Step 7: Make the script executable and commit everything (incl. the loose repo files)**

```bash
chmod +x review.py
git add review.py test_review.py README.md \
    retranscribe.sh glossary.txt weekly_review.json interview_review.json
git commit -m "feat: OpenAI call + CLI + dry-run + README; track pipeline files"
```

---

## Self-Review

**Spec coverage:**
- Repo hygiene (git init, .gitignore, README) — git/.gitignore already committed; README in Task 4. ✓
- `review.py <recording> <notes...> [-t] [--clean] [--dry-run] [-o]` — Task 4 argparse. ✓
- Transcribe via `retranscribe.sh`, skip-if-fresh — Task 3. ✓
- Read notes (docx/pptx/pdf) via markitdown — Task 2. ✓
- Build prompt from template; notes = GROUND TRUTH; transcript line-numbered — Task 1. ✓
- OpenAI call, model constant, key from env, fail early if missing — Task 4. ✓
- Write `<stem>_<date>.md`, date from recording mtime — Task 4. ✓
- `--dry-run` builds+prints prompt, no token spend; doubles as the check — Task 4 + tests. ✓
- One runnable check (tests on the pure functions) — Tasks 1–4. ✓
- Error handling: missing key early (T4), retranscribe failure propagates via `check=True` (T3), missing files raise on read. ✓

**Placeholder scan:** No TBD/TODO; every code step has real code. `MODEL="gpt-4o-mini"` is an intentional, documented config value, not a placeholder.

**Type consistency:** `build_prompt` returns `list[dict]` (messages) — consumed by `call_openai(messages, model)` and printed in dry-run. `_audio_path` defined in T3, reused by `_date_from` in T4. `transcribe`/`read_notes`/`build_prompt` names match across tasks. ✓
