# Phase 3 — Audio capture + template selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin pick which review template a meeting uses (from a self-updating list mirrored from the Mac), have `review.py` honor it, show minutes status in the MeeTeam UI, and add a `record.sh` to capture any online meeting's audio into the pipeline.

**Architecture:** Templates on the Mac stay the source of truth; `review.py --sync-templates` upserts their stem/name/description into a new Supabase `templates` table (via `quorum.py`, the Phase-2 network module). MeeTeam's `admin.html` reads that table into a dropdown and stores the chosen `stem` on `meetings.template`; `review.py --meeting <id>` resolves the template by precedence (`-t` > meeting's stem > default). A `minutesStatus` helper (in MeeTeam `web/lib.js`) drives a read-only status badge. `record.sh` records the macOS Aggregate device with ffmpeg to a file the existing pipeline already accepts.

**Tech Stack:** Python 3 (`review.py`, `quorum.py`, `pytest`), Supabase Python client (lazy-imported), MeeTeam static SPA (vanilla JS, `node:test`), ffmpeg/avfoundation, bash.

## Global Constraints

- **Two repos.** meetily = `/Users/leleditit/Desktop/Ospit/meetily`. MeeTeam = `/Users/leleditit/Desktop/Github/MeeTeam`. Each task states which repo it touches; commits land in that repo.
- **meetily tests:** `/tmp/rvenv/bin/python -m pytest` (that venv has `supabase`, `markitdown`, `openai`, `pytest`; system python3 is PEP-668 and blocks pip). **MeeTeam tests:** `node --test lib.test.js` from the MeeTeam root.
- **Supabase access:** `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` already in meetily's gitignored `.env` (Phase 2). The `supabase` client is imported INSIDE functions in `quorum.py` so unit tests need neither the package configured nor a network. Never hardcode/commit keys.
- **Template = a JSON file with top-level `name` + `sections`.** Registry row = `{stem, name, description}` where `stem` is the filename without `.json`.
- **Template precedence in `review.py`:** explicit `-t/--template` wins; else the meeting's `meetings.template` stem → `<stem>.json`; else `DEFAULT_TEMPLATE` (`weekly_review.json`). An unknown stem is a hard error listing available stems — never a silent fallback.
- **Status is derived, not stored:** `minutes_final` non-empty → "Minutes ready"; else "Awaiting minutes". No new status column, no Mac→cloud heartbeat.
- **Existing behavior is preserved:** Phase 1 local-file flow and all Phase 1/2 tests keep passing; new modes/flags are additive.
- **Recording stays Mac-driven:** no browser-triggered compute, no live transcript, no recording upload — out of scope.

---

### Task 1: Supabase registry + `review.py --sync-templates`

**Repo:** meetily.

**Files:**
- Modify: `quorum.py` (add `sync_templates`, `get_meeting_template`)
- Modify: `review.py` (add `_read_template_meta`, `_local_templates`, `_sync_templates_via_quorum`, `_meeting_template_via_quorum`, `--sync-templates` mode)
- Modify: `test_quorum.py` (payload/no-op guard)
- Modify: `test_review.py` (`_read_template_meta`, sync-mode wiring)
- Create: `docs/supabase-phase3.sql` (the manual schema, for the record)

**Interfaces:**
- Consumes: Phase-2 `quorum._client`.
- Produces:
  - `quorum.sync_templates(rows: list[dict]) -> list` — upsert `[{stem,name,description}]` into `templates`, `on_conflict="stem"`; `[]` when `rows` empty (no network).
  - `quorum.get_meeting_template(meeting_id: str) -> str | None` — the meeting's `template` stem, or `None`.
  - `review._read_template_meta(paths) -> list[dict]` — PURE-ish: parse each JSON path, keep those with `name` + `sections`, return `{stem,name,description}`; skip others with a stderr warning.
  - `review._local_templates(script_dir) -> list[Path]` — `sorted(Path(script_dir).glob("*.json"))`.
  - `review._sync_templates_via_quorum(rows)` / `review._meeting_template_via_quorum(id)` — thin `import quorum` wrappers (the test stub points).

- [ ] **Step 1: Manual Supabase schema (user runs once in the Supabase dashboard SQL editor)**

This is a prerequisite for the live/manual paths; the unit tests below do NOT need it (network is stubbed). Save the SQL to `docs/supabase-phase3.sql` and tell the user to run it:

