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

// ---- read one file into one or more reveal <section>s (async) ----
// Each file (or each `---` chunk of a doc) is its own full-page slide, headed by
// "Team · filename". Flat structure: every slide is navigated left/right.
async function fileToSection(entry, team) {
  const head = (extra = '') =>
    `<div class="slide-head">${esc(team)} · ${esc(entry.name)}${extra}</div>`;

  if (entry.kind === 'markdown') {
    const text = await entry.file.text();
    if (!text.trim()) return `<section class="doc">${head()}<em>(empty)</em></section>`;
    // Whole file on one slide; `---` becomes an <hr> divider between projects.
    return `<section class="doc">${head()}<div class="doc-body">${md.render(text)}</div></section>`;
  }
  const url = URL.createObjectURL(entry.file);
  if (entry.kind === 'image') {
    return `<section class="media">${head()}<img src="${url}" /></section>`;
  }
  if (entry.kind === 'pdf') {
    return `<section class="media">${head()}<embed src="${url}" type="application/pdf" /></section>`;
  }
  return `<section class="doc">${head()}<a class="filelink" href="${url}" target="_blank" rel="noopener">Open ${esc(entry.name)}</a></section>`;
}

// ---- build the whole deck (flat: team title page, then a page per file) ----
async function renderSlides() {
  const slides = document.getElementById('slides');
  const parts = [];
  for (const g of STATE.groups) {
    parts.push(`<section class="team-title"><h1>${esc(g.team)}</h1></section>`);
    for (const entry of g.files) parts.push(await fileToSection(entry, g.team));
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

// ---- load files (shared by folder picker and drag-drop) ----
// items: array of File objects (folder input) or {name, webkitRelativePath, file} wrappers (drop).
async function loadFiles(items) {
  if (STATE.rendering) return; // single in-flight guard
  const accepted = items.filter((f) => isAccepted(f.name));
  const rejected = items.length - accepted.length;
  const hint = document.getElementById('before-hint');
  if (!accepted.length) {
    hint.style.display = '';
    hint.innerHTML = 'Only <strong>document</strong> and <strong>picture</strong> files are supported (pdf, doc/docx, txt, md, png, jpg…). Try again.';
    return;
  }
  STATE.rendering = true;
  try {
    STATE.groups = groupFilesByTeam(accepted);
    if (rejected) console.warn(`${rejected} file(s) skipped — not a document or picture.`);
    const has = STATE.groups.length;
    document.getElementById('before-hint').style.display = has ? 'none' : '';
    document.getElementById('during-hint').style.display = has ? 'none' : '';
    showScreen('before'); // init Reveal while the deck container is visible
    await renderSlides();
    buildCapture();
  } finally {
    STATE.rendering = false;
  }
}

document.getElementById('folderInput').addEventListener('change', (e) => loadFiles([...e.target.files]));

// ---- drag-and-drop (files or a folder, dropped anywhere on the page) ----
// Read all entries from a directory reader (readEntries returns in batches — must
// loop until it returns empty, or large folders get truncated).
function readAllEntries(reader) {
  return new Promise((resolve) => {
    const all = [];
    const next = () =>
      reader.readEntries((batch) => {
        if (!batch.length) return resolve(all);
        all.push(...batch);
        next();
      }, () => resolve(all));
    next();
  });
}

// Recurse a dropped directory entry into flat {name, webkitRelativePath, file}
// wrappers whose path matches the folder-input shape (root/team/file).
async function readEntry(entry, prefix, out) {
  if (entry.isFile) {
    await new Promise((resolve) => {
      entry.file((file) => {
        out.push({ name: file.name, webkitRelativePath: prefix + file.name, file });
        resolve();
      }, resolve);
    });
  } else if (entry.isDirectory) {
    const entries = await readAllEntries(entry.createReader());
    for (const e of entries) await readEntry(e, prefix + entry.name + '/', out);
  }
}

const body = document.body;
body.addEventListener('dragover', (e) => { e.preventDefault(); body.classList.add('dragging'); });
body.addEventListener('dragleave', (e) => { if (e.target === body) body.classList.remove('dragging'); });
body.addEventListener('drop', async (e) => {
  e.preventDefault();
  body.classList.remove('dragging');
  // webkitGetAsEntry() must be read synchronously, before any await.
  const entries = [...(e.dataTransfer.items || [])]
    .map((it) => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null))
    .filter(Boolean);
  const droppedFiles = [...e.dataTransfer.files]; // reliable on file://, unlike entry.file()
  const out = [];
  // Only use the entry API when an actual directory was dropped (to preserve team
  // grouping). Plain files go straight through dataTransfer.files.
  if (entries.some((en) => en.isDirectory)) {
    for (const en of entries) await readEntry(en, '', out);
  }
  if (!out.length) {
    for (const f of droppedFiles) out.push({ name: f.name, webkitRelativePath: f.name, file: f });
  }
  loadFiles(out);
});

showScreen('before');

// ---- during screen: per-team note capture ----
function buildCapture() {
  const box = document.getElementById('capture');
  box.innerHTML = '';
  // Keep notes already typed for teams that still exist (folder re-pick mid-meeting
  // must not silently wipe captured notes); drop only teams no longer present.
  const kept = {};
  for (const g of STATE.groups) kept[g.team] = STATE.notes[g.team] || '';
  STATE.notes = kept;
  for (const g of STATE.groups) {
    const card = document.createElement('div');
    card.className = 'team-card';
    card.innerHTML = `<h3>${esc(g.team)}</h3>
      <textarea placeholder="Notes for ${esc(g.team)}…"></textarea>
      <div class="preview"></div>`;
    const ta = card.querySelector('textarea');
    const pv = card.querySelector('.preview');
    ta.value = STATE.notes[g.team];              // restore any preserved note
    pv.innerHTML = md.render(ta.value);
    ta.addEventListener('input', () => {
      STATE.notes[g.team] = ta.value;
      pv.innerHTML = md.render(ta.value);
    });
    box.appendChild(card);
  }
}

// ponytail: demo helper — fills each loaded team's box with plausible random notes
// so you can test the minutes without typing. Generic over whatever teams are loaded.
const SAMPLE = {
  done: ['shipped the new build', 'closed 4 support tickets', 'finished the Q3 report',
    'onboarded a new client', 'fixed the login bug', 'launched the email campaign',
    'completed the security review', 'migrated 60% of accounts'],
  next: ['start the data migration', 'review the new designs', 'follow up with the client',
    'prep the customer demo', 'write the release notes', 'plan the next sprint'],
  block: ['waiting on API keys', 'need design sign-off', 'blocked by the vendor',
    'pending budget approval', 'waiting on legal review'],
  task: ['send the proposal', 'update the roadmap', 'book the review', 'ship the fix', 'draft the email'],
  owner: ['sara', 'james', 'mei', 'omar', 'lena', 'raj'],
};
const pick = (a) => a[Math.floor(Math.random() * a.length)];
function sampleNote() {
  return [
    `- Done: ${pick(SAMPLE.done)}`,
    `- Next: ${pick(SAMPLE.next)}`,
    `- **Blocker:** ${pick(SAMPLE.block)}`,
    `- Action: ${pick(SAMPLE.task)} — @${pick(SAMPLE.owner)}`,
  ].join('\n');
}
function fillSampleNotes() {
  if (!STATE.groups.length) return;
  for (const g of STATE.groups) STATE.notes[g.team] = sampleNote();
  buildCapture();
}
document.getElementById('fill-demo').addEventListener('click', fillSampleNotes);

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
