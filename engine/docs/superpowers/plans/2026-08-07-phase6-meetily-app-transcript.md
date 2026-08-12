# Phase 6 — Read official Meetily's transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `review.py` use the official Meetily desktop app's transcript (read from its local SQLite) instead of transcribing audio itself, so the app (capture) + our engine (templated minutes) + Quorum (notes/history) compose into one CLI pipeline.

**Architecture:** A new read-only module `meetily_app.py` (parallel to `quorum.py`) reads `~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite` (opened `?mode=ro` — never written). `review.py` gains `--list-meetily` (discover meeting ids) and `--meetily-app <id>` (use that transcript, recording becomes optional). Everything downstream — notes folding, `--meeting`, `--publish`, templates, two-pass — is unchanged.

**Tech Stack:** Python 3, stdlib `sqlite3` (no new dep), the existing `review.py`, `pytest`.

## Global Constraints

- meetily repo `/Users/leleditit/Desktop/Ospit/meetily`. Tests: `/tmp/rvenv/bin/python -m pytest`.
- **`meetily_app.py` is READ-ONLY:** every connection is `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`. It must never write to the app's DB (the user's real meeting history). Unit tests use a temp SQLite fixture, never the real app DB.
- DB path: `MEETILY_APP_DB` env override, else `~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite`; missing file → `SystemExit`.
- Transcript source of truth: `transcript_chunks.transcript_text`; fall back to assembling from `transcripts` (ordered by `audio_start_time`, `speaker` prefix only when non-blank) when no chunk row.
- `review.py` additions are additive: `--meetily-app` makes `recording` optional and replaces the transcribe step; it composes with local notes, `--meeting`, `--publish`. Phase 1–5 behavior + tests unchanged.
- `sqlite3` imported at module top in `meetily_app.py` (stdlib, always present); `review.py` imports `meetily_app` INSIDE the thin wrapper functions (the test stub seam), so non-Meetily paths never import it.

---

### Task 1: `meetily_app.py` — read-only transcript adapter

**Files:**
- Create: `meetily_app.py`
- Create: `test_meetily_app.py`

**Interfaces:**
- Produces:
  - `list_meetings(db_path=None) -> list[dict]` — `[{id,title,created_at,folder_path}]`, newest-first by `created_at`.
  - `get_transcript(meeting_id, db_path=None) -> str` — the meeting's full transcript; `SystemExit` if unknown id / empty.
  - `_assemble_from_chunks(rows) -> str` — PURE: `rows` = list of `(speaker, text)` → joined transcript, blanks dropped, `speaker: ` prefix only when speaker is non-blank.
  - `_db_path() -> Path` / `_connect(db_path)` — path resolution + read-only connection.

- [ ] **Step 1: Write the failing tests**

Create `test_meetily_app.py`:

```python
import sqlite3
import pytest
from pathlib import Path
import meetily_app


def _mkdb(path):
    c = sqlite3.connect(path)
    c.executescript("""
        create table meetings (id text primary key, title text, created_at text, folder_path text);
        create table transcript_chunks (meeting_id text primary key, transcript_text text);
        create table transcripts (id text primary key, meeting_id text, transcript text,
                                  speaker text, audio_start_time real);
    """)
    c.execute("insert into meetings values ('m1','Alpha','2026-07-24T10:00:00Z','/rec/a')")
    c.execute("insert into meetings values ('m2','Beta','2026-07-25T10:00:00Z','/rec/b')")
    c.execute("insert into transcript_chunks values ('m1','[00:01] full chunk transcript')")
    # m2 has no chunk — must fall back to assembling from transcripts (out of order)
    c.execute("insert into transcripts values ('t2','m2','second line','Bob',2.0)")
    c.execute("insert into transcripts values ('t1','m2','first line','',1.0)")
    c.commit(); c.close()


def test_assemble_from_chunks_pure():
    out = meetily_app._assemble_from_chunks([("", "hi"), ("Bob", "there"), ("", "  ")])
    assert out == "hi\nBob: there"


def test_get_transcript_prefers_chunk(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    assert meetily_app.get_transcript("m1", db) == "[00:01] full chunk transcript"


def test_get_transcript_falls_back_ordered(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    # ordered by audio_start_time: first line (blank speaker), then Bob's second line
    assert meetily_app.get_transcript("m2", db) == "first line\nBob: second line"


def test_get_transcript_unknown_exits(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    with pytest.raises(SystemExit):
        meetily_app.get_transcript("nope", db)


def test_list_meetings_newest_first(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    ids = [m["id"] for m in meetily_app.list_meetings(db)]
    assert ids == ["m2", "m1"]


def test_db_path_env_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MEETILY_APP_DB", str(tmp_path / "nope.sqlite"))
    with pytest.raises(SystemExit):
        meetily_app._db_path()


def test_connection_is_readonly(tmp_path):
    db = tmp_path / "m.sqlite"; _mkdb(db)
    conn = meetily_app._connect(db)
    with pytest.raises(sqlite3.OperationalError):   # read-only rejects writes
        conn.execute("insert into meetings values ('x','X','now','/x')")
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_meetily_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'meetily_app'`.