```sql
-- templates registry: mirror of the Mac's template files (source of truth stays local)
create table if not exists templates (
  stem        text primary key,
  name        text not null,
  description text,
  updated_at  timestamptz default now()
);
alter table templates enable row level security;
create policy "templates readable by authenticated"
  on templates for select to authenticated using (true);
-- No insert/update policy: only the service_role key (the Mac sync) writes, and it bypasses RLS.

-- meetings gain a chosen template stem (null = pipeline default)
alter table meetings add column if not exists template text;
```

- [ ] **Step 2: Write the failing tests (meetily)**

Add to `test_quorum.py`:

```python
def test_sync_templates_empty_is_noop_without_network():
    from quorum import sync_templates
    assert sync_templates([]) == []      # returns early, never builds a client
```

Add to `test_review.py` (it already has `import json, os, pytest`):

```python
def test_read_template_meta_keeps_templates_skips_others(tmp_path, capsys):
    import review
    (tmp_path / "weekly_review.json").write_text(json.dumps(
        {"name": "Weekly Review v2", "description": "by project", "sections": [{"title": "X"}]}))
    (tmp_path / "notatemplate.json").write_text(json.dumps({"foo": 1}))       # no name+sections
    (tmp_path / "broken.json").write_text("{ not json")
    rows = review._read_template_meta(sorted(tmp_path.glob("*.json")))
    assert rows == [{"stem": "weekly_review", "name": "Weekly Review v2",
                     "description": "by project"}]

def test_sync_templates_mode_reads_local_and_calls_quorum(tmp_path, monkeypatch, capsys):
    import review
    sent = {}
    monkeypatch.setattr(review, "_local_templates",
                        lambda d: sorted(tmp_path.glob("*.json")))
    (tmp_path / "interview_review.json").write_text(json.dumps(
        {"name": "Interview Record", "description": "neutral", "sections": [{"title": "Y"}]}))
    monkeypatch.setattr(review, "_sync_templates_via_quorum",
                        lambda rows: sent.setdefault("rows", rows) or rows)
    review.main(["--sync-templates"])
    assert sent["rows"] == [{"stem": "interview_review", "name": "Interview Record",
                             "description": "neutral"}]
    assert "synced 1" in capsys.readouterr().out
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_quorum.py test_review.py -k "sync_templates or read_template_meta" -v`
Expected: FAIL — `AttributeError: module 'quorum'/'review' has no attribute ...`.

- [ ] **Step 4: Implement in `quorum.py`**

Add these two functions (anywhere after `_client`):

```python
def sync_templates(rows) -> list:
    """Upsert template-registry rows [{stem, name, description}] into Supabase."""
    if not rows:
        return []
    c = _client()
    res = c.table("templates").upsert(rows, on_conflict="stem").execute()
    return res.data or []


def get_meeting_template(meeting_id: str):
    """Return the meeting's chosen template stem, or None."""
    c = _client()
    rows = (c.table("meetings").select("template")
            .eq("id", meeting_id).execute().data) or []
    return (rows[0].get("template") if rows else None) or None
```

- [ ] **Step 5: Implement in `review.py`**

Near the other helpers (below `_publish_via_quorum`), add:

```python
def _local_templates(script_dir):
    return sorted(Path(script_dir).glob("*.json"))


def _read_template_meta(paths):
    """Parse template JSON files -> [{stem, name, description}]; skip non-templates."""
    rows = []
    for p in paths:
        p = Path(p)
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            print(f"skip {p.name}: not valid JSON ({e})", file=sys.stderr)
            continue
        if not d.get("name") or "sections" not in d:
            print(f"skip {p.name}: not a template (needs name + sections)", file=sys.stderr)
            continue
        rows.append({"stem": p.stem, "name": d["name"],
                     "description": d.get("description") or ""})
    return rows


def _sync_templates_via_quorum(rows):
    import quorum
    return quorum.sync_templates(rows)


def _meeting_template_via_quorum(meeting_id):
    import quorum
    return quorum.get_meeting_template(meeting_id)
```

In `main`, add the flag beside the others:

```python
    ap.add_argument("--sync-templates", action="store_true",
                    help="upsert local templates into Supabase and exit")
```

And handle it early — right after the `--publish` block returns, before the `recording` check:

