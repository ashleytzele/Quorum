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

// ---- load files (shared by folder picker and drag-drop) ----
// items: array of File objects (folder input) or {name, webkitRelativePath, file} wrappers (drop).
async function loadFiles(items) {
  if (STATE.rendering || !items.length) return; // single in-flight guard
  STATE.rendering = true;
  try {
    STATE.groups = groupFilesByTeam(items);
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
// Recurse dropped directory entries into flat {name, webkitRelativePath, file} wrappers
// whose path matches the folder-input shape (root/team/file), so grouping is identical.
function readEntry(entry, prefix, out) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((file) => {
        out.push({ name: file.name, webkitRelativePath: prefix + file.name, file });
        resolve();
      }, resolve);
    } else if (entry.isDirectory) {
      entry.createReader().readEntries((entries) => {
        Promise.all(entries.map((e) => readEntry(e, prefix + entry.name + '/', out))).then(resolve);
      }, resolve);
    } else {
      resolve();
    }
  });
}

const body = document.body;
body.addEventListener('dragover', (e) => { e.preventDefault(); body.classList.add('dragging'); });
body.addEventListener('dragleave', (e) => { if (e.target === body) body.classList.remove('dragging'); });
body.addEventListener('drop', async (e) => {
  e.preventDefault();
  body.classList.remove('dragging');
  // webkitGetAsEntry() must be called synchronously, before any await.
  const entries = [...e.dataTransfer.items]
    .map((it) => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null))
    .filter(Boolean);
  const out = [];
  if (entries.length) {
    await Promise.all(entries.map((en) => readEntry(en, '', out)));
  } else {
    for (const f of e.dataTransfer.files) out.push({ name: f.name, webkitRelativePath: f.name, file: f });
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
