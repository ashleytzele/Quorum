# Phase 9 — Bring-your-own-audio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin provide the audio directly in MeeTeam — record it in the browser (device picker) or import a file — instead of only using a Meetily-app recording. The bridge transcribes it locally via `review.py` and generates as usual.

**Architecture:** A new multipart `POST /generate-audio` on the local bridge saves the uploaded audio to a temp file and runs `review.py <audio> --meeting <q> -t <tpl>` (local-file mode → whisper transcription + Quorum notes). MeeTeam's Generate card gains an audio-source switch (Meetily recording · Record · Import); Record/Import post the audio to the new endpoint. `review.py`/`quorum.py`/`meetily_app.py` are untouched.

**Tech Stack:** Python 3 + Flask (bridge, multipart), `subprocess`, `pytest`; MeeTeam vanilla JS (`MediaRecorder`, `enumerateDevices`, `FormData`), `node:test`.

## Global Constraints

- **Two repos.** meetily = `/Users/leleditit/Desktop/Ospit/meetily` (bridge). MeeTeam = `/Users/leleditit/Desktop/Github/MeeTeam` (frontend). Tests: meetily `./.venv/bin/python -m pytest`; MeeTeam `node --test lib.test.js` from its root.
- **The bridge shells `review.py`** — no pipeline logic added; does not modify `review.py`/`quorum.py`/`meetily_app.py`.
- **Audio is transient:** save to a temp file, transcribe, then delete the temp audio, its `.manglish.txt` sidecar, and the temp `.md` in a `finally`. Never store audio persistently; never join a client filename into a path — derive only a safe extension.
- Bridge binds `127.0.0.1`; CORS `after_request` already allows `MEETEAM_ORIGIN`. `/generate-audio` handles `OPTIONS` and returns JSON `{error}` (never a bare 500) so CORS + the message reach the browser.
- **Browser recording = the selected microphone** (in-person friendly; online needs a virtual input — Import covers that). `getUserMedia` works because MeeTeam is served on localhost (a secure context).
- Phase 1–8 behavior + tests stay green. The existing Phase-7 `/generate` and the Meetily-recording source keep working unchanged. PRODUCT.md in MeeTeam has a pre-existing unstaged edit — never stage it.

---

### Task 1: Bridge — `POST /generate-audio` (transcribe an uploaded file)

**Files:**
- Modify: `local/bridge.py`
- Modify: `test_bridge.py`

**Interfaces:**
- `bridge._generate_audio_argv(python, review_py, audio_path, meeting_id, template, out_path) -> list[str]` — PURE: `[python, review_py, audio_path, "--meeting", meeting_id, ("-t", <tpl>.json)?, "-o", out_path]`.
- `bridge._safe_audio_suffix(filename) -> str` — PURE: whitelist audio extensions, default `.webm`.
- Endpoint: `POST /generate-audio` (+ `OPTIONS`).

- [ ] **Step 1: Write the failing tests**

Add to `test_bridge.py` (add `import io` at the top):