```python
    if args.sync_templates:
        script_dir = Path(__file__).resolve().parent
        rows = _read_template_meta(_local_templates(script_dir))
        synced = _sync_templates_via_quorum(rows)
        print(f"synced {len(synced)} templates")
        return
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `/tmp/rvenv/bin/python -m pytest test_quorum.py test_review.py -k "sync_templates or read_template_meta" -v`
Expected: PASS.

- [ ] **Step 7: Full suite (no regressions)**

Run: `/tmp/rvenv/bin/python -m pytest test_review.py test_quorum.py -q`
Expected: all pass (Phase 1/2 unaffected).

- [ ] **Step 8: Commit**

```bash
git add quorum.py review.py test_quorum.py test_review.py docs/supabase-phase3.sql
git commit -m "feat: template registry — review.py --sync-templates upserts local templates to Supabase"
```

---

### Task 2: `review.py --meeting` honors the meeting's template

**Repo:** meetily.

**Files:**
- Modify: `review.py` (`-t` default → None; `resolve_template`; wire into `main`; auto-sync)
- Modify: `test_review.py`

**Interfaces:**
- Consumes: Task 1's `_meeting_template_via_quorum`, `_sync_templates_via_quorum`, `_read_template_meta`, `_local_templates`; existing `DEFAULT_TEMPLATE`.
- Produces: `review.resolve_template(explicit, meeting_template, script_dir) -> str` — absolute template path by precedence; `SystemExit` if `meeting_template` names a stem with no local `<stem>.json`.

- [ ] **Step 1: Write the failing tests**

Add to `test_review.py`:

```python
def test_resolve_template_precedence(tmp_path):
    import review
    (tmp_path / "weekly_review.json").write_text("{}")
    (tmp_path / "interview_review.json").write_text("{}")
    # explicit -t wins
    assert review.resolve_template("/x/custom.json", "interview_review", tmp_path) == "/x/custom.json"
    # else the meeting's stem
    assert review.resolve_template(None, "interview_review", tmp_path) == str(tmp_path / "interview_review.json")
    # else the default
    assert review.resolve_template(None, None, tmp_path) == str(tmp_path / "weekly_review.json")

def test_resolve_template_unknown_stem_exits(tmp_path):
    import review
    (tmp_path / "weekly_review.json").write_text("{}")
    with pytest.raises(SystemExit):
        review.resolve_template(None, "nope", tmp_path)

def test_meeting_mode_uses_meeting_template(tmp_path, capsys, monkeypatch):
    import review
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(review, "_fetch_via_quorum", lambda mid: "QNOTE")
    monkeypatch.setattr(review, "_meeting_template_via_quorum", lambda mid: "interview_review")
    audio = tmp_path / "a.m4a"; audio.write_text("x")
    transcript = tmp_path / "a.manglish.txt"; transcript.write_text("hi")
    newer = audio.stat().st_mtime + 10; os.utime(transcript, (newer, newer))
    # no -t: the interview template (real file in the repo) must be selected
    review.main([str(audio), "--meeting", "MID-1", "--dry-run"])
    out = capsys.readouterr().out
    assert "Interview" in out          # interview_review.json's section titles reach the prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/tmp/rvenv/bin/python -m pytest test_review.py -k "resolve_template or meeting_mode_uses" -v`
Expected: FAIL — `AttributeError: resolve_template`, and the meeting-template test errors because `main` doesn't consult the meeting template yet.

- [ ] **Step 3: Change the `-t` default and add `resolve_template`**

In `main`, change the template arg so "not passed" is detectable:

```python
    ap.add_argument("-t", "--template", default=None,
                    help="template JSON; overrides the meeting's template. Default: weekly_review.json")
```

Add the resolver near the other helpers:

```python
def resolve_template(explicit, meeting_template, script_dir):
    """Pick the template path: explicit -t > meeting's stem > DEFAULT_TEMPLATE.
    Exit if meeting_template names a stem with no local <stem>.json."""
    if explicit:
        return explicit
    if meeting_template:
        cand = Path(script_dir) / f"{meeting_template}.json"
        if not cand.exists():
            avail = ", ".join(p.stem for p in _local_templates(script_dir)) or "(none)"
            sys.exit(f"meeting template '{meeting_template}' has no {cand.name} here. Available: {avail}")
        return str(cand)
    return str(Path(script_dir) / DEFAULT_TEMPLATE)
```

- [ ] **Step 4: Wire it into `main`'s generate path**

