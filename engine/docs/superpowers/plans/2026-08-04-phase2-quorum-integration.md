# Phase 2 — Quorum Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the local `review.py` a Supabase mode — pull a Quorum meeting's pre-meeting notes as the review's ground-truth input, and publish the finished review back to the meeting's minutes.

**Architecture:** A new `quorum.py` module holds all Supabase I/O (using the `supabase` Python client with a service-role key from `.env`), isolated from `review.py`'s core. `review.py` gains two additive modes: `--meeting <id>` (notes come from `quorum.fetch_notes`) and `--publish <id>` (push a local `.md` to `meetings.minutes_final` + archive). Pure assembly/guard logic is unit-tested; live-network paths are verified manually. Existing local-file flow is untouched.

**Tech Stack:** Python 3, `supabase` Python client, existing `markitdown` (for downloaded submission files), the Phase 1 `review.py`.

## Global Constraints

- `quorum.py` reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from the environment / gitignored `.env`. Never hardcoded, never committed.
- The `supabase` client is imported INSIDE functions (like `openai`/`markitdown`), so unit tests and `review.py`'s non-Supabase paths need it neither installed nor configured.
- Quorum schema (confirmed): `notes(meeting_id, team_id, pre_note, content, submitted, unique(meeting_id,team_id))`; `submissions(meeting_id, team_id, file_path, file_name, mime, url, created_at)`; `meetings(id, title, meeting_date, org, is_active, minutes_final, model)`. Files live in the private `submissions` storage bucket.
- Ground-truth INPUT = every team's `notes.pre_note` (labeled by `teams.name`) + each `submissions` file's extracted text + each link's `url`. It does NOT use `notes.content`.
- Publish = `update meetings set minutes_final=<md>, is_active=false where id=<meeting_id>`. Refuse to publish empty markdown; refuse if no meeting row matches.
- `review.py`'s existing local-file behavior and all Phase 1 tests must keep passing. New modes are additive.
- Test runner: `pytest`, in `test_quorum.py` (new) and `test_review.py` (extend).

---

### Task 1: `quorum.py` — Supabase read/write module

**Files:**
- Create: `quorum.py`
- Create: `test_quorum.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `markitdown` (already a dep) for downloaded files.
- Produces:
  - `_combine_inputs(pre_notes, file_texts, links) -> str` — PURE. `pre_notes`: list of `(team_name, text)`; `file_texts`: list of `(name, text)`; `links`: list of `(label, url)`. Returns one string, each non-empty piece under a `--- <label> ---` header, joined by blank lines, `.strip()`ed.
  - `_client()` — builds the supabase client from env; raises `SystemExit` if either env var is missing.
  - `fetch_notes(meeting_id: str) -> str` — assembles the ground-truth string from `notes` + `submissions`; raises `SystemExit` if the result is empty.
  - `publish_minutes(meeting_id: str, markdown: str) -> list` — raises `SystemExit` on empty markdown or when no meeting matched; else updates and returns the updated rows.

- [ ] **Step 1: Add the dependency**

Edit `requirements.txt` to add a third line:

```
openai
markitdown[docx,pptx,pdf]
supabase
```

- [ ] **Step 2: Write the failing tests**

Create `test_quorum.py`:

```python
import os
import pytest
from quorum import _combine_inputs, _client, publish_minutes


def test_combine_inputs_merges_with_headers():
    out = _combine_inputs(
        pre_notes=[("WCE", "did the thing"), ("MSAR", "  ")],   # blank one dropped
        file_texts=[("log.pdf", "file body")],
        links=[("dashboard", "https://x.test")],
    )
    assert "--- WCE (pre-meeting note) ---" in out
    assert "did the thing" in out
    assert "MSAR" not in out                      # empty pre_note omitted
    assert "--- log.pdf ---" in out and "file body" in out
    assert "--- link: dashboard ---" in out and "https://x.test" in out


def test_combine_inputs_empty_is_empty_string():
    assert _combine_inputs([], [], []) == ""


def test_client_requires_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(SystemExit):
        _client()


def test_publish_refuses_empty_markdown():
    with pytest.raises(SystemExit):
        publish_minutes("some-id", "   ")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest test_quorum.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quorum'`.

- [ ] **Step 4: Write minimal implementation**

Create `quorum.py`:

```python
#!/usr/bin/env python3
"""Supabase I/O for the review pipeline — pull a Quorum meeting's pre-meeting
notes, and publish the finished review to its minutes. All network access lives
here; review.py's core stays offline-testable."""

import os
import sys
import tempfile
from pathlib import Path


def _combine_inputs(pre_notes, file_texts, links) -> str:
    parts = []
    for team, text in pre_notes:
        if text and text.strip():
            parts.append(f"--- {team} (pre-meeting note) ---")
            parts.append(text.strip())
            parts.append("")
    for name, text in file_texts:
        if text and text.strip():
            parts.append(f"--- {name} ---")
            parts.append(text.strip())
            parts.append("")
    for label, url in links:
        if url:
            parts.append(f"--- link: {label} ---")
            parts.append(url)
            parts.append("")
    return "\n".join(parts).strip()


def _client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — put them in .env.")
    from supabase import create_client
    return create_client(url, key)


def fetch_notes(meeting_id: str) -> str:
    c = _client()
    note_rows = (c.table("notes").select("pre_note, teams(name)")
                 .eq("meeting_id", meeting_id).execute().data) or []
    pre_notes = [((r.get("teams") or {}).get("name") or "Team",
                  r.get("pre_note") or "") for r in note_rows]

    sub_rows = (c.table("submissions")
                .select("file_path, file_name, mime, url")
                .eq("meeting_id", meeting_id).execute().data) or []
    from markitdown import MarkItDown
    md = MarkItDown()
    file_texts, links = [], []
    for s in sub_rows:
        if s.get("mime") == "link" or (s.get("url") and not s.get("file_path")):
            links.append((s.get("file_name") or s.get("url"), s.get("url")))
            continue
        if not s.get("file_path"):
            continue
        blob = c.storage.from_("submissions").download(s["file_path"])
        suffix = Path(s.get("file_name") or s["file_path"]).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(blob)
            tmp = fh.name
        try:
            name = s.get("file_name") or Path(s["file_path"]).name
            file_texts.append((name, md.convert(tmp).text_content))
        finally:
            os.unlink(tmp)

    combined = _combine_inputs(pre_notes, file_texts, links)
    if not combined:
        sys.exit(f"No notes or submissions found for meeting {meeting_id}.")
    return combined


def publish_minutes(meeting_id: str, markdown: str) -> list:
    if not markdown or not markdown.strip():
        sys.exit("Refusing to publish empty minutes.")
    c = _client()
    res = (c.table("meetings")
           .update({"minutes_final": markdown, "is_active": False})
           .eq("id", meeting_id).execute())
    if not res.data:
        sys.exit(f"No meeting matched id {meeting_id}; nothing published.")
    return res.data
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest test_quorum.py -v`
Expected: PASS (4 passed). `_combine_inputs`, `_client` env guard, and the empty-publish guard are all exercised without any network call.

- [ ] **Step 6: Commit**

```bash
git add quorum.py test_quorum.py requirements.txt
git commit -m "feat: quorum.py — fetch a meeting's notes, publish its minutes"
```

---

### Task 2: `review.py` — `--meeting` and `--publish` modes

**Files:**
- Modify: `review.py`
- Modify: `test_review.py`

**Interfaces:**
- Consumes: `quorum.fetch_notes` / `quorum.publish_minutes` (Task 1); existing `transcribe`, `read_notes`, `build_prompt`, `list_projects`, `call_openai`.
- Produces: two new argparse options and the branches wiring them. `recording` becomes optional (`nargs="?"`) because publish mode takes a `.md` there instead.

- [ ] **Step 1: Write the failing tests**

Add to `test_review.py`:

```python
def test_publish_mode_pushes_file(tmp_path, monkeypatch):
    import review
    md = tmp_path / "r.md"
    md.write_text("# Minutes\nbody")
    called = {}
    monkeypatch.setattr(review, "_publish_via_quorum",
                        lambda mid, text: called.update(mid=mid, text=text))
    review.main([str(md), "--publish", "MID-1"])
    assert called == {"mid": "MID-1", "text": "# Minutes\nbody"}


def test_publish_mode_requires_a_file(monkeypatch):
    import review
    monkeypatch.setattr(review, "_publish_via_quorum", lambda mid, text: None)
    with pytest.raises(SystemExit):
        review.main(["--publish", "MID-1"])      # no .md positional


def test_meeting_mode_merges_quorum_notes(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QUORUM-NOTE")
    template = tmp_path / "t.json"
    template.write_text(json.dumps({"name": "T", "description": "D",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    audio = tmp_path / "a.m4a"
    audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"
    transcript.write_text("hello world")
    newer = audio.stat().st_mtime + 10
    os.utime(transcript, (newer, newer))

    review.main([str(audio), "-t", str(template), "--meeting", "MID-1", "--dry-run"])
    out = capsys.readouterr().out
    assert "QUORUM-NOTE" in out and "GROUND TRUTH" in out
```