```python
def test_generate_audio_argv():
    a = bridge._generate_audio_argv("py", "review.py", "/t/a.webm", "q1", "weekly_review", "/t/o.md")
    assert a == ["py", "review.py", "/t/a.webm", "--meeting", "q1",
                 "-t", str(bridge.REPO_ROOT / "weekly_review.json"), "-o", "/t/o.md"]
    b = bridge._generate_audio_argv("py", "review.py", "/t/a.webm", "q1", None, "/t/o.md")
    assert b == ["py", "review.py", "/t/a.webm", "--meeting", "q1", "-o", "/t/o.md"]


def test_safe_audio_suffix():
    assert bridge._safe_audio_suffix("meeting.m4a") == ".m4a"
    assert bridge._safe_audio_suffix("clip.MP3") == ".mp3"
    assert bridge._safe_audio_suffix("blob") == ".webm"           # no ext -> default
    assert bridge._safe_audio_suffix("../evil.exe") == ".webm"    # non-audio -> default (never .exe)


def test_generate_audio_missing_fields_400():
    c = bridge.create_app().test_client()
    # no audio file
    r = c.post("/generate-audio", data={"meeting_id": "q1"}, content_type="multipart/form-data")
    assert r.status_code == 400
    # no meeting_id
    r = c.post("/generate-audio",
               data={"audio": (io.BytesIO(b"AUDIO"), "a.webm")}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_generate_audio_success(monkeypatch):
    def fake_run(argv, **kw):
        Path(argv[argv.index("-o") + 1]).write_text("# Minutes\nbody")
        class R: returncode = 0; stdout = "projects (1): P\n"; stderr = ""
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate-audio",
               data={"meeting_id": "q1", "template": "weekly_review",
                     "audio": (io.BytesIO(b"AUDIO"), "rec.webm")},
               content_type="multipart/form-data").get_json()
    assert "# Minutes" in r["markdown"] and r["projects"] == ["P"]


def test_generate_audio_failure_500(monkeypatch):
    def fail_run(argv, **kw):
        class R: returncode = 1; stdout = ""; stderr = "no audio track"
        return R()
    monkeypatch.setattr(bridge.subprocess, "run", fail_run)
    c = bridge.create_app().test_client()
    r = c.post("/generate-audio",
               data={"meeting_id": "q1", "audio": (io.BytesIO(b"x"), "a.webm")},
               content_type="multipart/form-data")
    assert r.status_code == 500 and "no audio" in r.get_json()["error"]


def test_generate_audio_preflight():
    c = bridge.create_app().test_client()
    r = c.open("/generate-audio", method="OPTIONS")
    assert r.status_code in (200, 204) and r.headers["Access-Control-Allow-Origin"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest test_bridge.py -k "generate_audio or safe_audio" -v`
Expected: FAIL — `_generate_audio_argv`/`_safe_audio_suffix`/route missing.

- [ ] **Step 3: Implement in `local/bridge.py`**

Top-level helpers (near `_generate_argv`):

```python
_AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".webm", ".mp4", ".ogg", ".aac", ".flac"}


def _safe_audio_suffix(filename):
    ext = Path(filename or "").suffix.lower()
    return ext if ext in _AUDIO_EXTS else ".webm"


def _generate_audio_argv(python, review_py, audio_path, meeting_id, template, out_path):
    argv = [python, str(review_py), str(audio_path), "--meeting", meeting_id]
    if template:
        argv += ["-t", str(REPO_ROOT / f"{template}.json")]
    argv += ["-o", str(out_path)]
    return argv
```

