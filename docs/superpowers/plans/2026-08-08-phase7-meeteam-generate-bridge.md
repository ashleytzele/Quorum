# Phase 7 — Generate minutes inside MeeTeam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Generate with Meetily" button in MeeTeam's admin minutes page that produces AI minutes (transcript + team notes → template) via a local bridge and fills MeeTeam's editor, so the admin finalizes with the existing Finalize.

**Architecture:** A thin local Flask server (`local/bridge.py`, `127.0.0.1`, CORS-allowed for the MeeTeam origin) shells the existing `review.py` (`--meetily-app <transcript> --meeting <notes> [-t template]`) and returns markdown. MeeTeam's `web/minutes.html` health-gates a Generate button, picks the Meetily recording (auto-matched, overridable), calls the bridge, drops the markdown into an editable box, and reuses Finalize to publish. `review.py`/`quorum.py`/`meetily_app.py` are unchanged.

**Tech Stack:** Python 3 + Flask (bridge), stdlib `subprocess`; MeeTeam static SPA (vanilla JS, `node:test`); the existing `review.py` pipeline.

## Global Constraints

- **Two repos.** meetily = `/Users/leleditit/Desktop/Ospit/meetily` (bridge). MeeTeam = `/Users/leleditit/Desktop/Github/MeeTeam` (frontend). Each task states its repo.
- meetily tests: `/tmp/rvenv/bin/python -m pytest` (flask installed). MeeTeam tests: `node --test lib.test.js` from the MeeTeam root.
- **The bridge shells `review.py` — it never re-implements the pipeline** and does not modify `review.py`/`quorum.py`/`meetily_app.py`. It reads the Meetily DB only through `meetily_app` (read-only) and writes minutes only through `review.py`'s existing paths; MeeTeam's Finalize does the actual `minutes_final` write.
- Bridge binds **`127.0.0.1` only**, no auth. CORS `Access-Control-Allow-Origin` = `MEETEAM_ORIGIN` env (default `http://localhost:8000`).
- **Graceful degrade:** if the bridge is unreachable, MeeTeam hides/disables the AI button and the existing structured-minutes flow is untouched. A `/generate` failure returns 500 with `review.py`'s stderr and leaves current minutes intact (no partial write).
- Tests stub `subprocess.run` and `meetily_app.list_meetings` — no real review.py/OpenAI/Supabase/Meetily DB in unit tests. PRODUCT.md in MeeTeam has a pre-existing unstaged edit — never stage it.

---

### Task 1: `local/bridge.py` — the local generate bridge

**Repo:** meetily.

**Files:**
- Create: `local/bridge.py`
- Create: `test_bridge.py`
- Create: `run-bridge.command`

**Interfaces:**
- `bridge.create_app() -> Flask` (factory).
- `bridge._generate_argv(python, review_py, meetily_id, meeting_id, template, out_path) -> list[str]` — PURE.
- `bridge._parse_projects(stdout) -> list[str]` — PURE.
- Endpoints: `GET /health`, `GET /recordings`, `POST /generate` (+`OPTIONS`).

- [ ] **Step 1: Write the failing tests**

Create `test_bridge.py`:

```python
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent / "local"))
import bridge


def test_generate_argv_with_and_without_template():
    a = bridge._generate_argv("py", "review.py", "m1", "q1", "weekly_review", "/tmp/o.md")
    assert a == ["py", "review.py", "--meetily-app", "m1", "--meeting", "q1",
                 "-t", str(bridge.REPO_ROOT / "weekly_review.json"), "-o", "/tmp/o.md"]
    b = bridge._generate_argv("py", "review.py", "m1", "q1", None, "/tmp/o.md")
    assert b == ["py", "review.py", "--meetily-app", "m1", "--meeting", "q1", "-o", "/tmp/o.md"]


def test_parse_projects():
    assert bridge._parse_projects("projects (2): A, B\nwrote x\n") == ["A", "B"]
    assert bridge._parse_projects("nothing\n") == []


def test_health_and_cors():
    c = bridge.create_app().test_client()
    r = c.get("/health")
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    assert r.headers["Access-Control-Allow-Origin"]  # CORS header present


def test_generate_preflight_options():
    c = bridge.create_app().test_client()
    r = c.open("/generate", method="OPTIONS")
    assert r.status_code in (200, 204)
    assert r.headers["Access-Control-Allow-Origin"]


def test_recordings_via_stub(monkeypatch):
    import meetily_app
    monkeypatch.setattr(meetily_app, "list_meetings",
                        lambda *a, **k: [{"id": "m1", "title": "Alpha", "created_at": "2026-07-25"}])
    c = bridge.create_app().test_client()
    assert c.get("/recordings").get_json() == [{"id": "m1", "title": "Alpha", "created_at": "2026-07-25"}]


def test_generate_missing_ids_400():
    c = bridge.create_app().test_client()
    assert c.post("/generate", json={"meeting_id": "q1"}).status_code == 400


def test_generate_success(monkeypatch):
    def fake_run(argv, **kw):
        Path(argv[argv.index("-o") + 1]).write_text("# AI Minutes\nbody")
        class R: returncode = 0; stdout = "projects (1): P\nwrote o\n"; stderr = ""
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate", json={"meeting_id": "q1", "meetily_id": "m1", "template": "weekly_review"}).get_json()
    assert "# AI Minutes" in r["markdown"] and r["projects"] == ["P"]


def test_generate_failure_500(monkeypatch):
    def fail_run(argv, **kw):
        class R: returncode = 1; stdout = ""; stderr = "No transcript found."
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fail_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate", json={"meeting_id": "q1", "meetily_id": "m1"})
    assert r.status_code == 500 and "No transcript" in r.get_json()["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bridge'`.

