# Phase 4 — Meeting lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each meeting an explicit `status` so MeeTeam becomes a live dashboard (status pill + the exact Mac command per meeting) and Meetily reports progress back, while folding during-meeting notes into the minutes and unifying VIP into the same pipeline.

**Architecture:** One new `meetings.status` column drives everything. Meetily (`review.py`/`quorum.py`) writes status at each stage it owns (`processing` → `draft` → `published`), additionally reads each team's during-meeting `notes.content`, and no longer hard-fails on empty notes. MeeTeam generalizes the Phase-3 badge into a 6-state lifecycle pill and adds a copy-the-command card plus small status controls. No daemon, no in-app compute — the admin still runs the Mac command.

**Tech Stack:** Python 3 (`review.py`, `quorum.py`, `pytest`), Supabase Python client (lazy), MeeTeam static SPA (vanilla JS, `node:test`, OKLCH-token CSS).

## Global Constraints

- **Two repos.** meetily = `/Users/leleditit/Desktop/Ospit/meetily`. MeeTeam = `/Users/leleditit/Desktop/Github/MeeTeam`. Each task states its repo; commits land there.
- **meetily tests:** `/tmp/rvenv/bin/python -m pytest` (venv has supabase/markitdown/openai/pytest; system python3 is PEP-668, no pip). **MeeTeam tests:** `node --test lib.test.js` from the MeeTeam root.
- **The `supabase` client is imported INSIDE functions** in `quorum.py` (lazy) — unit tests need no package/network.
- **Six status values, exactly:** `setup`, `collecting`, `ready`, `processing`, `draft`, `published`.
- **Ownership:** MeeTeam advances `setup`/`collecting`/`ready`; Meetily advances `processing`/`draft`/`published`. `is_active`/`minutes_final` stay Phase-2 source of truth for archive/History; `published` ⇔ `is_active=false` + `minutes_final` set.
- **All Meetily status writes are best-effort:** wrapped in try/except, warn to stderr, never block a generate or publish.
- **`fetch_notes` no longer hard-fails on empty input** — it warns and returns `""` (enables recording-only / VIP-no-notes). `--publish` still refuses empty markdown / no-match id (Phase 2 unchanged).
- **Phase 1–3 behavior + tests must keep passing.** New work is additive except the deliberate `minutesStatus` → `meetingStatus` rename (Task 3), whose single call site + test are updated in the same task.

---

### Task 1: Meetily — status column + status writes

**Repo:** meetily.

**Files:**
- Create: `docs/supabase-phase4.sql`
- Modify: `quorum.py` (`set_meeting_status`; `publish_minutes` sets `status='published'`)
- Modify: `review.py` (`_set_status_via_quorum`, `_status_best_effort`, `processing`/`draft` writes)
- Modify: `test_quorum.py`, `test_review.py`

**Interfaces:**
- Produces:
  - `quorum.set_meeting_status(meeting_id: str, status: str) -> list` — `update meetings set status=<status> where id=<id>`; returns updated rows.
  - `review._set_status_via_quorum(meeting_id, status)` — thin `import quorum` wrapper (test stub point).
  - `review._status_best_effort(meeting_id, status)` — calls the wrapper in try/except, warns on failure.

- [ ] **Step 1: Manual Supabase SQL (user runs once in the dashboard; save it for the record)**

Create `docs/supabase-phase4.sql`:

```sql
-- Phase 4: meeting lifecycle status
alter table meetings add column if not exists status text default 'setup';

-- one-time reclassify of existing rows to a truthful state
update meetings set status = case
    when is_active = false then 'published'
    when minutes_final is not null and minutes_final <> '' then 'draft'
    else 'collecting'
  end;
```