Endpoint inside `create_app` (mirrors `/generate`'s temp/commit-on-success + try/except):

```python
    @app.route("/generate-audio", methods=["POST", "OPTIONS"])
    def generate_audio():
        if request.method == "OPTIONS":
            return ("", 204)
        meeting_id = request.form.get("meeting_id")
        f = request.files.get("audio")
        if not meeting_id or f is None:
            return (jsonify({"error": "meeting_id and audio file required"}), 400)
        template = request.form.get("template") or None
        if template and not re.fullmatch(r"[A-Za-z0-9_-]+", template):
            return (jsonify({"error": "invalid template name"}), 400)
        try:
            afd, atmp = tempfile.mkstemp(suffix=_safe_audio_suffix(f.filename))
            os.close(afd)
            audio = Path(atmp)
            ofd, otmp = tempfile.mkstemp(suffix=".md")
            os.close(ofd)
            out = Path(otmp)
            try:
                f.save(str(audio))
                argv = _generate_audio_argv(sys.executable, REPO_ROOT / "review.py",
                                            audio, meeting_id, template, out)
                r = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True)
                if r.returncode != 0 or not out.exists() or not out.read_text().strip():
                    return (jsonify({"error": (r.stderr or "generation failed").strip()}), 500)
                markdown = out.read_text()
            finally:
                for p in (audio, out, audio.with_suffix(".manglish.txt")):
                    try:
                        p.unlink()
                    except OSError:
                        pass
            return jsonify({"ok": True, "markdown": markdown,
                            "projects": _parse_projects(r.stdout),
                            "warnings": [l for l in (r.stderr or "").splitlines() if l.strip()]})
        except Exception as e:
            return (jsonify({"error": str(e)}), 500)
```

(If `review.py` writes a differently-named sidecar transcript, the implementer widens the
cleanup to also remove `audio.parent` transcript siblings of `audio.stem` — verify against
`retranscribe.sh`'s output name; the temp audio dir is the system temp, so a leftover sidecar
is harmless but should be cleaned.)

- [ ] **Step 4: Run tests, then the full meetily suite**

Run: `./.venv/bin/python -m pytest test_bridge.py -k "generate_audio or safe_audio" -v`
Expected: PASS.
Run: `./.venv/bin/python -m pytest test_bridge.py test_review.py test_quorum.py test_meetily_app.py test_local.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add local/bridge.py test_bridge.py
git commit -m "feat(bridge): /generate-audio — transcribe an uploaded/recorded audio file + Quorum notes -> minutes"
```

---

### Task 2: MeeTeam — audio-source switch (Record / Import) in the Generate card

**Files:**
- Modify: `web/minutes.html`
- Modify: `web/lib.js` (a tiny pure helper) + `lib.test.js`
- Modify: `web/styles.css` (a few rules for the source controls)

**Interfaces:**
- `recordingExt(mimeType) -> string` in `lib.js` — pick a file extension for a `MediaRecorder` mime (`audio/webm`→`webm`, `audio/mp4`→`m4a`, else `webm`). Pure, tested.

- [ ] **Step 1: Write the failing `recordingExt` test**

Add to `lib.test.js`:

```javascript
const { recordingExt } = require('./web/lib.js');

test('recordingExt maps MediaRecorder mimeType to an extension', () => {
  assert.equal(recordingExt('audio/webm;codecs=opus'), 'webm');
  assert.equal(recordingExt('audio/mp4'), 'm4a');
  assert.equal(recordingExt('video/webm'), 'webm');
  assert.equal(recordingExt(''), 'webm');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: FAIL — `recordingExt is not a function`.

- [ ] **Step 3: Implement `recordingExt` in `web/lib.js`** (extend `module.exports`)

```javascript
function recordingExt(mimeType) {
  const m = String(mimeType || '').toLowerCase();
  if (m.includes('mp4') || m.includes('m4a') || m.includes('aac')) return 'm4a';
  return 'webm';
}
```
```javascript
  module.exports = { classifyFile, isAccepted, groupFilesByTeam, buildMinutesMarkdown, meetingStatus, matchRecording, recordingExt };
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/leleditit/Desktop/Github/MeeTeam && node --test lib.test.js`
Expected: PASS (existing tests still green).

- [ ] **Step 5: Add the audio-source markup in the card** (`web/minutes.html`, inside `#ai-wrap`'s `.ai-card-head`/body — read the current card first)

Add a source selector and the Record/Import controls; keep the existing recording `<select>` for the Meetily source:

```html
        <div class="ai-source">
          <label><input type="radio" name="ai-source" value="meetily" checked> Meetily recording</label>
          <label><input type="radio" name="ai-source" value="record"> Record</label>
          <label><input type="radio" name="ai-source" value="import"> Import</label>
        </div>
        <div class="ai-src-panel" data-src="meetily">
          <label class="ai-rec">Recording <select class="input" id="ai-recording"></select></label>
        </div>
        <div class="ai-src-panel" data-src="record" style="display:none;">
          <label class="ai-rec">Mic <select class="input" id="ai-device"></select></label>
          <button class="btn btn-ghost" id="ai-rec-btn" type="button">● Record</button>
          <span id="ai-rec-time" class="page-sub"></span>
        </div>
        <div class="ai-src-panel" data-src="import" style="display:none;">
          <input type="file" id="ai-file" accept="audio/*">
        </div>
```
(Place the existing `#gen-ai` Generate button so it's visible for all sources.)

- [ ] **Step 6: Wire it in `minutes.html`'s script**

Add state + helpers near the Phase-7 AI wiring (`aiMinutes`, `genAiBtn`, etc.):

```javascript
  let recordedBlob = null, importedFile = null, mediaRec = null, recStream = null;
  function currentSource() { return (document.querySelector('input[name="ai-source"]:checked') || {}).value || 'meetily'; }
  function showSourcePanels() {
    const s = currentSource();
    document.querySelectorAll('.ai-src-panel').forEach(p => { p.style.display = p.dataset.src === s ? '' : 'none'; });
  }
  document.querySelectorAll('input[name="ai-source"]').forEach(r => r.addEventListener('change', function () {
    showSourcePanels();
    if (currentSource() === 'record') listMics();
  }));

  async function listMics() {
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });   // prompt once so labels appear
      const devs = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'audioinput');
      document.getElementById('ai-device').innerHTML =
        devs.map(d => '<option value="' + d.deviceId + '">' + esc(d.label || 'Microphone') + '</option>').join('');
    } catch (e) { aiStatus.className = 'ai-status is-err'; aiStatus.textContent = 'Mic access denied — use Import instead.'; }
  }

  document.getElementById('ai-rec-btn').addEventListener('click', async function () {
    const btn = this;
    if (mediaRec && mediaRec.state === 'recording') { mediaRec.stop(); return; }
    try {
      const deviceId = document.getElementById('ai-device').value;
      recStream = await navigator.mediaDevices.getUserMedia({ audio: deviceId ? { deviceId } : true });
      const chunks = [];
      mediaRec = new MediaRecorder(recStream);
      mediaRec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      mediaRec.onstop = function () {
        recordedBlob = new Blob(chunks, { type: mediaRec.mimeType });
        recStream.getTracks().forEach(t => t.stop());
        btn.textContent = '● Record'; document.getElementById('ai-rec-time').textContent = 'recorded ✓';
      };
      mediaRec.start(); recordedBlob = null;
      btn.textContent = '■ Stop'; document.getElementById('ai-rec-time').textContent = 'recording…';
    } catch (e) { aiStatus.className = 'ai-status is-err'; aiStatus.textContent = 'Could not start recording.'; }
  });

  document.getElementById('ai-file').addEventListener('change', function (e) { importedFile = e.target.files[0] || null; });
```

Replace the `genAiBtn` click handler so it routes by source (Meetily → JSON `/generate`; Record/Import → multipart `/generate-audio`):

```javascript
  genAiBtn.addEventListener('click', async function () {
    const src = currentSource();
    genAiBtn.disabled = true; aiText.style.display = '';
    aiStatus.className = 'ai-status is-busy';
    aiStatus.textContent = src === 'meetily' ? 'Generating…' : 'Transcribing + generating… (this can take a minute)';
    try {
      let res;
      if (src === 'meetily') {
        res = await fetch(window.BRIDGE_URL + '/generate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ meeting_id: meeting.id, meetily_id: document.getElementById('ai-recording').value, template: meeting.template || null })
        }).then(async r => r.ok ? r.json() : Promise.reject(await r.json()));
      } else {
        const blob = src === 'record' ? recordedBlob : importedFile;
        if (!blob) throw { error: src === 'record' ? 'Record something first.' : 'Choose an audio file first.' };
        const name = src === 'record' ? ('recording.' + recordingExt(blob.type)) : blob.name;
        const fd = new FormData();
        fd.append('meeting_id', meeting.id);
        if (meeting.template) fd.append('template', meeting.template);
        fd.append('audio', blob, name);
        res = await fetch(window.BRIDGE_URL + '/generate-audio', { method: 'POST', body: fd })
          .then(async r => r.ok ? r.json() : Promise.reject(await r.json()));
      }
      aiMinutes = res.markdown; aiText.value = res.markdown;
      document.getElementById('d-body').innerHTML = md.render(res.markdown);
      const n = res.projects.length;
      aiStatus.className = 'ai-status is-ok';
      aiStatus.textContent = '✓ Generated — ' + n + (n === 1 ? ' project: ' : ' projects: ') + res.projects.join(', ');
    } catch (e) {
      aiStatus.className = 'ai-status is-err';
      aiStatus.textContent = 'Failed: ' + ((e && e.error) || 'error');
    } finally {
      genAiBtn.disabled = false;
    }
  });
```

In the health-gate, keep showing the card when the bridge is up **even with no recordings**
(Record/Import don't need any) — change the reveal to: on bridge `ok`, `aiWrap.style.display = ''`
and only hide the Meetily `<select>`/panel if there are no recordings. Populate mics lazily
(on first switch to Record, already wired). Call `showSourcePanels()` once after reveal.

- [ ] **Step 7: A few styles in `web/styles.css`** (match the design system)

```css
.ai-source{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:0.82rem;color:var(--text-2);}
.ai-source label{display:flex;align-items:center;gap:6px;cursor:pointer;}
.ai-src-panel{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px;}
.ai-src-panel .input{height:34px;max-width:240px;}
#ai-file{font-size:0.82rem;}
```

- [ ] **Step 8: Manual browser verification**

`run-bridge.command` + MeeTeam `run.command`. On a meeting's Minutes page (bridge up):
1. **Record** → pick a mic → ● Record ~15s of talking → ■ Stop → **Generate** → after transcription the minutes appear → edit → **Finalize**.
2. **Import** → choose a `.m4a`/`.mp3` → **Generate** → minutes appear.
3. **Meetily recording** (regression) → still works as before.
Record the result in the commit body. (Requires the local whisper stack `review.py` uses.)

- [ ] **Step 9: Commit (MeeTeam repo)**

```bash
cd /Users/leleditit/Desktop/Github/MeeTeam
git add web/minutes.html web/lib.js lib.test.js web/styles.css
git commit -m "feat(minutes): audio-source switch — record in-browser or import a file, post to the bridge to transcribe+generate"
```

---

## Self-Review

**Spec coverage:**
- Bridge `/generate-audio` multipart (save temp, run review.py local-file, commit-on-success, cleanup, 400/500, CORS/OPTIONS) — Task 1. ✓
- Safe audio suffix, no client path joined — Task 1 `_safe_audio_suffix`. ✓
- Audio transient (temp audio + sidecar + .md deleted in finally) — Task 1 Step 3. ✓
- MeeTeam three-source switch (Meetily / Record / Import); Record via enumerateDevices+MediaRecorder; Import via file input; both post to `/generate-audio` — Task 2. ✓
- Reuses Phase-7 fill-editor + `minutesMarkdown()` override + Finalize; Meetily source unchanged — Task 2 Step 6. ✓
- Card shows for Record/Import even with no Meetily recordings — Task 2 Step 6. ✓
- `review.py`/`quorum.py`/`meetily_app.py` untouched — no such edits. ✓
- Transcription-is-slow UI state; mic-only caveat is a doc/UX matter, surfaced in status text — Task 2. ✓

**Placeholder scan:** No TBD/TODO. Endpoint/handler code is real. `<q>`/`<tpl>` are runtime values. The Task-1 sidecar note points at a concrete verify step, not a placeholder.

**Type consistency:** `_generate_audio_argv(python, review_py, audio_path, meeting_id, template, out_path)` matches its test and the endpoint call. `/generate-audio` returns `{markdown, projects, warnings}` — identical shape to `/generate`, so the frontend's fill logic is shared. `recordingExt(mime)->str` matches its test and the FormData filename. FormData keys (`meeting_id`, `template`, `audio`) match `request.form`/`request.files` names. ✓

**Cross-repo note:** Task 1 in meetily, Task 2 in MeeTeam (reviews diff the MeeTeam repo). The MediaRecorder/enumerateDevices/upload DOM path + the real whisper transcription behind `/generate-audio` are browser-verified (Task 2 Step 8); everything else is unit-tested offline.