- [ ] **Step 3: Write `local/bridge.py`**

```python
#!/usr/bin/env python3
"""Local bridge for MeeTeam's admin minutes page. Shells the existing review.py
(--meetily-app transcript + --meeting team-notes + template) and returns markdown.
Binds 127.0.0.1 only; CORS-allows the MeeTeam origin. Reuses review.py/quorum/
meetily_app unchanged — this file adds no pipeline logic."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))          # so `import meetily_app` resolves
MEETEAM_ORIGIN = os.environ.get("MEETEAM_ORIGIN", "http://localhost:8000")
_PROJECTS_RE = re.compile(r"^projects \(\d+\):\s*(.*)$", re.M)


def _generate_argv(python, review_py, meetily_id, meeting_id, template, out_path):
    argv = [python, str(review_py), "--meetily-app", meetily_id, "--meeting", meeting_id]
    if template:
        argv += ["-t", str(REPO_ROOT / f"{template}.json")]
    argv += ["-o", str(out_path)]
    return argv


def _parse_projects(stdout):
    m = _PROJECTS_RE.search(stdout or "")
    if not m or not m.group(1).strip():
        return []
    return [x.strip() for x in m.group(1).split(",") if x.strip()]


def create_app() -> Flask:
    app = Flask(__name__)

    @app.after_request
    def _cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = MEETEAM_ORIGIN
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/recordings")
    def recordings():
        import meetily_app
        return jsonify(meetily_app.list_meetings())

    @app.route("/generate", methods=["POST", "OPTIONS"])
    def generate():
        if request.method == "OPTIONS":
            return ("", 204)
        b = request.get_json(force=True) or {}
        meeting_id, meetily_id = b.get("meeting_id"), b.get("meetily_id")
        if not meeting_id or not meetily_id:
            return (jsonify({"error": "meeting_id and meetily_id required"}), 400)
        fd, tmp = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        out = Path(tmp)
        try:
            argv = _generate_argv(sys.executable, REPO_ROOT / "review.py",
                                  meetily_id, meeting_id, b.get("template"), out)
            r = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True)
            if r.returncode != 0 or not out.exists() or not out.read_text().strip():
                return (jsonify({"error": (r.stderr or "generation failed").strip()}), 500)
            markdown = out.read_text()
        finally:
            if out.exists():
                out.unlink()
        return jsonify({"ok": True, "markdown": markdown,
                        "projects": _parse_projects(r.stdout),
                        "warnings": [l for l in (r.stderr or "").splitlines() if l.strip()]})

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8899)
```

- [ ] **Step 4: `run-bridge.command`**

```bash
#!/usr/bin/env bash
# Double-click to run the MeeTeam generate bridge at http://localhost:8899
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating .venv and installing deps…"
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements-local.txt
fi
set -a; [ -f .env ] && . ./.env; set +a
echo "Bridge on http://localhost:8899 — keep this window open while using MeeTeam."
exec ./.venv/bin/python local/bridge.py
```
Then `chmod +x run-bridge.command`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `/tmp/rvenv/bin/python -m pytest test_bridge.py -v`
Expected: PASS (8 tests). Then the full meetily suite stays green:
Run: `/tmp/rvenv/bin/python -m pytest test_bridge.py test_review.py test_quorum.py test_meetily_app.py test_local.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add local/bridge.py test_bridge.py run-bridge.command
git commit -m "feat(bridge): local Flask bridge — /health /recordings /generate (shells review.py), CORS for MeeTeam"
```