- [ ] **Step 3: Write `meetily_app.py`**

```python
#!/usr/bin/env python3
"""Read-only adapter over the official Meetily desktop app's SQLite
(~/Library/Application Support/com.meetily.ai/meeting_minutes.sqlite). Pulls a
meeting's transcript so review.py can generate minutes without re-transcribing.
NEVER writes to the app's data — every connection is opened read-only."""
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = (Path.home() / "Library" / "Application Support"
              / "com.meetily.ai" / "meeting_minutes.sqlite")


def _db_path() -> Path:
    p = Path(os.environ.get("MEETILY_APP_DB", DEFAULT_DB))
    if not p.exists():
        sys.exit(f"Meetily app DB not found at {p}. Is the app installed? "
                 f"Override with MEETILY_APP_DB=/path/to/meeting_minutes.sqlite")
    return p


def _connect(db_path):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _assemble_from_chunks(rows) -> str:
    """rows: list of (speaker, text) -> one transcript; blanks dropped, speaker prefix when set."""
    lines = []
    for speaker, text in rows:
        text = (text or "").strip()
        if not text:
            continue
        lines.append(f"{speaker}: {text}" if speaker else text)
    return "\n".join(lines).strip()


def list_meetings(db_path=None) -> list:
    c = _connect(db_path or _db_path())
    try:
        rows = c.execute("select id, title, created_at, folder_path "
                         "from meetings order by created_at desc").fetchall()
    finally:
        c.close()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "folder_path": r[3]} for r in rows]


def get_transcript(meeting_id: str, db_path=None) -> str:
    c = _connect(db_path or _db_path())
    try:
        row = c.execute("select transcript_text from transcript_chunks where meeting_id=?",
                        (meeting_id,)).fetchone()
        if row and (row[0] or "").strip():
            text = row[0].strip()
        else:
            parts = c.execute("select speaker, transcript from transcripts "
                              "where meeting_id=? order by audio_start_time",
                              (meeting_id,)).fetchall()
            text = _assemble_from_chunks(parts)
    finally:
        c.close()
    if not text.strip():
        sys.exit(f"No transcript found for Meetily app meeting {meeting_id}.")
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/tmp/rvenv/bin/python -m pytest test_meetily_app.py -v`
Expected: PASS (7 tests), including the read-only-connection test proving writes are rejected.

- [ ] **Step 5: Commit**

```bash
git add meetily_app.py test_meetily_app.py
git commit -m "feat: meetily_app.py — read-only adapter over the Meetily app SQLite (list meetings, get transcript)"
```

---

### Task 2: `review.py` — `--list-meetily` and `--meetily-app` modes

**Files:**
- Modify: `review.py`
- Modify: `test_review.py`

**Interfaces:**
- Consumes: Task 1's `meetily_app.get_transcript` / `list_meetings`; existing `transcribe`, `read_notes`, `resolve_template`, `build_prompt`, `_date_from`.
- Produces: `_transcript_via_meetily_app(id)` / `_list_meetily_meetings()` thin `import meetily_app` wrappers (test stub seams); two new argparse options; the transcript-source branch.

- [ ] **Step 1: Write the failing tests**

Add to `test_review.py`:

```python
def test_list_meetily_prints_and_returns(capsys, monkeypatch):
    import review
    monkeypatch.setattr(review, "_list_meetily_meetings",
                        lambda: [{"id": "m2", "title": "Beta", "created_at": "2026-07-25T10:00:00Z"},
                                 {"id": "m1", "title": "Alpha", "created_at": "2026-07-24T10:00:00Z"}])
    review.main(["--list-meetily"])
    out = capsys.readouterr().out
    assert "m2" in out and "2026-07-25" in out and "Beta" in out


def test_meetily_app_uses_transcript_without_recording(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_transcript_via_meetily_app", lambda mid: "APP TRANSCRIPT TEXT")
    def no_transcribe(*a, **k):
        raise AssertionError("transcribe must not be called in --meetily-app mode")
    monkeypatch.setattr(review, "transcribe", no_transcribe)
    template = tmp_path / "weekly_review.json"
    template.write_text(json.dumps({"name": "T", "description": "d",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    # no recording positional, dry-run to skip OpenAI
    review.main(["--meetily-app", "m1", "-t", str(template), "--dry-run"])
    out = capsys.readouterr().out
    assert "APP TRANSCRIPT TEXT" in out


def test_recording_or_meetily_app_required(monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        review.main(["--dry-run"])      # neither a recording nor --meetily-app
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_review.py -k "meetily" -v`
Expected: FAIL — the flags/wrappers don't exist; `test_recording_or_meetily_app_required` may already pass (existing guard) — that's fine, it locks in the behavior.

- [ ] **Step 3: Add the wrappers and argparse options**

