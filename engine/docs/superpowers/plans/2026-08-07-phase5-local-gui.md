# Phase 5 — Local GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single-user local web GUI (`local/`) to enter notes, record in-app, generate minutes, and browse past meetings — backed by plain folders, shelling out to the existing `review.py`, with no cloud.

**Architecture:** A Flask backend (`local/serve.py`, bound to 127.0.0.1) stores each meeting as a folder under `meetings/<id>/` (`meta.json`, `notes/*.md`, `recording.m4a`, `minutes.md`), spawns ffmpeg for Record/Stop, and runs `review.py` (local-file mode) for Generate. A single static page (`local/static/`, reusing MeeTeam's `styles.css`) drives it via `fetch`. `review.py` and its Supabase modes are untouched.

**Tech Stack:** Python 3 + Flask (new, local-only), `pytest`; the existing `review.py`/ffmpeg; vanilla HTML/JS.

## Global Constraints

- **New app lives in `local/`** in the meetily repo (`/Users/leleditit/Desktop/Ospit/meetily`). `review.py`, `quorum.py`, `record.sh` are NOT modified.
- **Tests:** `/tmp/rvenv/bin/python -m pytest` — Flask must be installed there first (`/tmp/rvenv/bin/pip install flask`; the venv is not PEP-668 restricted). Endpoint tests use `app.test_client()`; no real ffmpeg/OpenAI/network in unit tests.
- **`create_app(meetings_root)` factory** so tests point at a tmp root. Server binds **127.0.0.1 only**, no auth.
- **All fs writes stay within `meetings/<id>/`.** `<id>` and note `<name>` are sanitized to `[A-Za-z0-9_-]+`; anything else is rejected (no path traversal).
- **Status is derived from files:** no `recording.m4a` → `ready`; recording but no `minutes.md` → `recorded`; `minutes.md` present → `done`.
- **The backend shells out** — it never reimplements the pipeline. Generate argv: `[sys.executable, review.py, <recording>, <sorted notes/*.md>, "-t", <template.json>, "-o", <minutes.md>]`, run with `cwd`=repo root and inherited env (for `OPENAI_API_KEY`).
- **One recording at a time** (single module-level process handle). ffmpeg is SIGINT-stopped (finalizes the `.m4a`), mirroring `record.sh`.
- `meetings/` is gitignored (personal notes/recordings/minutes).

---

### Task 1: Backend skeleton — storage, meetings, templates, notes

**Files:**
- Create: `local/serve.py`
- Create: `local/static/.gitkeep` (placeholder; assets land in Task 4)
- Create: `test_local.py`
- Create: `requirements-local.txt`
- Create: `run-local.command`
- Modify: `.gitignore`

**Interfaces (produced, consumed by later tasks):**
- `serve.create_app(meetings_root: Path) -> Flask app`
- `serve._safe_name(s: str) -> str` — returns `s` if it matches `[A-Za-z0-9_-]+`, else raises `ValueError`.
- `serve._slugify(title: str) -> str` — lowercase, non-alphanumerics → `-`, trimmed.
- `serve._create_meeting(root, title, template) -> dict` — makes `<slug>/` (+ `-2`, `-3` on collision) + `meta.json`, returns `{id,title,date,template}`.
- `serve._list_meetings(root) -> list[dict]` — each `{id,title,date,template,status}`, newest-first by `meta.date` then id.
- `serve._meeting_status(dir: Path) -> str` — `ready`/`recorded`/`done` from file presence.
- `serve._list_templates(repo_root) -> list[dict]` — `[{stem,name,description}]` for `*.json` objects with `name`+`sections` (ignores the `registry` marker).

- [ ] **Step 1: Install Flask + scaffold**

Run: `/tmp/rvenv/bin/pip install flask`
Create `requirements-local.txt`:
```
flask
```
Add to `.gitignore`:
```
meetings/
```
Create `local/static/.gitkeep` (empty).

- [ ] **Step 2: Write the failing tests**

Create `test_local.py`:

```python
import json
from pathlib import Path
import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "local"))
import serve


def test_safe_name_accepts_and_rejects():
    assert serve._safe_name("weekly_review-2") == "weekly_review-2"
    for bad in ["../etc", "a/b", "a b", "a.b", ""]:
        with pytest.raises(ValueError):
            serve._safe_name(bad)


def test_slugify():
    assert serve._slugify("Weekly Review 31/6") == "weekly-review-31-6"


def test_create_and_list_meeting(tmp_path):
    m = serve._create_meeting(tmp_path, "Team Sync", "weekly_review")
    assert m["title"] == "Team Sync" and m["template"] == "weekly_review"
    d = tmp_path / m["id"]
    assert (d / "meta.json").exists() and (d / "notes").is_dir()
    # collision → distinct id
    m2 = serve._create_meeting(tmp_path, "Team Sync", "weekly_review")
    assert m2["id"] != m["id"]
    listed = serve._list_meetings(tmp_path)
    assert {x["id"] for x in listed} == {m["id"], m2["id"]}
    assert all(x["status"] == "ready" for x in listed)   # no recording yet


def test_meeting_status_progression(tmp_path):
    m = serve._create_meeting(tmp_path, "S", "weekly_review")
    d = tmp_path / m["id"]
    assert serve._meeting_status(d) == "ready"
    (d / "recording.m4a").write_bytes(b"x")
    assert serve._meeting_status(d) == "recorded"
    (d / "minutes.md").write_text("# M")
    assert serve._meeting_status(d) == "done"


def test_list_templates_filters(tmp_path):
    (tmp_path / "weekly_review.json").write_text(json.dumps(
        {"name": "Weekly Review v2", "description": "by project", "sections": [{"title": "X"}]}))
    (tmp_path / "notatemplate.json").write_text(json.dumps({"foo": 1}))
    out = serve._list_templates(tmp_path)
    assert out == [{"stem": "weekly_review", "name": "Weekly Review v2", "description": "by project"}]


def test_api_create_get_and_save_note(tmp_path):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    r = c.post("/api/meetings", json={"title": "Demo", "template": "weekly_review"})
    mid = r.get_json()["id"]
    c.put(f"/api/meetings/{mid}/notes/DataProject", json={"content": "# DataProject\nshipped"})
    got = c.get(f"/api/meetings/{mid}").get_json()
    assert got["notes"] == [{"name": "DataProject", "content": "# DataProject\nshipped"}]
    assert got["minutes"] == ""


def test_api_note_path_traversal_rejected(tmp_path):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "D", "template": "weekly_review"}).get_json()["id"]
    assert c.put(f"/api/meetings/{mid}/notes/..%2fevil", json={"content": "x"}).status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_local.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'serve'` / attribute errors.

- [ ] **Step 4: Implement `local/serve.py`**

```python
#!/usr/bin/env python3
"""Local single-user GUI backend. Stores meetings as folders, spawns ffmpeg for
recording, and shells out to review.py for generation. Bind 127.0.0.1 only."""
import json
import re
import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_name(s: str) -> str:
    if not isinstance(s, str) or not _NAME_RE.match(s):
        raise ValueError(f"unsafe name: {s!r}")
    return s


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s or "meeting"


def _meeting_status(d: Path) -> str:
    if (d / "minutes.md").exists():
        return "done"
    if (d / "recording.m4a").exists():
        return "recorded"
    return "ready"


def _create_meeting(root: Path, title: str, template: str) -> dict:
    root = Path(root)
    base = _slugify(title)
    slug, n = base, 1
    while (root / slug).exists():
        n += 1
        slug = f"{base}-{n}"
    d = root / slug
    (d / "notes").mkdir(parents=True)
    meta = {"title": title or "Untitled", "date": datetime.date.today().isoformat(),
            "template": template or "weekly_review", "created": datetime.datetime.now().isoformat(timespec="seconds")}
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    return {"id": slug, **{k: meta[k] for k in ("title", "date", "template")}}


def _read_meta(d: Path) -> dict:
    return json.loads((d / "meta.json").read_text())


def _list_meetings(root: Path) -> list:
    root = Path(root)
    out = []
    for d in root.iterdir() if root.exists() else []:
        if not (d / "meta.json").exists():
            continue
        meta = _read_meta(d)
        out.append({"id": d.name, "title": meta.get("title", d.name),
                    "date": meta.get("date", ""), "template": meta.get("template", ""),
                    "status": _meeting_status(d)})
    out.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    return out


def _list_templates(repo_root: Path) -> list:
    rows = []
    for p in sorted(Path(repo_root).glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(data, dict) and data.get("name") and "sections" in data:
            rows.append({"stem": p.stem, "name": data["name"], "description": data.get("description") or ""})
    return rows


def _notes(d: Path) -> list:
    nd = d / "notes"
    return [{"name": f.stem, "content": f.read_text()} for f in sorted(nd.glob("*.md"))] if nd.exists() else []


def create_app(meetings_root) -> Flask:
    root = Path(meetings_root)
    root.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__, static_folder=None)
    app.config["ROOT"] = root

    def _dir(mid):
        return root / _safe_name(mid)

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:fn>")
    def static_files(fn):
        return send_from_directory(STATIC, fn)

    @app.get("/api/templates")
    def templates():
        return jsonify(_list_templates(REPO_ROOT))

    @app.get("/api/meetings")
    def meetings():
        return jsonify(_list_meetings(root))

    @app.post("/api/meetings")
    def create():
        b = request.get_json(force=True)
        return jsonify(_create_meeting(root, b.get("title", ""), b.get("template", "weekly_review")))

    @app.get("/api/meetings/<mid>")
    def get_meeting(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        mins = (d / "minutes.md")
        return jsonify({"meta": {**_read_meta(d), "id": d.name, "status": _meeting_status(d)},
                        "notes": _notes(d),
                        "minutes": mins.read_text() if mins.exists() else ""})

    @app.put("/api/meetings/<mid>")
    def update_meeting(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        meta = _read_meta(d)
        b = request.get_json(force=True)
        for k in ("title", "template"):
            if k in b:
                meta[k] = b[k]
        (d / "meta.json").write_text(json.dumps(meta, indent=2))
        return jsonify({"ok": True})

    @app.put("/api/meetings/<mid>/notes/<name>")
    def save_note(mid, name):
        try:
            d, safe = _dir(mid), _safe_name(name)
        except ValueError:
            return ("bad name", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        (d / "notes").mkdir(exist_ok=True)
        (d / "notes" / f"{safe}.md").write_text(request.get_json(force=True).get("content", ""))
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    app = create_app(REPO_ROOT / "meetings")
    app.run(host="127.0.0.1", port=8765)
```

- [ ] **Step 5: `run-local.command`**

```bash
#!/usr/bin/env bash
# Double-click to launch the local GUI at http://localhost:8765
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
( sleep 1; open "http://localhost:8765" ) &
exec /tmp/rvenv/bin/python local/serve.py
```
Then `chmod +x run-local.command`.
(Note: uses the project venv python that has flask + the pipeline deps. If the user later makes a dedicated venv, update this path.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `/tmp/rvenv/bin/python -m pytest test_local.py -v`
Expected: PASS (7 tests). Existing suites untouched.

- [ ] **Step 7: Commit**

```bash
git add local/serve.py local/static/.gitkeep test_local.py requirements-local.txt run-local.command .gitignore
git commit -m "feat(local): Flask backend — meetings/templates/notes storage on folders"
```

---

### Task 2: Recording — device resolution + start/stop

**Files:**
- Modify: `local/serve.py`
- Modify: `test_local.py`

**Interfaces:**
- `serve._resolve_device_index(list_output: str, device_name: str) -> str | None` — parse an ffmpeg `-list_devices` blob (audio section) for `[N] <device_name>`.
- Endpoints: `GET /api/record/status`, `POST /api/meetings/<id>/record/start`, `POST /api/meetings/<id>/record/stop`.

- [ ] **Step 1: Write the failing tests**

Add to `test_local.py`:

```python
SAMPLE_DEVICES = """[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] Aggregate Device
[AVFoundation indev @ 0x1] [1] MacBook Air Microphone
[AVFoundation indev @ 0x1] [2] VB-Cable
"""

def test_resolve_device_index():
    assert serve._resolve_device_index(SAMPLE_DEVICES, "Aggregate Device") == "0"
    assert serve._resolve_device_index(SAMPLE_DEVICES, "VB-Cable") == "2"
    assert serve._resolve_device_index(SAMPLE_DEVICES, "Nope") is None


def test_record_status_and_single_recording(tmp_path, monkeypatch):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "R", "template": "weekly_review"}).get_json()["id"]
    assert c.get("/api/record/status").get_json() == {"recording": False, "meeting_id": None}

    class FakeProc:
        def __init__(self): self.signals = []
        def poll(self): return None
        def send_signal(self, s): self.signals.append(s)
        def wait(self, timeout=None): return 0
    fake = FakeProc()
    monkeypatch.setattr(serve, "_spawn_ffmpeg", lambda idx, out: fake)
    monkeypatch.setattr(serve, "_resolve_device_index", lambda blob, name: "0")
    monkeypatch.setattr(serve, "_list_audio", lambda: SAMPLE_DEVICES)

    assert c.post(f"/api/meetings/{mid}/record/start").status_code == 200
    assert c.get("/api/record/status").get_json()["recording"] is True
    # second start refused while one is active
    assert c.post(f"/api/meetings/{mid}/record/start").status_code == 409
    # stop finalizes (write a non-empty file to simulate ffmpeg output)
    (tmp_path / mid / "recording.m4a").write_bytes(b"AUDIO")
    assert c.post(f"/api/meetings/{mid}/record/stop").status_code == 200
    assert c.get("/api/record/status").get_json()["recording"] is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_local.py -k "device_index or record_status" -v`
Expected: FAIL — `_resolve_device_index`/record endpoints missing.

- [ ] **Step 3: Implement recording in `serve.py`**

Add near the top-level helpers:

```python
import subprocess
import signal

_DEVICE_LINE = re.compile(r"\[(\d+)\]\s+(.+?)\s*$")


def _list_audio() -> str:
    r = subprocess.run(["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                       capture_output=True, text=True)
    return r.stderr or r.stdout


def _resolve_device_index(list_output: str, device_name: str):
    in_audio = False
    for line in list_output.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio = True
            continue
        if "AVFoundation video devices:" in line:
            in_audio = False
            continue
        if in_audio:
            m = _DEVICE_LINE.search(line)
            if m and m.group(2) == device_name:
                return m.group(1)
    return None


def _spawn_ffmpeg(idx: str, out_path: Path):
    return subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-f", "avfoundation",
         "-i", f":{idx}", "-c:a", "aac", str(out_path)])
```

Inside `create_app`, add module-ish recording state on the app and the endpoints:

```python
    rec = {"proc": None, "meeting_id": None}   # single active recording

    @app.get("/api/record/status")
    def record_status():
        active = rec["proc"] is not None and rec["proc"].poll() is None
        return jsonify({"recording": active, "meeting_id": rec["meeting_id"] if active else None})

    @app.post("/api/meetings/<mid>/record/start")
    def record_start(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        if rec["proc"] is not None and rec["proc"].poll() is None:
            return ("already recording", 409)
        import os
        name = os.environ.get("RECORD_DEVICE", "Aggregate Device")
        idx = _resolve_device_index(_list_audio(), name)
        if idx is None:
            return (jsonify({"error": f"audio device {name!r} not found"}), 400)
        rec["proc"] = _spawn_ffmpeg(idx, d / "recording.m4a")
        rec["meeting_id"] = d.name
        return jsonify({"ok": True})

    @app.post("/api/meetings/<mid>/record/stop")
    def record_stop(mid):
        if rec["proc"] is None or rec["proc"].poll() is not None:
            rec["proc"], rec["meeting_id"] = None, None
            return ("not recording", 409)
        rec["proc"].send_signal(signal.SIGINT)
        try:
            rec["proc"].wait(timeout=10)
        except Exception:
            pass
        rec["proc"], rec["meeting_id"] = None, None
        f = _dir(mid) / "recording.m4a"
        if not (f.exists() and f.stat().st_size > 0):
            return (jsonify({"error": "recording produced no file"}), 500)
        return jsonify({"ok": True, "bytes": f.stat().st_size})
```

- [ ] **Step 4: Run tests, then full local suite**

Run: `/tmp/rvenv/bin/python -m pytest test_local.py -k "device_index or record_status" -v`
Expected: PASS.
Run: `/tmp/rvenv/bin/python -m pytest test_local.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add local/serve.py test_local.py
git commit -m "feat(local): in-app recording — device resolution + ffmpeg start/stop (one at a time)"
```

---

### Task 3: Generate + minutes

**Files:**
- Modify: `local/serve.py`
- Modify: `test_local.py`

**Interfaces:**
- `serve._generate_argv(python, review_py, recording, note_paths, template_path, out_path) -> list[str]` — pure; notes sorted.
- `serve._parse_projects(stdout: str) -> list[str]` — pull the `projects (N): a, b` line.
- Endpoints: `POST /api/meetings/<id>/generate`, `PUT /api/meetings/<id>/minutes`.

- [ ] **Step 1: Write the failing tests**

Add to `test_local.py`:

```python
def test_generate_argv_sorted_notes():
    argv = serve._generate_argv("py", "review.py", "rec.m4a",
                                ["notes/b.md", "notes/a.md"], "weekly_review.json", "out.md")
    assert argv == ["py", "review.py", "rec.m4a", "notes/a.md", "notes/b.md",
                    "-t", "weekly_review.json", "-o", "out.md"]


def test_parse_projects():
    assert serve._parse_projects("projects (3): A, B, C\nwrote out.md\n") == ["A", "B", "C"]
    assert serve._parse_projects("wrote out.md\n") == []


def test_generate_requires_recording(tmp_path):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "G", "template": "weekly_review"}).get_json()["id"]
    assert c.post(f"/api/meetings/{mid}/generate").status_code == 400   # no recording yet


def test_generate_runs_review_and_returns_minutes(tmp_path, monkeypatch):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "G", "template": "weekly_review"}).get_json()["id"]
    d = tmp_path / mid
    (d / "recording.m4a").write_bytes(b"AUDIO")
    (d / "notes" / "P.md").write_text("# P")
    def fake_run(argv, **kw):
        Path(argv[argv.index("-o") + 1]).write_text("# Minutes\nbody")   # simulate review.py writing -o
        class R: returncode = 0; stdout = "projects (1): P\nwrote out\n"; stderr = ""
        return R()
    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    r = c.post(f"/api/meetings/{mid}/generate").get_json()
    assert r["projects"] == ["P"] and "# Minutes" in r["minutes"]
    # edit + save
    c.put(f"/api/meetings/{mid}/minutes", json={"content": "# Edited"})
    assert c.get(f"/api/meetings/{mid}").get_json()["minutes"] == "# Edited"


def test_generate_failure_keeps_old_minutes(tmp_path, monkeypatch):
    app = serve.create_app(tmp_path)
    c = app.test_client()
    mid = c.post("/api/meetings", json={"title": "G", "template": "weekly_review"}).get_json()["id"]
    d = tmp_path / mid
    (d / "recording.m4a").write_bytes(b"A")
    (d / "minutes.md").write_text("# Old")
    def fail_run(argv, **kw):
        class R: returncode = 1; stdout = ""; stderr = "OPENAI_API_KEY not set."
        return R()
    monkeypatch.setattr(serve.subprocess, "run", fail_run)
    r = c.post(f"/api/meetings/{mid}/generate")
    assert r.status_code == 500 and "OPENAI_API_KEY" in r.get_json()["error"]
    assert (d / "minutes.md").read_text() == "# Old"     # not overwritten
```

- [ ] **Step 2: Run to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_local.py -k "generate or parse_projects" -v`
Expected: FAIL.

- [ ] **Step 3: Implement in `serve.py`**

Top-level helpers:

```python
import sys

_PROJECTS_RE = re.compile(r"^projects \(\d+\):\s*(.*)$", re.M)


def _generate_argv(python, review_py, recording, note_paths, template_path, out_path):
    return [python, str(review_py), str(recording), *sorted(str(p) for p in note_paths),
            "-t", str(template_path), "-o", str(out_path)]


def _parse_projects(stdout: str):
    m = _PROJECTS_RE.search(stdout or "")
    if not m or not m.group(1).strip():
        return []
    return [x.strip() for x in m.group(1).split(",") if x.strip()]
```

Endpoints inside `create_app`:

```python
    @app.post("/api/meetings/<mid>/generate")
    def generate(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        recording = d / "recording.m4a"
        if not recording.exists():
            return (jsonify({"error": "no recording yet"}), 400)
        meta = _read_meta(d)
        template = REPO_ROOT / f"{_safe_name(meta.get('template', 'weekly_review'))}.json"
        note_paths = sorted(str(p) for p in (d / "notes").glob("*.md"))
        out = d / "minutes.md"
        tmp_out = d / ".minutes.tmp.md"
        argv = _generate_argv(sys.executable, REPO_ROOT / "review.py", recording,
                              note_paths, template, tmp_out)
        r = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if r.returncode != 0 or not tmp_out.exists():
            if tmp_out.exists():
                tmp_out.unlink()
            return (jsonify({"error": (r.stderr or "generation failed").strip()}), 500)
        tmp_out.replace(out)     # commit only on success — old minutes survive a failure
        return jsonify({"ok": True, "projects": _parse_projects(r.stdout),
                        "minutes": out.read_text(),
                        "warnings": [l for l in (r.stderr or "").splitlines() if l.strip()]})

    @app.put("/api/meetings/<mid>/minutes")
    def save_minutes(mid):
        try:
            d = _dir(mid)
        except ValueError:
            return ("bad id", 400)
        if not (d / "meta.json").exists():
            return ("not found", 404)
        (d / "minutes.md").write_text(request.get_json(force=True).get("content", ""))
        return jsonify({"ok": True})
```

- [ ] **Step 4: Run tests, then full local suite**

Run: `/tmp/rvenv/bin/python -m pytest test_local.py -k "generate or parse_projects" -v`
Expected: PASS.
Run: `/tmp/rvenv/bin/python -m pytest test_local.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add local/serve.py test_local.py
git commit -m "feat(local): generate via review.py (temp-file commit-on-success) + editable minutes"
```

---

### Task 4: Frontend — one page reusing MeeTeam CSS

**Files:**
- Create: `local/static/index.html`
- Create: `local/static/app.js`
- Create: `local/static/styles.css` (copied from MeeTeam)
- Modify: `test_local.py` (one serving smoke test)

No DOM unit tests (browser-verified in Step 5); the one automated check is that `GET /` serves the page.

- [ ] **Step 1: Copy the stylesheet**

```bash
cp /Users/leleditit/Desktop/Github/MeeTeam/web/styles.css local/static/styles.css
```

- [ ] **Step 2: Serving smoke test**

Add to `test_local.py`:

```python
def test_index_served(tmp_path):
    app = serve.create_app(tmp_path)
    r = app.test_client().get("/")
    assert r.status_code == 200 and b"<html" in r.data.lower()
```

- [ ] **Step 3: `local/static/index.html`**

A single page linking `styles.css` + `app.js`, with these element ids the script drives (fill in layout/markup using MeeTeam's classes — `card`, `btn`, `btn-primary`, `input`, `label`, `pill`, `page-title`; two-column: `#meeting-list` sidebar + `#detail` panel):

- `#meeting-list` (ul), `#new-meeting-btn`
- `#m-title` (input), `#m-template` (select)
- `#notes-list` (container of note editors), `#add-note-btn`
- `#record-btn` (toggles Record/Stop), `#record-status` (text)
- `#generate-btn`, `#gen-status` (shows `projects (N)` + warnings)
- `#minutes-edit` (textarea), `#minutes-save-btn`, `#minutes-preview`

```html
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meeting Minutes — Local</title>
<link rel="stylesheet" href="/static/styles.css">
</head><body>
<div class="wrap" style="display:grid;grid-template-columns:280px 1fr;gap:20px;padding:20px;max-width:1100px;margin:0 auto;">
  <aside class="card">
    <button class="btn btn-primary" id="new-meeting-btn">New meeting</button>
    <ul id="meeting-list" style="list-style:none;padding:0;margin-top:14px;"></ul>
  </aside>
  <main id="detail" class="card"><p class="page-sub">Select or create a meeting.</p></main>
</div>
<template id="detail-tpl">
  <h1 class="page-title"><input class="input" id="m-title" placeholder="Meeting title"></h1>
  <label class="label">Template</label><select class="input" id="m-template"></select>
  <div class="label" style="margin-top:16px;">Pre-meeting notes</div>
  <div id="notes-list"></div>
  <button class="btn btn-ghost" id="add-note-btn">+ Add project note</button>
  <div class="label" style="margin-top:16px;">Recording</div>
  <button class="btn" id="record-btn">● Record</button> <span id="record-status" class="pill pill-muted"></span>
  <div style="margin-top:16px;"><button class="btn btn-primary" id="generate-btn">Generate minutes</button>
    <span id="gen-status" class="page-sub"></span></div>
  <div class="label" style="margin-top:16px;">Minutes</div>
  <textarea class="textarea" id="minutes-edit" rows="18" style="width:100%;"></textarea>
  <button class="btn" id="minutes-save-btn">Save minutes</button>
</template>
<script src="/static/app.js"></script>
</body></html>
```

- [ ] **Step 4: `local/static/app.js`**

Vanilla `fetch` wiring. Implement these behaviors (real code; keep it small and dependency-free):

```javascript
const api = (u, opts) => fetch(u, opts).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)));
let currentId = null;

async function loadMeetings() {
  const list = await api('/api/meetings');
  const ul = document.getElementById('meeting-list');
  ul.innerHTML = '';
  list.forEach(m => {
    const li = document.createElement('li');
    li.style.cssText = 'padding:8px;cursor:pointer;border-radius:8px;';
    li.innerHTML = `${m.title} <span class="pill pill-muted">${m.status}</span><br><small>${m.date}</small>`;
    li.onclick = () => openMeeting(m.id);
    ul.appendChild(li);
  });
}

async function loadTemplates(sel, chosen) {
  const t = await api('/api/templates');
  sel.innerHTML = t.map(x => `<option value="${x.stem}"${x.stem===chosen?' selected':''}>${x.name}</option>`).join('');
}

async function openMeeting(id) {
  currentId = id;
  const m = await api('/api/meetings/' + id);
  const detail = document.getElementById('detail');
  detail.innerHTML = '';
  detail.appendChild(document.getElementById('detail-tpl').content.cloneNode(true));
  document.getElementById('m-title').value = m.meta.title;
  await loadTemplates(document.getElementById('m-template'), m.meta.template);
  renderNotes(m.notes);
  document.getElementById('minutes-edit').value = m.minutes;
  wireDetail();
  refreshRecordStatus();
}

function renderNotes(notes) {
  const box = document.getElementById('notes-list');
  box.innerHTML = '';
  (notes.length ? notes : []).forEach(n => addNoteEditor(n.name, n.content));
}

function addNoteEditor(name, content) {
  const box = document.getElementById('notes-list');
  const wrap = document.createElement('div');
  wrap.innerHTML = `<input class="input" value="${name||''}" placeholder="Project name" style="margin:6px 0;">
    <textarea class="textarea" rows="4" style="width:100%;">${content||''}</textarea>`;
  const [nameEl, taEl] = wrap.querySelectorAll('input,textarea');
  const save = () => nameEl.value && api(`/api/meetings/${currentId}/notes/${encodeURIComponent(nameEl.value)}`,
    {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content: taEl.value})});
  nameEl.onchange = save; taEl.onchange = save;
  box.appendChild(wrap);
}

function wireDetail() {
  document.getElementById('m-title').onchange = e => save({title: e.target.value});
  document.getElementById('m-template').onchange = e => save({template: e.target.value});
  document.getElementById('add-note-btn').onclick = () => addNoteEditor('', '');
  document.getElementById('record-btn').onclick = toggleRecord;
  document.getElementById('generate-btn').onclick = generate;
  document.getElementById('minutes-save-btn').onclick = () =>
    api(`/api/meetings/${currentId}/minutes`, {method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({content: document.getElementById('minutes-edit').value})});
}

const save = body => api('/api/meetings/' + currentId, {method:'PUT',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});

async function refreshRecordStatus() {
  const s = await api('/api/record/status');
  const btn = document.getElementById('record-btn'); if (!btn) return;
  const mine = s.recording && s.meeting_id === currentId;
  btn.textContent = mine ? '■ Stop' : '● Record';
  document.getElementById('record-status').textContent = mine ? 'recording…' : '';
}

async function toggleRecord() {
  const s = await api('/api/record/status');
  const mine = s.recording && s.meeting_id === currentId;
  await api(`/api/meetings/${currentId}/record/${mine ? 'stop' : 'start'}`, {method:'POST'})
    .catch(e => alert(e.error || 'record failed'));
  refreshRecordStatus();
}

async function generate() {
  const st = document.getElementById('gen-status'); st.textContent = 'generating…';
  try {
    const r = await api(`/api/meetings/${currentId}/generate`, {method:'POST'});
    document.getElementById('minutes-edit').value = r.minutes;
    st.textContent = `projects (${r.projects.length}): ${r.projects.join(', ')}`;
    loadMeetings();
  } catch (e) { st.textContent = 'failed: ' + (e.error || 'error'); }
}

document.getElementById('new-meeting-btn').onclick = async () => {
  const t = await api('/api/templates');
  const m = await api('/api/meetings', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title:'New meeting', template: (t[0]||{}).stem || 'weekly_review'})});
  await loadMeetings(); openMeeting(m.id);
};

loadMeetings();
```

- [ ] **Step 5: Run the smoke test + manual browser check**

Run: `/tmp/rvenv/bin/python -m pytest test_local.py -q` → all pass.
Manual: `./run-local.command` → create a meeting, add a project note (type a name + text), pick a template, **● Record** ~15s of talking, **■ Stop**, **Generate**, confirm minutes render and **Save minutes** persists an edit. Record the result in the commit body.

- [ ] **Step 6: Commit**

```bash
git add local/static/index.html local/static/app.js local/static/styles.css test_local.py
git commit -m "feat(local): single-page GUI (meetings, notes, record, generate, edit minutes)"
```

---

## Self-Review

**Spec coverage:**
- Flask backend, 127.0.0.1, `create_app(root)` factory — Task 1. ✓
- Folder storage (`meta.json`, `notes/*.md`, `recording.m4a`, `minutes.md`) + derived status — Task 1. ✓
- Templates listing (name+sections, ignores `registry` marker) — Task 1. ✓
- Notes read/save with path-traversal rejection — Task 1. ✓
- In-app recording: device resolution + ffmpeg start/stop, one at a time — Task 2. ✓
- Generate via `review.py` (argv builder, temp-file commit-on-success, projects/warnings), editable minutes — Task 3. ✓
- Single page reusing MeeTeam CSS; record/generate/notes/minutes wired — Task 4. ✓
- `run-local.command` sources `.env`, launches, opens browser; `requirements-local.txt`; `.gitignore` meetings/ — Tasks 1/4. ✓
- `review.py`/Supabase untouched — no task edits them. ✓

**Placeholder scan:** No TBD/TODO. `<id>`/`<name>` in routes are Flask params; frontend markup is scaffolded with concrete ids the given `app.js` drives. Every backend step ships real, tested code.

**Type consistency:** `_create_meeting`→`{id,title,date,template}`; `_list_meetings` adds `status`; API `GET /api/meetings/<id>` returns `{meta,notes,minutes}` consumed verbatim by `openMeeting`. `_generate_argv(python,review_py,recording,note_paths,template_path,out_path)` matches its test and the `generate` endpoint call. `_resolve_device_index(list_output,name)` and `_spawn_ffmpeg(idx,out)` are the two monkeypatch seams the record test stubs. `_parse_projects` return feeds `r.projects` in `app.js`. Status strings `ready/recorded/done` are one set across `_meeting_status`, tests, and the sidebar pill. ✓

**Note on test isolation:** the record test stubs `_spawn_ffmpeg`/`_list_audio`/`_resolve_device_index`; the generate tests stub `subprocess.run`. No unit test spawns ffmpeg, calls OpenAI, or hits the network — only the manual E2E (Task 4 Step 5) does.