Replace the current block (the `template = json.loads(...)`, `notes = read_notes(...)`, `if args.meeting:` fold, `transcript = transcribe(...)` lines) with — note the order keeps Phase 2's fail-fast (Quorum + resolve before transcription), only fetches the meeting template when no `-t`, and auto-syncs best-effort on real generates:

```python
    script_dir = Path(__file__).resolve().parent
    notes = read_notes(args.notes)
    meeting_template = None
    if args.meeting:
        qnotes = _fetch_via_quorum(args.meeting)
        notes = (qnotes + "\n\n" + notes).strip() if notes.strip() else qnotes
        if not args.template:
            meeting_template = _meeting_template_via_quorum(args.meeting)
        if not args.dry_run:
            try:
                _sync_templates_via_quorum(_read_template_meta(_local_templates(script_dir)))
            except Exception as e:
                print(f"warning: template sync skipped ({e})", file=sys.stderr)

    template_path = resolve_template(args.template, meeting_template, script_dir)
    template = json.loads(Path(template_path).read_text())
    transcript = transcribe(args.recording, args.clean)
```

Then change the output-name line from `stem = Path(args.template).stem` to:

```python
    stem = Path(template_path).stem
```

- [ ] **Step 5: New tests pass, then whole suite**

Run: `/tmp/rvenv/bin/python -m pytest test_review.py -k "resolve_template or meeting_mode" -v`
Expected: PASS (including the existing `test_meeting_mode_merges_quorum_notes`, which passes `-t` so the meeting-template fetch is skipped).

Run: `/tmp/rvenv/bin/python -m pytest test_review.py test_quorum.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add review.py test_review.py
git commit -m "feat: review.py --meeting uses the meeting's chosen template (precedence: -t > meeting > default)"
```

---

### Task 3: MeeTeam admin — template dropdown

**Repo:** MeeTeam (`/Users/leleditit/Desktop/Github/MeeTeam`).

**Files:**
- Modify: `web/admin.html`

**Interfaces:**
- Consumes: Supabase `templates` (read) and `meetings.template` (write) from Task 1's schema.
- Produces: a meeting's `template` stem, written by the existing autosave.

No unit test — this is DOM + network wiring, verified in the browser (Step 5). It is one reviewable deliverable (a working dropdown bound to autosave).

- [ ] **Step 1: Add the select markup**

In `web/admin.html`, right after the Mode field's closing `</div>` (the field containing `id="m-model"`, ~line 85), add:

```html
            <div class="field">
              <label class="label" for="m-template">Template</label>
              <select class="input" id="m-template">
                <option value="">Default (weekly)</option>
              </select>
              <span class="field-hint">Which review format the pipeline generates for this meeting.</span>
            </div>
```

- [ ] **Step 2: Bind the element**

Beside the other field consts (`const fModel = document.getElementById('m-model');`, ~line 221) add:

```javascript
  const fTemplate = document.getElementById('m-template');
```

- [ ] **Step 3: Populate options from the registry**

Add this function (near the other helpers in the inline script) and call it once during init, after the field consts are defined (~line 224):

```javascript
  async function loadTemplateOptions(){
    const { data } = await supa.from('templates').select('stem,name').order('name');
    (data || []).forEach(function(t){
      const o = document.createElement('option');
      o.value = t.stem; o.textContent = t.name;
      fTemplate.appendChild(o);
    });
  }
```

Call site (once, during the existing init flow):

```javascript
  await loadTemplateOptions();
```

- [ ] **Step 4: Load into the form, save in the payload, autosave on change**

In `showMeeting(m)` beside `fModel.value = ...` (~line 267) add:

```javascript
    fTemplate.value = m ? (m.template || '') : '';
```

In `persistMeeting`, add `template` to the payload (~line 300):

```javascript
    const payload = { title: fTitle.value || 'Untitled', meeting_date: fDate.value || null, org: fOrg.value, model: fModel.value, template: fTemplate.value || null };
```

Add `fTemplate` to the autosave input-listener array (~line 306):

```javascript
  [fTitle, fDate, fOrg, fModel, fTemplate].forEach(function(f){ f.addEventListener('input', function(){ flashSaving(); clearTimeout(mtimer); mtimer = setTimeout(persistMeeting, 600); }); });
```

- [ ] **Step 5: Manual browser verification**

With the Supabase schema applied (Task 1 Step 1) and templates synced (`review.py --sync-templates`): open `web/admin.html`, confirm the Template dropdown lists the synced templates, pick one on a meeting, reload, and confirm the choice persisted (round-trips through `meetings.template`). Note the result in the commit body.