Near the other `_via_quorum` wrappers add:

```python
def _transcript_via_meetily_app(meeting_id):
    import meetily_app
    return meetily_app.get_transcript(meeting_id)


def _list_meetily_meetings():
    import meetily_app
    return meetily_app.list_meetings()
```

In `main`, beside the other options:

```python
    ap.add_argument("--meetily-app", metavar="ID",
                    help="use the Meetily app meeting's transcript instead of transcribing")
    ap.add_argument("--list-meetily", action="store_true",
                    help="list the Meetily app's meetings (id, date, title) and exit")
```

- [ ] **Step 4: Add the `--list-meetily` early return**

After the `--sync-templates` early-return block, add:

```python
    if args.list_meetily:
        meetings = _list_meetily_meetings()
        if not meetings:
            print("no Meetily app meetings found.")
        for m in meetings:
            print(f'{m["id"]}  {(m.get("created_at") or "")[:10]}  {m.get("title") or ""}')
        return
```

- [ ] **Step 5: Relax the recording guard and branch the transcript source**

Change the recording-required guard (currently `if not args.recording: sys.exit("a recording ...")`):

```python
    if not args.recording and not args.meetily_app:
        sys.exit("a recording (audio file/folder) or --meetily-app <id> is required.")
```

Change the transcribe line (`transcript = transcribe(args.recording, args.clean)`):

```python
    if args.meetily_app:
        transcript = _transcript_via_meetily_app(args.meetily_app)
    else:
        transcript = transcribe(args.recording, args.clean)
```

Change the output-name line so it doesn't call `_date_from(None)`:

```python
    date = _date_from(args.recording) if args.recording else datetime.date.today().isoformat()
    out = args.out or f"{stem}_{date}.md"
```

(`datetime` is already imported — `_date_from` uses it.)

- [ ] **Step 6: Run the new tests, then the whole suite**

Run: `/tmp/rvenv/bin/python -m pytest test_review.py -k "meetily" -v`
Expected: PASS.
Run: `/tmp/rvenv/bin/python -m pytest test_review.py test_quorum.py test_meetily_app.py test_local.py -q`
Expected: all pass (Phases 1–5 unaffected).

- [ ] **Step 7: README + commit**

Add a short "Using the Meetily app's transcript" section to `README.md`:

```markdown
## Using the official Meetily app's transcript
Record in the Meetily app; then use its transcript instead of transcribing here:

    ./review.py --list-meetily                                  # find the meeting id
    ./review.py --meetily-app <id> notes.md -t weekly_review.json
    ./review.py --meetily-app <id> --meeting <quorum-id>        # + Quorum notes -> minutes

Read-only: this never modifies the app's data. Override the DB path with MEETILY_APP_DB.
```

```bash
git add review.py test_review.py README.md
git commit -m "feat: review.py --meetily-app (use the Meetily app transcript) and --list-meetily"
```

- [ ] **Step 8: Manual E2E (real app DB — do once)**

```bash
./review.py --list-meetily                 # shows your real 11 app meetings
./review.py --meetily-app <one-id> notes.md -t weekly_review.json --dry-run   # prompt shows the app transcript
```
Confirm the transcript is the app's and no OpenAI spend on `--dry-run`. Record the result.

---

## Self-Review

**Spec coverage:**
- `meetily_app.py` read-only adapter (`list_meetings`, `get_transcript`, `_assemble_from_chunks`, `_db_path`/`_connect`) — Task 1. ✓
- `transcript_chunks.transcript_text` with `transcripts` fallback ordered by `audio_start_time`, speaker prefix when set — Task 1 `get_transcript`/`_assemble_from_chunks`. ✓
- Read-only (`?mode=ro`) proven by a write-rejected test — Task 1 Step 1/4. ✓
- `--list-meetily` (discover ids) + `--meetily-app <id>` (transcript source, recording optional) — Task 2. ✓
- Composes with local notes / `--meeting` / `--publish`; downstream unchanged — Task 2 (only the transcript source + guard + output-date change). ✓
- Missing DB / unknown id → `SystemExit` — Task 1. ✓
- No new dependency (`sqlite3` stdlib); `meetily_app` imported lazily in review.py wrappers — Tasks 1/2. ✓
- Phase 1–5 tests preserved — Task 2 Step 6 full suite. ✓

**Placeholder scan:** No TBD/TODO. `<id>`, `<quorum-id>`, `<date>` are runtime values. Every code step is real.

**Type consistency:** `get_transcript(id)->str` feeds `transcript` (str) in review.py via `_transcript_via_meetily_app`; `list_meetings()->[{id,title,created_at,folder_path}]` matches `_list_meetily_meetings` and the `--list-meetily` printing (`m["id"]`, `created_at`, `title`). `_assemble_from_chunks(list[(speaker,text)])` matches the `transcripts` select `(speaker, transcript)` order. The recording-optional change (`nargs="?"` already) + guard + `_date_from` fallback are consistent. ✓