(The unit tests below stub the network and don't need the column; the live/manual runs do.)

- [ ] **Step 2: Write the failing tests**

Add to `test_quorum.py`:

```python
def test_set_meeting_status_builds_update(monkeypatch):
    import quorum
    captured = {}
    class FakeExec:
        def __init__(self, data): self.data = data
    class FakeTable:
        def update(self, payload): captured["payload"] = payload; return self
        def eq(self, col, val): captured["eq"] = (col, val); return self
        def execute(self): return FakeExec([{"id": captured["eq"][1], "status": captured["payload"]["status"]}])
    class FakeClient:
        def table(self, name): captured["table"] = name; return FakeTable()
    monkeypatch.setattr(quorum, "_client", lambda: FakeClient())
    out = quorum.set_meeting_status("MID-1", "processing")
    assert captured["table"] == "meetings"
    assert captured["payload"] == {"status": "processing"}
    assert captured["eq"] == ("id", "MID-1")
    assert out == [{"id": "MID-1", "status": "processing"}]


def test_publish_minutes_sets_published_status(monkeypatch):
    import quorum
    captured = {}
    class FakeExec:
        def __init__(self, data): self.data = data
    class FakeTable:
        def update(self, payload): captured["payload"] = payload; return self
        def eq(self, col, val): return self
        def execute(self): return FakeExec([{"id": "MID-1"}])
    class FakeClient:
        def table(self, name): return FakeTable()
    monkeypatch.setattr(quorum, "_client", lambda: FakeClient())
    quorum.publish_minutes("MID-1", "# Minutes")
    assert captured["payload"]["status"] == "published"
    assert captured["payload"]["is_active"] is False
    assert captured["payload"]["minutes_final"] == "# Minutes"
```

Add to `test_review.py`:

```python
def test_meeting_generate_writes_processing_then_draft(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QNOTE")
    monkeypatch.setattr(review, "_meeting_template_via_quorum", lambda mid: None)
    monkeypatch.setattr(review, "_sync_templates_via_quorum", lambda rows: rows)
    calls = []
    monkeypatch.setattr(review, "_set_status_via_quorum", lambda mid, s: calls.append((mid, s)))
    monkeypatch.setattr(review, "transcribe", lambda rec, clean: "hello transcript")
    monkeypatch.setattr(review, "call_openai", lambda messages, model: "# Minutes\nbody")
    audio = tmp_path / "a.m4a"; audio.write_text("x")
    template = tmp_path / "weekly_review.json"
    template.write_text(json.dumps({"name": "T", "description": "d",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    out = tmp_path / "o.md"
    review.main([str(audio), "-t", str(template), "--meeting", "MID-1", "-o", str(out)])
    assert calls == [("MID-1", "processing"), ("MID-1", "draft")]


def test_status_write_failure_does_not_abort_generate(tmp_path, monkeypatch):
    import review
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QNOTE")
    monkeypatch.setattr(review, "_meeting_template_via_quorum", lambda mid: None)
    monkeypatch.setattr(review, "_sync_templates_via_quorum", lambda rows: rows)
    def boom(mid, s): raise RuntimeError("supabase down")
    monkeypatch.setattr(review, "_set_status_via_quorum", boom)
    monkeypatch.setattr(review, "transcribe", lambda rec, clean: "hi")
    monkeypatch.setattr(review, "call_openai", lambda messages, model: "# M")
    audio = tmp_path / "a.m4a"; audio.write_text("x")
    template = tmp_path / "weekly_review.json"
    template.write_text(json.dumps({"name": "T", "description": "d",
        "sections": [{"title": "X", "instruction": "i", "format": "string"}]}))
    out = tmp_path / "o.md"
    review.main([str(audio), "-t", str(template), "--meeting", "MID-1", "-o", str(out)])
    assert out.read_text() == "# M"      # generate completed despite status failures
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_quorum.py test_review.py -k "set_meeting_status or publish_minutes_sets or writes_processing or status_write_failure" -v`
Expected: FAIL — `AttributeError` on the new functions / `calls` empty.

- [ ] **Step 4: Implement in `quorum.py`**

Add `set_meeting_status` (after `get_meeting_template`):

```python
def set_meeting_status(meeting_id: str, status: str) -> list:
    """update meetings set status=<status> where id=<meeting_id>."""
    c = _client()
    res = c.table("meetings").update({"status": status}).eq("id", meeting_id).execute()
    return res.data or []
```

In `publish_minutes`, add `status` to the update payload:

```python
    res = (c.table("meetings")
           .update({"minutes_final": markdown, "is_active": False, "status": "published"})
           .eq("id", meeting_id).execute())
```

- [ ] **Step 5: Implement in `review.py`**

Near the other `_via_quorum` wrappers add:

```python
def _set_status_via_quorum(meeting_id, status):
    import quorum
    return quorum.set_meeting_status(meeting_id, status)


def _status_best_effort(meeting_id, status):
    try:
        _set_status_via_quorum(meeting_id, status)
    except Exception as e:
        print(f"warning: status update to '{status}' skipped ({e})", file=sys.stderr)
```

In `main`, inside the `if args.meeting:` block, at the end of the `if not args.dry_run:` branch (after the template-sync try/except), add:

```python
            _status_best_effort(args.meeting, "processing")
```

And after the output is written (`print(f"wrote {out}")`), add:

```python
    if args.meeting and not args.dry_run:
        _status_best_effort(args.meeting, "draft")
```

- [ ] **Step 6: Run tests to verify they pass, then the full suite**

Run: `/tmp/rvenv/bin/python -m pytest test_quorum.py test_review.py -k "set_meeting_status or publish_minutes_sets or writes_processing or status_write_failure" -v`
Expected: PASS.
Run: `/tmp/rvenv/bin/python -m pytest test_review.py test_quorum.py -q`
Expected: all pass (Phases 1–3 unaffected).

- [ ] **Step 7: Commit**

```bash
git add docs/supabase-phase4.sql quorum.py review.py test_quorum.py test_review.py
git commit -m "feat: meeting lifecycle status — set_meeting_status, publish->published, review.py writes processing/draft"
```

---

### Task 2: Meetily — during-meeting notes feed the minutes + empty-notes relaxation

**Repo:** meetily.

**Files:**
- Modify: `quorum.py` (`_combine_inputs` gains during-notes; `fetch_notes` reads `content`, no longer exits on empty)
- Modify: `test_quorum.py`

**Interfaces:**
- Changed: `quorum._combine_inputs(pre_notes, file_texts, links, during_notes=())` — adds an optional `during_notes` list of `(team, text)` emitted under `--- <team> (during-meeting note) ---`, right after the pre-meeting notes. Default `()` keeps existing callers working.
- Changed: `quorum.fetch_notes(meeting_id) -> str` — selects `pre_note, content, teams(name)`; on empty combined input, warns to stderr and returns `""` (no `SystemExit`).

- [ ] **Step 1: Write the failing tests**

Add to `test_quorum.py`:

```python
def test_combine_inputs_includes_during_notes():
    from quorum import _combine_inputs
    out = _combine_inputs(
        pre_notes=[("WCE", "pre stuff")],
        file_texts=[],
        links=[],
        during_notes=[("WCE", "live decision: ship Friday"), ("MSAR", "  ")],
    )
    assert "--- WCE (pre-meeting note) ---" in out and "pre stuff" in out
    assert "--- WCE (during-meeting note) ---" in out and "live decision: ship Friday" in out
    assert "MSAR" not in out          # blank during-note dropped
    # during-note for a team appears after that team's pre-note block
    assert out.index("(pre-meeting note)") < out.index("(during-meeting note)")


def test_combine_inputs_backward_compatible_without_during():
    from quorum import _combine_inputs
    out = _combine_inputs(pre_notes=[("WCE", "x")], file_texts=[], links=[])
    assert "--- WCE (pre-meeting note) ---" in out and "during-meeting" not in out


def test_fetch_notes_empty_warns_and_returns_blank(monkeypatch, capsys):
    import quorum
    class FakeExec:
        def __init__(self, data): self.data = data
    class FakeTable:
        def select(self, *a): return self
        def eq(self, *a): return self
        def execute(self): return FakeExec([])          # no notes, no submissions
    class FakeClient:
        def table(self, name): return FakeTable()
    monkeypatch.setattr(quorum, "_client", lambda: FakeClient())
    result = quorum.fetch_notes("MID-empty")             # must NOT raise SystemExit
    assert result == ""
    assert "no notes" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_quorum.py -k "during_notes or backward_compatible or empty_warns" -v`
Expected: FAIL — `_combine_inputs` has no `during_notes`; `fetch_notes` still `SystemExit`s on empty.

- [ ] **Step 3: Extend `_combine_inputs`**

Change the signature and emit during-notes right after the pre-meeting loop:

```python
def _combine_inputs(pre_notes, file_texts, links, during_notes=()) -> str:
    parts = []
    for team, text in pre_notes:
        if text and text.strip():
            parts.append(f"--- {team} (pre-meeting note) ---")
            parts.append(text.strip())
            parts.append("")
    for team, text in during_notes:
        if text and text.strip():
            parts.append(f"--- {team} (during-meeting note) ---")
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
```

- [ ] **Step 4: Read `content` in `fetch_notes`, relax the empty guard**

Change the notes select and build `during_notes`; replace the empty `sys.exit` with a warn + return:

```python
def fetch_notes(meeting_id: str) -> str:
    c = _client()
    note_rows = (c.table("notes").select("pre_note, content, teams(name)")
                 .eq("meeting_id", meeting_id).execute().data) or []
    pre_notes = [((r.get("teams") or {}).get("name") or "Team",
                  r.get("pre_note") or "") for r in note_rows]
    during_notes = [((r.get("teams") or {}).get("name") or "Team",
                     r.get("content") or "") for r in note_rows]
```

Leave the `submissions`/`file_texts`/`links` block unchanged, then the tail becomes:

```python
    combined = _combine_inputs(pre_notes, file_texts, links, during_notes)
    if not combined:
        print(f"warning: no notes or submissions for meeting {meeting_id} — "
              f"generating from the recording alone.", file=sys.stderr)
        return ""
    return combined
```

- [ ] **Step 5: Run the new tests, then the whole suite**

Run: `/tmp/rvenv/bin/python -m pytest test_quorum.py -k "during_notes or backward_compatible or empty_warns" -v`
Expected: PASS.
Run: `/tmp/rvenv/bin/python -m pytest test_review.py test_quorum.py -q`
Expected: all pass (the Phase-2 `test_combine_inputs_*` still green — the new param has a default).

- [ ] **Step 6: Commit**

```bash
git add quorum.py test_quorum.py
git commit -m "feat: fetch_notes folds in during-meeting notes.content; empty notes warn (recording-only) instead of exit"
```

---

### Task 3: MeeTeam — 6-state lifecycle pill

**Repo:** MeeTeam (`/Users/leleditit/Desktop/Github/MeeTeam`).

**Files:**
- Modify: `web/lib.js` (replace `minutesStatus` with `meetingStatus`)
- Modify: `lib.test.js`
- Modify: `web/styles.css` (six `.mt-status-*` rules)
- Modify: `web/admin.html` (renderTabs uses `meetingStatus`)

**Interfaces:**
- Produces: `meetingStatus(m) -> { key, label, cls }` for the six states, with a derive fallback for rows lacking `status`.

- [ ] **Step 1: Write the failing test**

Replace the Phase-3 `minutesStatus` test in `lib.test.js` with:

```javascript
const { meetingStatus } = require('./web/lib.js');

test('meetingStatus maps each explicit status', () => {
  assert.equal(meetingStatus({ status: 'setup' }).label, 'Setup');
  assert.equal(meetingStatus({ status: 'collecting' }).label, 'Collecting');
  assert.equal(meetingStatus({ status: 'ready' }).label, 'Ready to record');
  assert.equal(meetingStatus({ status: 'processing' }).label, 'Processing');
  assert.equal(meetingStatus({ status: 'draft' }).label, 'Draft ready');
  assert.equal(meetingStatus({ status: 'published' }).label, 'Published');
  assert.equal(meetingStatus({ status: 'published' }).cls, 'published');
});

test('meetingStatus derives status for un-migrated rows', () => {
  assert.equal(meetingStatus({ is_active: false }).label, 'Published');
  assert.equal(meetingStatus({ is_active: true, minutes_final: '# M' }).label, 'Draft ready');
  assert.equal(meetingStatus({ is_active: true }).label, 'Collecting');
  assert.equal(meetingStatus({}).label, 'Collecting');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: FAIL — `meetingStatus is not a function`.

- [ ] **Step 3: Implement `meetingStatus` in `web/lib.js`**

Replace the `minutesStatus` function with:

```javascript
function meetingStatus(m) {
  const S = {
    setup:      { key: 'setup',      label: 'Setup',           cls: 'setup' },
    collecting: { key: 'collecting', label: 'Collecting',      cls: 'collecting' },
    ready:      { key: 'ready',      label: 'Ready to record', cls: 'ready' },
    processing: { key: 'processing', label: 'Processing',      cls: 'processing' },
    draft:      { key: 'draft',      label: 'Draft ready',     cls: 'draft' },
    published:  { key: 'published',  label: 'Published',       cls: 'published' },
  };
  if (m && m.status && S[m.status]) return S[m.status];
  if (m && m.is_active === false) return S.published;
  if (m && m.minutes_final && String(m.minutes_final).trim()) return S.draft;
  return S.collecting;
}
```

Update the `module.exports` line to export `meetingStatus` instead of `minutesStatus`:

```javascript
  module.exports = { classifyFile, isAccepted, groupFilesByTeam, buildMinutesMarkdown, meetingStatus };
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: PASS (existing `classifyFile` tests still green).

- [ ] **Step 5: Six status styles in `web/styles.css`**

Replace the Phase-3 `.mt-status-ready` / `.mt-status-pending` rules (right after `.mt-flag-team`) with the six lifecycle rules, reusing existing tokens (theme-aware in light + dark):

```css
.mt-status-setup{background:var(--muted-bg);color:var(--text-2);}
.mt-status-collecting{background:var(--muted-bg);color:var(--text-2);}
.mt-status-ready{background:var(--accent-50);color:var(--accent-700);}
.mt-status-processing{background:var(--accent-100);color:var(--accent-700);}
.mt-status-draft{background:var(--accent-50);color:var(--accent-700);}
.mt-status-published{background:var(--ok-50);color:var(--ok);}
```

- [ ] **Step 6: Use `meetingStatus` in the admin tab render**

In `web/admin.html` `renderTabs`, change the Phase-3 badge lines from `minutesStatus(m)` to:

```javascript
      const st = meetingStatus(m);
      const statusBadge = ' <span class="mt-flag mt-status-' + st.cls + '">' + st.label + '</span>';
```

(The `+ statusBadge` in the returned tab HTML stays as-is.)

- [ ] **Step 7: Manual check + commit (MeeTeam repo)**

With the Phase-4 SQL applied, open `web/admin.html`: each meeting tab shows its lifecycle label; the archived Phase-2 meeting shows "Published".

```bash
cd /Users/leleditit/Desktop/Github/MeeTeam
git add web/lib.js lib.test.js web/styles.css web/admin.html
git commit -m "feat(admin): 6-state lifecycle pill (meetingStatus) replacing the 2-state minutes badge"
```

---

### Task 4: MeeTeam — handoff command card + status controls

**Repo:** MeeTeam.

**Files:**
- Modify: `web/admin.html`

No unit test — DOM + Supabase wiring, browser-verified (Step 5). One reviewable deliverable: the admin can copy the exact command and advance the pre-meeting status.

**Interfaces:**
- Consumes: `meetingStatus` (Task 3), `meetings.status` (Task 1 SQL), the existing `supa`, `mId`, `meeting`, `isVip`, `showMeeting`, `renderTabs` in `admin.html`.

- [ ] **Step 1: Add the markup**

In `web/admin.html`, add a card in the meeting-detail area (after the meeting `<form>`/section, near the `admin-actions` block ~line 138). Use classes already in the stylesheet:

```html
      <section class="card" id="handoff-card" style="display:none;margin-bottom:22px;">
        <div class="label">Generate minutes on your Mac</div>
        <p class="page-sub">Record the meeting, then run this — the meeting id is filled in.</p>
        <pre class="handoff-cmd"><code id="handoff-cmd-text"></code></pre>
        <button type="button" class="btn btn-subtle" id="handoff-copy">Copy command</button>
      </section>
```

And a status-control button beside the archive action (inside the `admin-actions` block):

```html
        <button type="button" class="btn btn-ghost" id="status-action-btn" style="display:none;"></button>
```

- [ ] **Step 2: Bind the elements**

Beside the other `document.getElementById` consts (~line 217):

```javascript
  const handoffCard = document.getElementById('handoff-card');
  const handoffCmd = document.getElementById('handoff-cmd-text');
  const handoffCopy = document.getElementById('handoff-copy');
  const statusActionBtn = document.getElementById('status-action-btn');
```

- [ ] **Step 3: Render the card + control from the meeting's status**

Add a function and call it from `showMeeting(m)` (after the existing field-loading lines):

```javascript
  // What the single status button does next, per current status.
  function nextStatusAction(m) {
    const s = (m && m.status) || 'setup';
    const vip = !!(m && m.model === 'admin');
    if (s === 'setup')      return vip ? { label: 'Ready to record', to: 'ready' }
                                       : { label: 'Open for submissions', to: 'collecting' };
    if (s === 'collecting') return { label: 'Ready to record', to: 'ready' };
    if (s === 'ready')      return { label: 'Reopen for submissions', to: 'collecting' };
    return null;                        // processing / draft / published: Mac-owned, no control
  }

  function renderLifecycle(m) {
    if (!m) { handoffCard.style.display = 'none'; statusActionBtn.style.display = 'none'; return; }
    const s = m.status || 'setup';
    const preRecord = (s === 'setup' || s === 'collecting' || s === 'ready');
    if (preRecord) {
      handoffCmd.textContent = './review.py --meeting ' + m.id + ' <recording>';
      handoffCard.style.display = '';
    } else {
      handoffCard.style.display = 'none';
    }
    const act = nextStatusAction(m);
    if (act) {
      statusActionBtn.textContent = act.label;
      statusActionBtn.dataset.to = act.to;
      statusActionBtn.style.display = '';
    } else {
      statusActionBtn.style.display = 'none';
    }
  }
```

Call `renderLifecycle(m);` at the end of `showMeeting(m)`.

- [ ] **Step 4: Wire the copy button and the status control**

Add once during init (near the other `addEventListener` wiring):

```javascript
  handoffCopy.addEventListener('click', function(){
    navigator.clipboard.writeText(handoffCmd.textContent).then(function(){
      handoffCopy.textContent = 'Copied'; setTimeout(function(){ handoffCopy.textContent = 'Copy command'; }, 1500);
    });
  });

  statusActionBtn.addEventListener('click', async function(){
    if (!mId) return;
    const to = statusActionBtn.dataset.to;
    await supa.from('meetings').update({ status: to }).eq('id', mId);
    if (meeting) meeting.status = to;
    renderLifecycle(meeting);
    renderTabs();
  });
```

- [ ] **Step 5: Manual browser verification**

With the Phase-4 SQL applied: open `admin.html`, select a fresh Team meeting → status button reads "Open for submissions" → click → pill shows "Collecting", button becomes "Ready to record"; click → "Ready to record" state, handoff card shows `./review.py --meeting <id> <recording>` and **Copy command** copies it. A VIP meeting goes setup → "Ready to record" directly. Confirm the card hides once a meeting is `processing`/`draft`/`published`. Note the result in the commit body.

- [ ] **Step 6: Commit (MeeTeam repo)**

```bash
cd /Users/leleditit/Desktop/Github/MeeTeam
git add web/admin.html
git commit -m "feat(admin): copy-the-command handoff card + pre-meeting status controls"
```

---

## Self-Review

**Spec coverage:**
- `meetings.status` column + backfill — Task 1 Step 1 (`docs/supabase-phase4.sql`). ✓
- Meetily writes `processing`/`draft` (best-effort) + `published` on publish — Task 1. ✓
- `set_meeting_status` — Task 1. ✓
- During-meeting `notes.content` folded into minutes — Task 2 (`_combine_inputs` during-notes + `fetch_notes` reads `content`). ✓
- Empty-notes relaxation (warn, return "", no exit) — Task 2. ✓
- 6-state lifecycle pill generalizing `minutesStatus` → `meetingStatus` + styles — Task 3. ✓
- Handoff command card (id pre-filled, copyable) — Task 4. ✓
- Status controls (setup→collecting→ready, VIP→ready, reopen) — Task 4. ✓
- VIP uses the same pipeline (its content is a `notes` row read by `fetch_notes`) — no code needed; the only VIP-specific branch is the status control's `model === 'admin'` path (Task 4). ✓
- Phase 1–3 tests preserved — Tasks 1/2 full-suite steps; Task 3 keeps `classifyFile`; the `minutesStatus`→`meetingStatus` rename updates its only call site + test together. ✓

**Placeholder scan:** No TBD/TODO. `<id>`, `<recording>` are runtime values the admin substitutes (the card literally prints `<recording>` for the user to replace). Every code step is real.

**Type consistency:** `set_meeting_status(id, status) -> list` matches `_set_status_via_quorum`/`_status_best_effort` calls and the two ordered status writes asserted in tests. `_combine_inputs(..., during_notes=())` default keeps Phase-2 callers/tests valid; `fetch_notes` passes `during_notes` positionally in the documented order. `meetingStatus(m) -> {key,label,cls}` matches its test and the `st.cls`/`st.label` use in `renderTabs`. `status` string values (`setup`/`collecting`/`ready`/`processing`/`draft`/`published`) are identical across the SQL, Meetily writes, `meetingStatus` map, and `nextStatusAction`. ✓

**Cross-repo note:** Tasks 1–2 commit in meetily; Tasks 3–4 in MeeTeam. Task 4 reviews diff the MeeTeam repo. The Phase-4 SQL and the two manual browser walkthroughs are user-run — the only coverage for the live column and DOM wiring.