---

### Task 2: MeeTeam — "Generate with Meetily" in the minutes page

**Repo:** MeeTeam (`/Users/leleditit/Desktop/Github/MeeTeam`).

**Files:**
- Modify: `web/config.js` (BRIDGE_URL)
- Modify: `web/lib.js` (`matchRecording` helper) + `lib.test.js`
- Modify: `web/minutes.html` (health-gate, button, picker, AI textarea, `minutesMarkdown` override)

**Interfaces:**
- `matchRecording(meeting, recordings) -> recording|null` — pick the recording whose date is nearest the meeting's `meeting_date` (tie-break: title contains, else newest). Pure, tested.

- [ ] **Step 1: Add the bridge URL**

In `web/config.js`, add:
```javascript
window.BRIDGE_URL = 'http://localhost:8899';   // local Meetily generate bridge (run-bridge.command)
```

- [ ] **Step 2: Write the failing `matchRecording` test**

Add to `lib.test.js`:
```javascript
const { matchRecording } = require('./web/lib.js');

test('matchRecording picks nearest date, null on empty', () => {
  const recs = [
    { id: 'a', title: 'Standup', created_at: '2026-07-20T10:00:00Z' },
    { id: 'b', title: 'Weekly Review', created_at: '2026-07-24T10:00:00Z' },
  ];
  assert.equal(matchRecording({ meeting_date: '2026-07-24', title: 'Weekly Review' }, recs).id, 'b');
  assert.equal(matchRecording({ meeting_date: '2026-07-19', title: 'x' }, recs).id, 'a');
  assert.equal(matchRecording({ meeting_date: '2026-07-24' }, []), null);
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: FAIL — `matchRecording is not a function`.

- [ ] **Step 4: Implement `matchRecording` in `web/lib.js`**

Add the function and export it (extend the existing `module.exports`):
```javascript
function matchRecording(meeting, recordings) {
  if (!recordings || !recordings.length) return null;
  const target = meeting && meeting.meeting_date ? new Date(meeting.meeting_date + 'T00:00').getTime() : NaN;
  let best = null, bestScore = Infinity;
  recordings.forEach(function (r) {
    const t = new Date(r.created_at).getTime();
    const dateDist = isNaN(target) || isNaN(t) ? 1e15 : Math.abs(t - target);
    const titleBonus = meeting && meeting.title && r.title &&
      r.title.toLowerCase().includes(meeting.title.toLowerCase()) ? -1 : 0;
    const score = dateDist + titleBonus;
    if (score < bestScore) { bestScore = score; best = r; }
  });
  return best;
}
```
```javascript
  module.exports = { classifyFile, isAccepted, groupFilesByTeam, buildMinutesMarkdown, meetingStatus, matchRecording };
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: PASS (existing tests still green).

- [ ] **Step 6: Add the markup in `web/minutes.html`**

Beside the existing header buttons (`#generate`, `#print`, `#finalize`, ~lines 29–39) add an AI Generate button:
```html
        <button class="btn btn-ghost" id="gen-ai" type="button" style="display:none;">Generate with Meetily</button>
        <select class="input" id="ai-recording" style="display:none;max-width:240px;"></select>
```
In the editor column (near the `#decisions` field, ~line 58) add the AI minutes box (hidden until generated):
```html
        <div id="ai-wrap" style="display:none;">
          <label class="label">AI minutes (editable — review before finalizing)</label>
          <textarea class="textarea" id="ai-minutes" rows="16" style="width:100%;"></textarea>
          <div class="page-sub" id="ai-status"></div>
        </div>
```

- [ ] **Step 7: Wire the bridge in `minutes.html`'s script**

Add inside the existing IIFE (after `meeting` is loaded and the field consts exist). This health-gates the button, populates the recording picker, generates, and routes Finalize to the AI markdown:

```javascript
  let aiMinutes = null;   // when set, Finalize publishes this instead of the structured minutes
  const genAiBtn = document.getElementById('gen-ai');
  const recSel = document.getElementById('ai-recording');
  const aiWrap = document.getElementById('ai-wrap');
  const aiText = document.getElementById('ai-minutes');
  const aiStatus = document.getElementById('ai-status');

  // Health-gate: only show the AI button if the local bridge is running.
  try {
    const h = await fetch(window.BRIDGE_URL + '/health').then(r => r.json());
    if (h && h.ok) {
      const recs = await fetch(window.BRIDGE_URL + '/recordings').then(r => r.json());
      recSel.innerHTML = (recs || []).map(r =>
        '<option value="' + esc(r.id) + '">' + esc(r.title || r.id) + '</option>').join('');
      const m = matchRecording(meeting, recs || []);
      if (m) recSel.value = m.id;
      if ((recs || []).length) { genAiBtn.style.display = ''; recSel.style.display = ''; }
    }
  } catch (e) { /* bridge not running — leave AI button hidden, structured flow works */ }

  aiText.addEventListener('input', function () { aiMinutes = aiText.value; });

  genAiBtn.addEventListener('click', async function () {
    aiStatus.textContent = 'generating…'; aiWrap.style.display = '';
    try {
      const res = await fetch(window.BRIDGE_URL + '/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting_id: meeting.id, meetily_id: recSel.value, template: meeting.template || null })
      }).then(async r => r.ok ? r.json() : Promise.reject(await r.json()));
      aiMinutes = res.markdown;
      aiText.value = res.markdown;
      document.getElementById('d-body').innerHTML = md.render(res.markdown);
      aiStatus.textContent = 'projects (' + res.projects.length + '): ' + res.projects.join(', ');
    } catch (e) {
      aiStatus.textContent = 'failed: ' + ((e && e.error) || 'error');
    }
  });
```

Then make Finalize publish the AI minutes when present — add this as the FIRST line of the existing `minutesMarkdown()` function:
```javascript
    if (aiMinutes && aiMinutes.trim()) return aiMinutes;
```
(`esc` and `md` already exist in this scope; `matchRecording` comes from `lib.js`, already loaded at minutes.html line 84.)

- [ ] **Step 8: Manual browser verification**

Start `run-bridge.command` (meetily) and `run.command` (MeeTeam). Open a real meeting's minutes page as admin: the **Generate with Meetily** button appears (bridge up), the recording picker is auto-matched; click it → AI minutes fill the box + preview + `projects (N)`; edit a line; **Finalize & archive** → confirm History shows the AI minutes (the edited markdown). Then stop the bridge and reload → the AI button is hidden and the structured flow still works. Record the result in the commit body.

- [ ] **Step 9: Commit (MeeTeam repo)**

```bash
cd /Users/leleditit/Desktop/Github/MeeTeam
git add web/config.js web/lib.js lib.test.js web/minutes.html
git commit -m "feat(minutes): Generate with Meetily — local-bridge AI minutes into the editor, reuse Finalize"
```

---

## Self-Review

**Spec coverage:**
- Local bridge (`/health`, `/recordings`, `/generate`) shelling `review.py`, 127.0.0.1, CORS — Task 1. ✓
- `run-bridge.command` sources `.env`, repo-local `.venv` — Task 1 Step 4. ✓
- Graceful degrade (health-gate hides the button; structured flow untouched) — Task 2 Step 7. ✓
- `/generate` failure → 500 + stderr, no partial write (temp-file, only return on success) — Task 1 Step 3 + test. ✓
- Recording auto-match, overridable via dropdown — Task 2 `matchRecording` + picker. ✓
- AI markdown fills an editable box + preview; Finalize publishes it via `minutesMarkdown()` override — Task 2 Steps 6–7. ✓
- `review.py`/`quorum.py`/`meetily_app.py` untouched; bridge shells them — no task edits them. ✓
- CORS origin configurable (`MEETEAM_ORIGIN`) / `BRIDGE_URL` in config.js — Tasks 1/2. ✓

**Placeholder scan:** No TBD/TODO. `<transcript>`/`<notes>` in prose are descriptive; every code step ships real code. `<meetily_id>` etc. are runtime values.

**Type consistency:** `_generate_argv(python, review_py, meetily_id, meeting_id, template, out_path)` matches its test and the `/generate` call. `/recordings` returns `meetily_app.list_meetings()` shape `[{id,title,created_at}]` consumed by `matchRecording(meeting, recordings)` and the `<option>` render. `/generate` returns `{markdown, projects, warnings}` consumed verbatim in Step 7. `aiMinutes` (string|null) gates `minutesMarkdown()`. `meeting.template` (Phase-3 column) passed as the optional template stem. ✓

**Cross-repo note:** Task 1 commits in meetily; Task 2 in MeeTeam (reviews diff the MeeTeam repo). The bridge↔MeeTeam CORS wiring and the whole AI-minutes flow are browser-verified (Task 2 Step 8) — the one manual, un-unit-testable seam, plus the real `review.py` generation behind `/generate`.
