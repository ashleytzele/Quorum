const api = (u, opts) => fetch(u, opts).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)));
let currentId = null;

// ponytail: brief's markup is built via innerHTML with raw interpolation (title/name/content
// come from user input) — escape before inserting to avoid breaking markup / injecting HTML.
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

async function loadMeetings() {
  const list = await api('/api/meetings');
  const ul = document.getElementById('meeting-list');
  ul.innerHTML = '';
  list.forEach(m => {
    const li = document.createElement('li');
    li.style.cssText = 'padding:8px;cursor:pointer;border-radius:8px;';
    li.innerHTML = `${esc(m.title)} <span class="pill pill-muted">${esc(m.status)}</span><br><small>${esc(m.date)}</small>`;
    li.onclick = () => openMeeting(m.id);
    ul.appendChild(li);
  });
}

async function loadTemplates(sel, chosen) {
  const t = await api('/api/templates');
  sel.innerHTML = t.map(x => `<option value="${esc(x.stem)}"${x.stem===chosen?' selected':''}>${esc(x.name)}</option>`).join('');
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
  wrap.innerHTML = `<input class="input" value="${esc(name||'')}" placeholder="Project name" style="margin:6px 0;">
    <textarea class="textarea" rows="4" style="width:100%;">${esc(content||'')}</textarea>`;
  const [nameEl, taEl] = wrap.querySelectorAll('input,textarea');
  const save = () => nameEl.value && api(`/api/meetings/${currentId}/notes/${encodeURIComponent(nameEl.value)}`,
    {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content: taEl.value})})
    .catch(e => alert(e.error || 'could not save note'));
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
  if (mine) loadMeetings();   // a stop just finished — refresh sidebar status pill
}

async function generate() {
  const st = document.getElementById('gen-status'); st.textContent = 'generating…';
  const btn = document.getElementById('generate-btn');
  btn.disabled = true;
  try {
    const r = await api(`/api/meetings/${currentId}/generate`, {method:'POST'});
    document.getElementById('minutes-edit').value = r.minutes;
    st.textContent = `projects (${r.projects.length}): ${r.projects.join(', ')}`;
    loadMeetings();
  } catch (e) { st.textContent = 'failed: ' + (e.error || 'error'); }
  finally { btn.disabled = false; }
}

document.getElementById('new-meeting-btn').onclick = async () => {
  const t = await api('/api/templates');
  const m = await api('/api/meetings', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title:'New meeting', template: (t[0]||{}).stem || 'weekly_review'})});
  await loadMeetings(); openMeeting(m.id);
};

loadMeetings();