- [ ] **Step 6: Commit (in the MeeTeam repo)**

```bash
cd /Users/leleditit/Desktop/Github/MeeTeam
git add web/admin.html
git commit -m "feat(admin): template dropdown — pick a meeting's review format, populated from the templates registry"
```

---

### Task 4: MeeTeam — minutes-status badge

**Repo:** MeeTeam.

**Files:**
- Modify: `web/lib.js` (add + export `minutesStatus`)
- Modify: `lib.test.js` (unit test)
- Modify: `web/admin.html` (load `lib.js`, render the badge)

**Interfaces:**
- Produces: `minutesStatus(m) -> { label: string, cls: 'ready' | 'pending' }`.

- [ ] **Step 1: Write the failing test**

Add to `lib.test.js`:

```javascript
const { minutesStatus } = require('./web/lib.js');

test('minutesStatus reflects whether minutes are published', () => {
  assert.equal(minutesStatus({ minutes_final: '# Minutes\nbody' }).label, 'Minutes ready');
  assert.equal(minutesStatus({ minutes_final: '   ' }).label, 'Awaiting minutes');
  assert.equal(minutesStatus({ minutes_final: null, is_active: true }).label, 'Awaiting minutes');
  assert.equal(minutesStatus({}).label, 'Awaiting minutes');
  assert.equal(minutesStatus({ minutes_final: '# M' }).cls, 'ready');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: FAIL — `minutesStatus is not a function` (undefined export).

- [ ] **Step 3: Implement in `web/lib.js`**

Add the function and export it (extend the existing `module.exports` at the bottom):

```javascript
function minutesStatus(m) {
  return (m && m.minutes_final && String(m.minutes_final).trim())
    ? { label: 'Minutes ready', cls: 'ready' }
    : { label: 'Awaiting minutes', cls: 'pending' };
}
```

```javascript
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { classifyFile, isAccepted, groupFilesByTeam, buildMinutesMarkdown, minutesStatus };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: PASS (existing `classifyFile` tests still green).

- [ ] **Step 5: Use it in the admin tab render**

Load `lib.js` in `web/admin.html` — add before the inline `<script>` (after `ui.js`, ~line 193):

```html
<script src="lib.js?v=1"></script>
```

In `renderTabs`, beside `const modelBadge = ...` (~line 247), build the status pill and append it to the tab markup next to `modelBadge`:

```javascript
      const st = minutesStatus(m);
      const statusBadge = ' <span class="mt-flag mt-status-' + st.cls + '">' + st.label + '</span>';
```

Then in the returned tab HTML, add `+ statusBadge` immediately after `+ modelBadge` (the `'<span class="mt-sub">' + label + modelBadge + ...'` line becomes `... + label + modelBadge + statusBadge + ...`).

- [ ] **Step 6: Manual check + commit (MeeTeam repo)**

Open `web/admin.html`: an unpublished meeting shows "Awaiting minutes"; one whose minutes were published (Phase 2) shows "Minutes ready".

```bash
cd /Users/leleditit/Desktop/Github/MeeTeam
git add web/lib.js lib.test.js web/admin.html
git commit -m "feat(admin): minutes-status badge (Awaiting minutes / Minutes ready) from existing fields"
```

---

### Task 5: `record.sh` — capture an online meeting

**Repo:** meetily.

**Files:**
- Create: `record.sh`
- Modify: `README.md` (online-meeting + Audio MIDI Setup section)

**Interfaces:** produces `recordings/meeting_<timestamp>.m4a`, which `review.py <file>` already accepts.

No pytest (shell + audio). The runnable check is `record.sh --list` (Step 3) — it prints devices and exits 0 without recording. The audio routing itself is verified by the manual test in Step 5.

- [ ] **Step 1: Write `record.sh`**