(Add `import pytest` at the top of `test_review.py` if not already present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_review.py -k "publish_mode or meeting_mode" -v`
Expected: FAIL — `AttributeError`/`SystemExit` mismatch: `_publish_via_quorum` / `_fetch_via_quorum` and the new modes don't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `review.py`, add two thin indirection wrappers near the other helpers (they exist so tests can stub Supabase without importing it):

```python
def _fetch_via_quorum(meeting_id: str) -> str:
    import quorum
    return quorum.fetch_notes(meeting_id)


def _publish_via_quorum(meeting_id: str, markdown: str) -> None:
    import quorum
    quorum.publish_minutes(meeting_id, markdown)
```

Change the `recording` positional and add the two options in `main`:

```python
    ap.add_argument("recording", nargs="?",
                    help="audio/recording folder (generate), or the review .md (with --publish)")
```
```python
    ap.add_argument("--meeting", metavar="ID",
                    help="Quorum meeting id: pull its pre-meeting notes as ground truth")
    ap.add_argument("--publish", metavar="MEETING_ID",
                    help="publish the given review .md to this meeting's minutes and archive it")
```

Then, at the START of `main`'s body (right after `args = ap.parse_args(argv)`), handle publish first, and fold Quorum notes into the generate path:

```python
    if args.publish:
        if not args.recording:
            sys.exit("--publish needs the review .md file as the positional argument.")
        text = Path(args.recording).read_text()
        _publish_via_quorum(args.publish, text)
        print(f"published {args.recording} -> meeting {args.publish} (archived)")
        return

    if not args.recording:
        sys.exit("a recording (audio file or folder) is required.")

    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set. export it, or put it in a .env you source.")

    template = json.loads(Path(args.template).read_text())
    transcript = transcribe(args.recording, args.clean)
    notes = read_notes(args.notes)
    if args.meeting:
        qnotes = _fetch_via_quorum(args.meeting)
        notes = (qnotes + "\n\n" + notes).strip() if notes.strip() else qnotes
```

Delete the OLD `if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):` block and the OLD `template = …`/`transcript = …`/`notes = read_notes(...)` lines that these replace, so they are not duplicated. The rest of `main` (two-pass enumerate, `build_prompt`, dry-run print, `call_openai`, write) is unchanged.

- [ ] **Step 4: Run the new tests, then the whole suite**

Run: `python3 -m pytest test_review.py -k "publish_mode or meeting_mode" -v`
Expected: PASS.

Run: `python3 -m pytest test_review.py test_quorum.py -v`
Expected: PASS (all — Phase 1 tests still green, publish/meeting modes green).

- [ ] **Step 5: Update the README**

Add a Quorum section under `## Use`:

```markdown
## Quorum integration (Phase 2)
Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `.env` (Supabase → Settings → API,
the `service_role` key).

    # generate from a Quorum meeting's submitted notes
    ./review.py --meeting <meeting-id> "Meeting.m4a"

    # ...read/edit the produced weekly_review_<date>.md, fixing any dropped project...

    # publish the reviewed file as that meeting's minutes (archives it to History)
    ./review.py --publish <meeting-id> weekly_review_<date>.md
```

- [ ] **Step 6: Commit**

```bash
git add review.py test_review.py README.md
git commit -m "feat: review.py --meeting (notes from Quorum) and --publish (minutes to Quorum)"
```

- [ ] **Step 7: Manual end-to-end verification (network — do once, real project)**

With `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` in `.env` and a real active meeting id:

```bash
set -a && . ./.env && set +a
./review.py --meeting <id> "Meeting 31:6:2026.m4a" --dry-run   # prints prompt incl. Quorum notes
./review.py --meeting <id> "Meeting 31:6:2026.m4a"             # writes weekly_review_<date>.md
# eyeball the .md, then:
./review.py --publish <id> weekly_review_<date>.md
```

Confirm the meeting now shows the review as its minutes in Quorum's History and is no longer in the active list. Record the result in the completion notes.

---

## Self-Review

**Spec coverage:**
- `quorum.py` with `fetch_notes` / `publish_minutes` / `_combine_inputs` — Task 1. ✓
- Reads `notes.pre_note` per team (+ `teams.name`) and `submissions` files/links — Task 1 `fetch_notes`. ✓
- Publish updates `minutes_final` + `is_active=false`, refuses empty/no-match — Task 1 `publish_minutes`. ✓
- Service-role key + URL from env/.env; supabase imported lazily — Task 1 `_client`. ✓
- `review.py` `--meeting` (notes from Quorum, additive with local notes) and `--publish` — Task 2. ✓
- Publish mode needs no OpenAI key (returns before that check) — Task 2 ordering. ✓
- Existing local-file flow + Phase 1 tests untouched/passing — Task 2 Step 4 full suite. ✓
- `requirements.txt` gains `supabase` — Task 1 Step 1. ✓
- One runnable check per unit (pure `_combine_inputs`, env/empty guards, mode wiring via stubs) + manual E2E — Tasks 1–2. ✓

**Placeholder scan:** No TBD/TODO; every code step is real. `<id>`/`<date>` in shell examples are user-supplied runtime values, not plan placeholders.

**Type consistency:** `fetch_notes(id)->str` feeds `notes` (str) in review.py; `_fetch_via_quorum`/`_publish_via_quorum` wrap them with matching signatures and are the stub points the tests patch. `_combine_inputs(pre_notes, file_texts, links)` tuple shapes match `fetch_notes`'s construction. `recording` is `nargs="?"` so publish mode's positional-as-md-file works. ✓
