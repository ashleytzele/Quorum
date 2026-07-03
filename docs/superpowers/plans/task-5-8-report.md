# Tasks 5-8 Implementation Report

Implemented Tasks 5 (HTML shell + styles), 6 (before screen), 7 (during screen —
replaces the Task 6 `buildCapture` stub with the real implementation), and 8
(after screen — minutes + PDF). `app.js` is the single coherent end state of
Tasks 6+7+8 combined: no leftover stub, `STATE` initialized with `notes: {}`.

## Verification

### `node --check`

```
$ node --check app.js && echo "app.js OK" && node --check lib.js && echo "lib.js OK"
app.js OK
lib.js OK
```

No syntax errors in either file.

### Element id cross-check

Every `getElementById`/`querySelector` target in `app.js` matches an id or
selector present in `index.html`:

| app.js reference | index.html |
|---|---|
| `before-hint` | present |
| `capture` | present |
| `deck` | present |
| `during-hint` | present |
| `folderInput` | present |
| `minutes` | present |
| `mom-date` | present |
| `mom-decisions` | present |
| `mom-generate` | present |
| `mom-org` | present |
| `mom-print` | present |
| `mom-title` | present |
| `slides` | present |
| `` `screen-${name}` `` (before/during/after) | `screen-before`, `screen-during`, `screen-after` present |
| `#nav button[data-screen]` | 3 buttons with `data-screen="before"/"during"/"after"` present |
| `.screen`, `#nav button`, `textarea`, `.preview` (scoped querySelectors) | matching classes/elements present |

Result: **no mismatches**.

Script load order in `index.html`: `markdown-it@14` → `reveal.js@5` → `lib.js`
→ `app.js`, matching the plan exactly.

## Final file contents

### `index.html`

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

### `style.css`

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

### `app.js`

```js
'use strict';

const md = window.markdownit({ html: false, linkify: true, breaks: true });
const STATE = { groups: [], deck: null, notes: {} };

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

// ---- during screen: per-team note capture ----
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

// ---- after screen: minutes + PDF ----
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

## Notes on Task 6/7 stub sequencing

Per the parent instruction, the intermediate `function buildCapture() {}` stub
from Task 6 Step 2 was never left in the final file — it was written directly
as the real Task 7 implementation in one pass, so the committed `app.js` is
the combined end state of Tasks 6+7+8, not an intermediate snapshot.

## Commit

```
517d30b feat: UI — before slideshow, during capture, after minutes/PDF
 3 files changed, 191 insertions(+)
 create mode 100644 app.js
 create mode 100644 index.html
 create mode 100644 style.css
```

---

# Bugfix follow-up: three defects in app.js

Fixed three defects in `app.js` only (no other files touched):

1. **Reveal.js init while hidden** — the `#folderInput` change handler now calls
   `showScreen('before')` before `await renderSlides()`, so the deck initializes
   while `#screen-before` is visible instead of `display:none`.
2. **Unescaped interpolation into innerHTML** — added an `esc()` helper and
   wrapped every team/file name interpolated into HTML (`fileToSection`'s
   `entry.name` occurrences and link text, `renderSlides`'s `<h2>${g.team}</h2>`,
   `buildCapture`'s `<h3>${g.team}</h3>` and the textarea `placeholder`
   attribute). Object URLs in `href`/`src` and `md.render(...)` output were left
   untouched per instructions.
3. **No re-entrancy guard** — added `STATE.rendering` flag: the folder change
   handler returns early if a previous run is still in flight, sets the flag at
   the start, and clears it in a `finally`.

## Verification

### `node --check app.js`

```
$ node --check app.js && echo "SYNTAX OK"
SYNTAX OK
```

### Element/function integrity

No element ids, event listeners, or the `showScreen`/`renderSlides`/
`buildCapture`/`generateMinutes` function names were removed or renamed.

## Final `app.js` contents (post-fix)

```js
'use strict';

const md = window.markdownit({ html: false, linkify: true, breaks: true });
const STATE = { groups: [], deck: null, notes: {}, rendering: false };

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

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
      .join('') || `<section><em>${esc(entry.name)} (empty)</em></section>`;
  }
  const url = URL.createObjectURL(entry.file);
  if (entry.kind === 'image') {
    return `<section><h3>${esc(entry.name)}</h3><img src="${url}" style="max-height:70vh" /></section>`;
  }
  if (entry.kind === 'pdf') {
    return `<section><h3>${esc(entry.name)}</h3><embed src="${url}" type="application/pdf" style="width:90%;height:70vh" /></section>`;
  }
  return `<section><h3>${esc(entry.name)}</h3><a href="${url}" target="_blank" rel="noopener">Open ${esc(entry.name)}</a></section>`;
}

// ---- build the whole deck ----
async function renderSlides() {
  const slides = document.getElementById('slides');
  const parts = [];
  for (const g of STATE.groups) {
    const inner = [`<section><h2>${esc(g.team)}</h2></section>`];
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
  if (STATE.rendering) return; // ponytail: single in-flight guard, no queue needed for a folder picker
  STATE.rendering = true;
  try {
    STATE.groups = groupFilesByTeam([...e.target.files]);
    document.getElementById('before-hint').style.display = STATE.groups.length ? 'none' : '';
    document.getElementById('during-hint').style.display = STATE.groups.length ? 'none' : '';
    showScreen('before'); // init Reveal while the deck container is visible
    await renderSlides();
    buildCapture();   // defined in Task 7
  } finally {
    STATE.rendering = false;
  }
});

showScreen('before');

// ---- during screen: per-team note capture ----
function buildCapture() {
  const box = document.getElementById('capture');
  box.innerHTML = '';
  STATE.notes = {};
  for (const g of STATE.groups) {
    STATE.notes[g.team] = '';
    const card = document.createElement('div');
    card.className = 'team-card';
    card.innerHTML = `<h3>${esc(g.team)}</h3>
      <textarea placeholder="Notes for ${esc(g.team)}…"></textarea>
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

// ---- after screen: minutes + PDF ----
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

## Commit

```
a128965 fix: escape names, init reveal while visible, guard re-entrant folder load
 1 file changed, 24 insertions(+), 13 deletions(-)
```