```bash
#!/usr/bin/env bash
# Record an online meeting's audio (both sides) to a file the pipeline reads.
# Needs a macOS Aggregate Device that combines VB-Cable (far end) + your mic.
# See README "Recording an online meeting" for the one-time Audio MIDI Setup.
set -euo pipefail

DEVICE_NAME="${RECORD_DEVICE:-Aggregate Device}"
OUTDIR="$(cd "$(dirname "$0")" && pwd)/recordings"

# ffmpeg avfoundation indices shift between reboots — resolve by name every run.
list_audio() {
  ffmpeg -f avfoundation -list_devices true -i "" 2>&1 \
    | awk '/AVFoundation audio devices:/{a=1;next} /AVFoundation video devices:/{a=0} a'
}

if [[ "${1:-}" == "--list" ]]; then
  echo "Audio input devices ffmpeg sees:"; list_audio; exit 0
fi

IDX="$(list_audio | sed -n "s/.*\[\([0-9]\+\)\] ${DEVICE_NAME}\$/\1/p" | head -1)"
if [[ -z "$IDX" ]]; then
  echo "Audio device '${DEVICE_NAME}' not found. Devices seen:" >&2
  list_audio >&2
  echo "Set RECORD_DEVICE=... or build the Aggregate Device (see README)." >&2
  exit 1
fi

mkdir -p "$OUTDIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
OUT="$OUTDIR/meeting_${TS}.m4a"
echo "Recording '${DEVICE_NAME}' (index ${IDX}) -> ${OUT}"
echo "Press Ctrl-C to stop."
ffmpeg -hide_banner -loglevel warning -f avfoundation -i ":${IDX}" -c:a aac "$OUT"

echo
echo "Saved ${OUT}"
echo "Next: ./review.py --meeting <meeting-id> \"${OUT}\""
```

(ffmpeg finalizes the AAC/m4a on the Ctrl-C SIGINT, so the file is playable.)

- [ ] **Step 2: Make it executable**

```bash
chmod +x record.sh
```

- [ ] **Step 3: Runnable check — list mode + shellcheck**

Run: `./record.sh --list`
Expected: prints "Audio input devices ffmpeg sees:" and the numbered device list (incl. `Aggregate Device`), exit 0, no recording.
Run: `shellcheck record.sh` (if installed) — expected: clean.

- [ ] **Step 4: README section**

Add to `README.md` (under `## Use` or a new `## Recording an online meeting`):

```markdown
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
```

- [ ] **Step 5: Manual audio verification**

Do the 15-second both-voices test above once and confirm the transcript contains both your speech and the clip. Record the result in the commit body.

- [ ] **Step 6: Commit**

```bash
git add record.sh README.md
git commit -m "feat: record.sh — capture an online meeting (both sides) into the pipeline; README setup"
```

---

## Self-Review

**Spec coverage:**
- A. `record.sh` capture + Audio MIDI Setup doc — Task 5. ✓
- B. `templates` table + `meetings.template` column — Task 1 Step 1 (manual SQL, saved to `docs/supabase-phase3.sql`). ✓
- B. `review.py --sync-templates` + auto-sync on generate + `quorum` helpers — Tasks 1 & 2. ✓
- B. Template precedence (`-t` > meeting > default), unknown-stem hard error — Task 2 `resolve_template`. ✓
- B. MeeTeam dropdown populated from registry, writes `meetings.template` — Task 3. ✓
- C. Minutes-status badge from existing fields — Task 4. ✓
- Existing Phase 1/2 behavior + tests preserved — Tasks 1/2 Steps 7/5 (full suite), Task 3/4 keep `classifyFile` tests. ✓
- Error handling (device-not-found, missing stem, best-effort sync, empty registry) — Task 5 Step 1, Task 2 Step 3, Task 2 Step 4, Task 3 markup default option. ✓

**Placeholder scan:** No TBD/TODO. `<id>`, `<stem>`, `<ts>`, `<meeting-id>` are runtime values, not plan gaps. Every code step shows real code.

**Type consistency:** Registry row shape `{stem,name,description}` is identical in `_read_template_meta` (produce), `sync_templates` (consume), the dropdown (`stem`,`name`), and the tests. `resolve_template(explicit, meeting_template, script_dir) -> str` is called with those exact args in `main` and asserted in tests. `_meeting_template_via_quorum` returns the stem string that `resolve_template`'s `meeting_template` expects. `minutesStatus(m) -> {label,cls}` matches its test and its `admin.html` use. `meetings.template` (write in Task 3, read in Task 2 via `get_meeting_template`) is one name throughout. ✓

**Cross-repo note:** Tasks 1, 2, 5 commit in meetily; Tasks 3, 4 commit in MeeTeam. Reviews for 3/4 diff the MeeTeam repo. The Supabase schema (Task 1 Step 1) and the two manual audio/browser verifications are user-run — no automated test covers the live table, the browser wiring, or the audio routing.
