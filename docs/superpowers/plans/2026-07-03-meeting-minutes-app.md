# Meeting Minutes App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single-machine, admin-only web app that turns team-submitted files into a slideshow, captures notes live during a meeting, and exports formal Minutes-of-Meeting as a PDF.

**Architecture:** Pure logic (file classification, grouping, slide-splitting, minutes assembly) lives in `lib.js` and is unit-tested with Node's built-in test runner. All DOM, rendering, and library glue live in `app.js` and are verified by opening `index.html` in a browser. No build step, no server, no framework.

**Tech Stack:** Vanilla JS, `markdown-it@14` (Markdown → HTML), `reveal.js@5` (slideshow), both via CDN. Node ≥18 for `node --test` (dev-time only; not needed to run the app).

## Global Constraints

- No build step, no framework, no server, no database, no accounts, no AI. — verbatim from spec.
- App runs by double-clicking `index.html` in **Chrome or Edge**.
- Folder access via native `<input type="file" webkitdirectory>` — no File System Access API, no secure context.
- Pure functions in `lib.js` must run under both browser (`<script>` globals) and Node (`require`). Guard exports with `typeof module`.
- Export is **PDF only**, via native `window.print()`. No DOCX.
- MoM template sections: **Header** (org, title, date), **Team updates** (one per team, "No updates this week" if empty), **Decisions**. Nothing else.
- File rendering: `.md/.txt/.markdown` inline via markdown-it; images inline; `.pdf` embedded; anything else a clickable filename.

---

### Task 1: `classifyFile` + test harness

**Files:**
- Create: `lib.js`
- Test: `lib.test.js`

**Interfaces:**
- Produces: `classifyFile(name: string) -> 'markdown' | 'image' | 'pdf' | 'other'`

- [ ] **Step 1: Write the failing test**

Create `lib.test.js`:

```js
'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { classifyFile } = require('./lib.js');

test('classifyFile maps extensions to kinds', () => {
  assert.equal(classifyFile('notes.md'), 'markdown');
  assert.equal(classifyFile('a.MARKDOWN'), 'markdown');
  assert.equal(classifyFile('readme.txt'), 'markdown');
  assert.equal(classifyFile('shot.PNG'), 'image');
  assert.equal(classifyFile('pic.jpeg'), 'image');
  assert.equal(classifyFile('roadmap.pdf'), 'pdf');
  assert.equal(classifyFile('update.docx'), 'other');
  assert.equal(classifyFile('noext'), 'other');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `Cannot find module './lib.js'`.

- [ ] **Step 3: Write minimal implementation**

Create `lib.js`:

```js
'use strict';

function classifyFile(name) {
  const ext = String(name).toLowerCase().split('.').pop();
  if (['md', 'markdown', 'txt'].includes(ext)) return 'markdown';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) return 'image';
  if (ext === 'pdf') return 'pdf';
  return 'other';
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { classifyFile };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: PASS — 1 test, 0 failures.

- [ ] **Step 5: Commit**

```bash
git init -q 2>/dev/null; git add lib.js lib.test.js
git commit -m "feat: classifyFile + node test harness"
```

---

### Task 2: `splitSlides`

**Files:**
- Modify: `lib.js`
- Test: `lib.test.js`

**Interfaces:**
- Produces: `splitSlides(text: string) -> string[]` — splits on lines that are exactly `---`, trims chunks, drops empty ones.

- [ ] **Step 1: Write the failing test**

Append to `lib.test.js`:

```js
const { splitSlides } = require('./lib.js');

test('splitSlides splits on --- and drops empties', () => {
  assert.deepEqual(splitSlides('a\n---\nb'), ['a', 'b']);
  assert.deepEqual(splitSlides('only one'), ['only one']);
  assert.deepEqual(splitSlides(''), []);
  assert.deepEqual(splitSlides('a\r\n---\r\nb'), ['a', 'b']);
  assert.deepEqual(splitSlides('  x  \n---\n\n'), ['x']);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `splitSlides is not a function`.

- [ ] **Step 3: Write minimal implementation**

In `lib.js`, add the function above the export guard:

```js
function splitSlides(text) {
  return String(text)
    .split(/\r?\n---\r?\n/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}
```

Update the export line:

```js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { classifyFile, splitSlides };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: PASS — 2 tests, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add lib.js lib.test.js
git commit -m "feat: splitSlides"
```

---

### Task 3: `groupFilesByTeam`

**Files:**
- Modify: `lib.js`
- Test: `lib.test.js`

**Interfaces:**
- Consumes: `classifyFile` (Task 1).
- Produces: `groupFilesByTeam(files) -> Array<{ team: string, files: Array<{ name, path, kind, file }> }>`, sorted by team name. `files` is any iterable of objects with `.name` and `.webkitRelativePath` (real `File` objects in the browser). Files not at least two levels deep (`root/team/file`) are skipped.

- [ ] **Step 1: Write the failing test**

Append to `lib.test.js`:

```js
const { groupFilesByTeam } = require('./lib.js');

test('groupFilesByTeam groups by second path segment, sorted', () => {
  const files = [
    { name: 'notes.md', webkitRelativePath: 'team/Tech/notes.md' },
    { name: 'shot.png', webkitRelativePath: 'team/Tech/shot.png' },
    { name: 'roadmap.pdf', webkitRelativePath: 'team/R&D/roadmap.pdf' },
    { name: 'stray.txt', webkitRelativePath: 'team/stray.txt' }, // skipped: too shallow
  ];
  const groups = groupFilesByTeam(files);
  assert.deepEqual(groups.map((g) => g.team), ['R&D', 'Tech']);
  const tech = groups.find((g) => g.team === 'Tech');
  assert.equal(tech.files.length, 2);
  assert.equal(tech.files[0].kind, 'markdown');
  assert.equal(tech.files[1].kind, 'image');
  assert.equal(tech.files[0].file, files[0]); // original passed through
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `groupFilesByTeam is not a function`.

- [ ] **Step 3: Write minimal implementation**

In `lib.js`, add:

```js
function groupFilesByTeam(files) {
  const map = new Map();
  for (const f of files) {
    const parts = String(f.webkitRelativePath).split('/');
    if (parts.length < 3) continue; // need root/team/file
    const team = parts[1];
    if (!map.has(team)) map.set(team, []);
    map.get(team).push({
      name: f.name,
      path: f.webkitRelativePath,
      kind: classifyFile(f.name),
      file: f,
    });
  }
  return [...map.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([team, files]) => ({ team, files }));
}
```

Update the export line:

```js
  module.exports = { classifyFile, splitSlides, groupFilesByTeam };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: PASS — 3 tests, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add lib.js lib.test.js
git commit -m "feat: groupFilesByTeam"
```

---

### Task 4: `buildMinutesMarkdown`

**Files:**
- Modify: `lib.js`
- Test: `lib.test.js`

**Interfaces:**
- Produces: `buildMinutesMarkdown({ org, title, date, teams, decisions }) -> string`. `teams` is `Array<{ team: string, notes: string }>`. Empty/whitespace notes render as `_No updates this week_`; empty decisions render as `_None recorded_`.

- [ ] **Step 1: Write the failing test**

Append to `lib.test.js`:

```js
const { buildMinutesMarkdown } = require('./lib.js');

test('buildMinutesMarkdown fills template with empty fallbacks', () => {
  const md = buildMinutesMarkdown({
    org: 'Ospit',
    title: 'Weekly Sync',
    date: '2026-07-03',
    teams: [
      { team: 'Tech', notes: 'Shipped login.' },
      { team: 'R&D', notes: '   ' },
    ],
    decisions: '',
  });
  assert.match(md, /# Weekly Sync/);
  assert.match(md, /\*\*Organization:\*\* Ospit/);
  assert.match(md, /\*\*Date:\*\* 2026-07-03/);
  assert.match(md, /### Tech\n\nShipped login\./);
  assert.match(md, /### R&D\n\n_No updates this week_/);
  assert.match(md, /## Decisions\n\n_None recorded_/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `buildMinutesMarkdown is not a function`.

- [ ] **Step 3: Write minimal implementation**

In `lib.js`, add:

```js
function buildMinutesMarkdown({ org, title, date, teams, decisions }) {
  const out = [`# ${title || 'Meeting Minutes'}`, ''];
  if (org) out.push(`**Organization:** ${org}`);
  out.push(`**Date:** ${date || ''}`, '', '## Team Updates', '');
  for (const t of teams || []) {
    out.push(`### ${t.team}`, '');
    out.push(t.notes && t.notes.trim() ? t.notes.trim() : '_No updates this week_', '');
  }
  out.push('## Decisions', '');
  out.push(decisions && decisions.trim() ? decisions.trim() : '_None recorded_', '');
  return out.join('\n');
}
```

Update the export line:

```js
  module.exports = { classifyFile, splitSlides, groupFilesByTeam, buildMinutesMarkdown };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: PASS — 4 tests, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add lib.js lib.test.js
git commit -m "feat: buildMinutesMarkdown"
```

---

### Task 5: HTML shell, styles, and screen navigation

**Files:**
- Create: `index.html`
- Create: `style.css`

**Interfaces:**
- Produces: three screen containers with ids `#screen-before`, `#screen-during`, `#screen-after`; a nav with `data-screen` buttons; loads `lib.js` then `app.js`; loads markdown-it and reveal.js from CDN. `app.js` (Tasks 6–8) attaches to these ids.

- [ ] **Step 1: Create `index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Meeting Minutes</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/theme/white.css" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <nav id="nav">
    <button data-screen="before" class="active">1 · Before</button>
    <button data-screen="during">2 · During</button>
    <button data-screen="after">3 · After</button>
    <label id="folder-pick">
      Open team folder
      <input type="file" id="folderInput" webkitdirectory directory multiple hidden />
    </label>
  </nav>

  <main>
    <section id="screen-before" class="screen active">
      <p class="hint" id="before-hint">Click “Open team folder” and pick your <code>team/</code> folder.</p>
      <div class="reveal" id="deck"><div class="slides" id="slides"></div></div>
    </section>

    <section id="screen-during" class="screen">
      <p class="hint" id="during-hint">Open a team folder first — a note box appears per team.</p>
      <div id="capture"></div>
    </section>

    <section id="screen-after" class="screen">
      <div class="mom-header no-print">
        <input id="mom-org" placeholder="Organization" />
        <input id="mom-title" placeholder="Meeting title" />
        <input id="mom-date" type="date" />
        <textarea id="mom-decisions" placeholder="Decisions (one per line)"></textarea>
        <button id="mom-generate">Generate minutes</button>
        <button id="mom-print">Print / Save PDF</button>
      </div>
      <article id="minutes"></article>
    </section>
  </main>

  <script src="https://cdn.jsdelivr.net/npm/markdown-it@14/dist/markdown-it.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"></script>
  <script src="lib.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `style.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font: 16px/1.5 system-ui, sans-serif; color: #1a1a1a; }

#nav { display: flex; gap: .5rem; align-items: center; padding: .5rem 1rem;
  border-bottom: 1px solid #ddd; background: #fafafa; position: sticky; top: 0; z-index: 10; }
#nav button { padding: .4rem .8rem; border: 1px solid #ccc; background: #fff; border-radius: 6px; cursor: pointer; }
#nav button.active { background: #1a1a1a; color: #fff; }
#folder-pick { margin-left: auto; padding: .4rem .8rem; border: 1px solid #ccc;
  border-radius: 6px; cursor: pointer; background: #fff; }

.screen { display: none; padding: 1rem; }
.screen.active { display: block; }
.hint { color: #666; }

/* Before: reveal deck only tall enough to preview; F for fullscreen */
#screen-before .reveal { height: 78vh; }

/* During: one card per team */
#capture .team-card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
#capture h3 { margin: 0 0 .5rem; }
#capture textarea { width: 100%; min-height: 5rem; font: inherit; }
#capture .preview { border-top: 1px dashed #ddd; margin-top: .5rem; padding-top: .5rem; color: #333; }

/* After: header controls + rendered minutes */
.mom-header { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
.mom-header input, .mom-header textarea { font: inherit; padding: .4rem; }
#minutes { max-width: 720px; margin: 0 auto; }

/* Print: only the minutes */
@media print {
  #nav, .no-print, #screen-before, #screen-during { display: none !important; }
  .screen { display: block !important; padding: 0; }
  #minutes { max-width: none; }
}
```

- [ ] **Step 3: Verify in browser**

Open `index.html` in Chrome. Expected: three nav buttons; clicking each switches which screen is visible (nav wiring lands in Task 6 — for now only "Before" shows). No console errors except that `app.js` is empty. Confirm the reveal and markdown-it scripts load (Network tab, 200s).

- [ ] **Step 4: Commit**

```bash
git add index.html style.css
git commit -m "feat: html shell, styles, screen layout"
```

---

### Task 6: Before screen — folder → slideshow

**Files:**
- Create: `app.js`

**Interfaces:**
- Consumes: `groupFilesByTeam`, `splitSlides`, `classifyFile` (globals from `lib.js`); `window.markdownit`, `window.Reveal`.
- Produces: module-level `STATE.groups` (result of `groupFilesByTeam`) for Tasks 7–8; nav switching via `showScreen(name)`; `renderSlides()`.

- [ ] **Step 1: Write `app.js`**

```js
'use strict';

const md = window.markdownit({ html: false, linkify: true, breaks: true });
const STATE = { groups: [], deck: null };

// ---- nav ----
function showScreen(name) {
  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
  document.querySelectorAll('#nav button').forEach((b) => b.classList.remove('active'));
  document.getElementById('screen-' + name).classList.add('active');
  document.querySelector(`#nav button[data-screen="${name}"]`).classList.add('active');
  if (name === 'before' && STATE.deck) STATE.deck.layout();
}
document.querySelectorAll('#nav button[data-screen]').forEach((b) => {
  b.addEventListener('click', () => showScreen(b.dataset.screen));
});

// ---- read one file into a reveal <section> (async) ----
async function fileToSection(entry) {
  if (entry.kind === 'markdown') {
    const text = await entry.file.text();
    return splitSlides(text)
      .map((chunk) => `<section>${md.render(chunk)}</section>`)
      .join('') || `<section><em>${entry.name} (empty)</em></section>`;
  }
  const url = URL.createObjectURL(entry.file);
  if (entry.kind === 'image') {
    return `<section><h3>${entry.name}</h3><img src="${url}" style="max-height:70vh" /></section>`;
  }
  if (entry.kind === 'pdf') {
    return `<section><h3>${entry.name}</h3><embed src="${url}" type="application/pdf" style="width:90%;height:70vh" /></section>`;
  }
  return `<section><h3>${entry.name}</h3><a href="${url}" target="_blank" rel="noopener">Open ${entry.name}</a></section>`;
}

// ---- build the whole deck ----
async function renderSlides() {
  const slides = document.getElementById('slides');
  const parts = [];
  for (const g of STATE.groups) {
    const inner = [`<section><h2>${g.team}</h2></section>`];
    for (const entry of g.files) inner.push(await fileToSection(entry));
    // one horizontal group per team, files as vertical slides
    parts.push(`<section>${inner.join('')}</section>`);
  }
  slides.innerHTML = parts.join('') || '<section>No teams found.</section>';

  if (STATE.deck) {
    STATE.deck.sync();
    STATE.deck.slide(0);
  } else {
    STATE.deck = new window.Reveal(document.getElementById('deck'), { embedded: true, hash: false });
    STATE.deck.initialize();
  }
}

// ---- folder input ----
document.getElementById('folderInput').addEventListener('change', async (e) => {
  STATE.groups = groupFilesByTeam([...e.target.files]);
  document.getElementById('before-hint').style.display = STATE.groups.length ? 'none' : '';
  document.getElementById('during-hint').style.display = STATE.groups.length ? 'none' : '';
  await renderSlides();
  buildCapture();   // defined in Task 7
});

showScreen('before');
```

Note: `buildCapture()` is added in Task 7. Until then, temporarily stub it at the bottom of `app.js`: `function buildCapture() {}` — Task 7 replaces the stub.

- [ ] **Step 2: Add the temporary stub**

At the very bottom of `app.js` add:

```js
function buildCapture() {} // replaced in Task 7
```

- [ ] **Step 3: Verify in browser**

Create a test folder `team/Tech/notes.md` containing `# Tech\n\nShipped login.\n\n---\n\nNext: billing.` and `team/R&D/roadmap.pdf` (any small PDF). Open `index.html`, click **Open team folder**, pick `team/`. Expected: hint disappears; deck shows a "Tech" title slide, then two content slides (split on `---`), then an "R&D" slide, then the embedded PDF. Press **F** → fullscreen present mode. Arrow keys navigate.

- [ ] **Step 4: Commit**

```bash
git add app.js
git commit -m "feat: before screen — folder to reveal.js slideshow"
```

---

### Task 7: During screen — per-team note capture

**Files:**
- Modify: `app.js`

**Interfaces:**
- Consumes: `STATE.groups`, `md`.
- Produces: `buildCapture()` (replaces the Task 6 stub); `STATE.notes` = `{ [team]: string }` kept in sync with the textareas.

- [ ] **Step 1: Replace the stub with the real implementation**

In `app.js`, delete `function buildCapture() {}` and add:

```js
function buildCapture() {
  const box = document.getElementById('capture');
  box.innerHTML = '';
  STATE.notes = {};
  for (const g of STATE.groups) {
    STATE.notes[g.team] = '';
    const card = document.createElement('div');
    card.className = 'team-card';
    card.innerHTML = `<h3>${g.team}</h3>
      <textarea placeholder="Notes for ${g.team}…"></textarea>
      <div class="preview"></div>`;
    const ta = card.querySelector('textarea');
    const pv = card.querySelector('.preview');
    ta.addEventListener('input', () => {
      STATE.notes[g.team] = ta.value;
      pv.innerHTML = md.render(ta.value);
    });
    box.appendChild(card);
  }
}
```

Add `notes: {}` to the initial `STATE` object at the top of `app.js`:

```js
const STATE = { groups: [], deck: null, notes: {} };
```

- [ ] **Step 2: Verify in browser**

Reload, open the `team/` folder, click **2 · During**. Expected: one card per team (Tech, R&D) with a textarea. Type `**bold** and a list:\n- one\n- two` in Tech — the preview below renders formatted HTML live.

- [ ] **Step 3: Commit**

```bash
git add app.js
git commit -m "feat: during screen — per-team note capture with live preview"
```

---

### Task 8: After screen — minutes + PDF

**Files:**
- Modify: `app.js`

**Interfaces:**
- Consumes: `STATE.groups`, `STATE.notes`, `buildMinutesMarkdown`, `md`.
- Produces: `generateMinutes()` wired to `#mom-generate`; `window.print()` wired to `#mom-print`.

- [ ] **Step 1: Add the minutes wiring**

Append to `app.js`:

```js
function generateMinutes() {
  const markdown = buildMinutesMarkdown({
    org: document.getElementById('mom-org').value,
    title: document.getElementById('mom-title').value,
    date: document.getElementById('mom-date').value,
    teams: STATE.groups.map((g) => ({ team: g.team, notes: STATE.notes[g.team] || '' })),
    decisions: document.getElementById('mom-decisions').value,
  });
  document.getElementById('minutes').innerHTML = md.render(markdown);
}

document.getElementById('mom-generate').addEventListener('click', generateMinutes);
document.getElementById('mom-print').addEventListener('click', () => {
  generateMinutes();
  window.print();
});
```

- [ ] **Step 2: Verify in browser**

Reload, open `team/`, add a note for Tech in **During**, leave R&D empty. Go to **3 · After**, fill org/title/date + a decision, click **Generate minutes**. Expected: rendered minutes with Tech's note, `R&D` showing *No updates this week*, and the Decisions section. Click **Print / Save PDF** → browser print dialog shows only the minutes (nav and header controls hidden). Save as PDF and confirm layout.

- [ ] **Step 3: Commit**

```bash
git add app.js
git commit -m "feat: after screen — minutes template + print to PDF"
```

---

## Self-Review

**Spec coverage:**
- Admin-only, single machine, no server/login/DB/AI → Global Constraints; no backend code anywhere. ✓
- BEFORE: any-file-type submissions per team → slideshow → Task 1 (`classifyFile`), Task 6 (`fileToSection` handles markdown/image/pdf/other), Task 6 verify. ✓
- Editable teams via subfolders → `groupFilesByTeam` uses folder names, no hardcoded teams (Task 3). ✓
- `---` splits slides within a file → `splitSlides` (Task 2), used in Task 6. ✓
- DURING: one capture section per team, live preview → Task 7. ✓
- AFTER: MoM template (Header/Team updates/Decisions), "No updates this week" fallback, PDF via print → Task 4 + Task 8 + print CSS in Task 5. ✓
- Runs by double-clicking `index.html` in Chrome/Edge → Task 5 shell, no build. ✓
- Out of scope (AI, DOCX, sync, action items, attendees) → none added. ✓

**Placeholder scan:** No TBD/TODO. The one intentional stub (`buildCapture`) is introduced in Task 6 and explicitly replaced in Task 7. ✓

**Type consistency:** `classifyFile`, `splitSlides`, `groupFilesByTeam`, `buildMinutesMarkdown` signatures match between `lib.js` definitions, tests, and `app.js` call sites. `STATE.groups` shape (`{team, files:[{name,kind,file}]}`) is produced in Task 3 and consumed identically in Tasks 6–8. `STATE.notes` keyed by team name, written in Task 7, read in Task 8. ✓

**Known ceiling (`ponytail:`):** CDN scripts require internet on first load. If the meeting laptop is offline, vendor `markdown-it`, `reveal.js`, and `reveal.css` locally and swap the CDN URLs — add when offline use is actually needed.
