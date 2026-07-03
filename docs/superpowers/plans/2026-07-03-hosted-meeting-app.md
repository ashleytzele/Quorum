# Hosted Meeting App Implementation Plan

**Goal:** Turn the local tool into a hosted multi-team app: teams log in, upload files + write notes before a meeting; admin presents the combined slideshow and exports one MoM PDF.

**Architecture:** Static HTML/CSS/JS frontend (no build) + Supabase (Auth + Postgres + Storage) as the managed backend. Frontend visuals come from claude.ai/design and are wired to Supabase here. Reuses the local tool's pure functions and slideshow renderer.

**Tech Stack:** Vanilla JS, `@supabase/supabase-js` (CDN), `markdown-it`, `reveal.js`, Supabase cloud, Netlify hosting.

## Global Constraints

- No build step, no framework. Multi-page static site + CDN scripts.
- Supabase is the only backend. No custom server.
- Row-Level Security ON for every table — a team may read/write only its own rows; admin reads all. Security is not optional here.
- Documents + pictures only (reuse `isAccepted`).
- Export is PDF via `window.print()`. No DOCX.
- Secrets: only the Supabase **anon** public key ships in the frontend (safe by design when RLS is on). The service-role key is never in frontend code.

---

## Phase 0 — Supabase project & schema

### Task 1: Create project and run the schema

**You (one-time, in the Supabase dashboard):**
1. Create a free account at supabase.com, create a project, note the **Project URL** and **anon public key** (Settings → API).
2. Open the SQL editor and run the schema below.
3. Create a **private** Storage bucket named `submissions`.

- [ ] **Step 1: Run schema SQL** (Supabase → SQL editor)

```sql
create table teams (
  id uuid primary key default gen_random_uuid(),
  name text unique not null
);

create table profiles (
  id uuid primary key references auth.users on delete cascade,
  team_id uuid references teams,
  role text not null default 'member' check (role in ('member','admin'))
);

create table meetings (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  meeting_date date,
  org text,
  is_active boolean not null default true,
  minutes_final text,               -- exported MoM markdown, set on finalize (History reads this)
  created_at timestamptz not null default now()
);

create table notes (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null references meetings on delete cascade,
  team_id uuid not null references teams,
  pre_note text not null default '',   -- pre-meeting note → shown in the presentation
  content text not null default '',    -- meeting notes → fill the minutes
  submitted boolean not null default false, -- Draft/Submitted toggle for the pre-meeting submission
  updated_at timestamptz not null default now(),
  unique (meeting_id, team_id)
);

create table submissions (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null references meetings on delete cascade,
  team_id uuid not null references teams,
  file_path text not null,
  file_name text not null,
  mime text,
  created_at timestamptz not null default now()
);
```

- [ ] **Step 2: Enable RLS and add policies**

```sql
alter table teams enable row level security;
alter table profiles enable row level security;
alter table meetings enable row level security;
alter table notes enable row level security;
alter table submissions enable row level security;

-- helpers MUST be SECURITY DEFINER: they query profiles, and the profiles RLS
-- policy calls is_admin() — without DEFINER that recurses infinitely.
create or replace function is_admin() returns boolean
  language sql stable security definer set search_path = public as $$
  select exists (select 1 from profiles where id = auth.uid() and role = 'admin');
$$;
create or replace function my_team() returns uuid
  language sql stable security definer set search_path = public as $$
  select team_id from profiles where id = auth.uid();
$$;

-- everyone authenticated can read teams and their own profile
create policy "read teams" on teams for select to authenticated using (true);
create policy "read own profile" on profiles for select to authenticated using (id = auth.uid() or is_admin());
create policy "update own profile" on profiles for update to authenticated using (id = auth.uid());

-- meetings: all read; admin writes
create policy "read meetings" on meetings for select to authenticated using (true);
create policy "admin writes meetings" on meetings for all to authenticated using (is_admin()) with check (is_admin());

-- notes: own team read/write; admin read all
create policy "team rw notes" on notes for all to authenticated
  using (team_id = my_team()) with check (team_id = my_team());
create policy "admin read notes" on notes for select to authenticated using (is_admin());

-- submissions: own team read/write; admin read all
create policy "team rw submissions" on submissions for all to authenticated
  using (team_id = my_team()) with check (team_id = my_team());
create policy "admin read submissions" on submissions for select to authenticated using (is_admin());
```

- [ ] **Step 3: Storage policies** (bucket `submissions`, path `{meeting_id}/{team_id}/{file}`)

```sql
create policy "team reads own files" on storage.objects for select to authenticated
  using (bucket_id = 'submissions'
    and ((storage.foldername(name))[2] = my_team()::text or is_admin()));
create policy "team writes own files" on storage.objects for insert to authenticated
  with check (bucket_id = 'submissions' and (storage.foldername(name))[2] = my_team()::text);
create policy "team deletes own files" on storage.objects for delete to authenticated
  using (bucket_id = 'submissions' and (storage.foldername(name))[2] = my_team()::text);
```

- [ ] **Step 4: Seed teams, users, and the active meeting**

```sql
insert into teams (name) values ('Solution Consultant'), ('Tech'), ('R&D');
-- create users via Auth → Users → Add user (email). Then map each to a team:
-- update profiles set team_id = (select id from teams where name='Tech'), role='member' where id='<user-uuid>';
-- make yourself admin:
-- update profiles set role='admin' where id='<your-user-uuid>';
insert into meetings (title, meeting_date, org, is_active)
  values ('Weekly Sync', current_date, 'Ospit', true);
```

Note: add a trigger so a `profiles` row is auto-created on signup:

```sql
-- search_path MUST be pinned or signup fails with "Database error saving new user".
create or replace function handle_new_user() returns trigger
  language plpgsql security definer set search_path = public as $$
begin insert into public.profiles (id) values (new.id) on conflict (id) do nothing; return new; end; $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function handle_new_user();
```

**Verify:** In the SQL editor, `select * from teams;` returns 3 rows; the bucket `submissions` exists and is private.

---

## Phase 1 — Config + shared client

### Task 2: Project skeleton and Supabase client

**Files:**
- Create: `web/config.js`, `web/supa.js`
- Reuse: copy `lib.js` (pure functions) into `web/lib.js` unchanged.

- [ ] **Step 1: Config** — `web/config.js`

```js
// Public values — safe to ship. RLS protects the data.
window.SUPA_URL = 'https://YOUR-PROJECT.supabase.co';
window.SUPA_ANON = 'YOUR-ANON-PUBLIC-KEY';
```

- [ ] **Step 2: Client + helpers** — `web/supa.js`

```js
const supa = window.supabase.createClient(window.SUPA_URL, window.SUPA_ANON);

async function currentProfile() {
  const { data: { user } } = await supa.auth.getUser();
  if (!user) return null;
  const { data } = await supa.from('profiles').select('*, teams(name)').eq('id', user.id).single();
  return data; // { id, team_id, role, teams: { name } }
}
async function activeMeeting() {
  const { data } = await supa.from('meetings').select('*').eq('is_active', true)
    .order('created_at', { ascending: false }).limit(1).single();
  return data;
}
async function requireAuth(redirect = 'index.html') {
  const { data: { session } } = await supa.auth.getSession();
  if (!session) location.href = redirect;
}
```

- [ ] **Step 3: Commit**

```bash
git add web/ && git commit -m "feat: supabase client, config, reused lib"
```

---

## Phase 2 — Auth (magic link)

### Task 3: Login page

**Files:** Create `web/index.html` (login) + `web/auth.js`. Use the claude.ai/design login screen markup; wire these handlers.

- [ ] **Step 1: Wire magic-link send + redirect** — `web/auth.js`

```js
const form = document.getElementById('login-form');
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const { error } = await supa.auth.signInWithOtp({
    email, options: { emailRedirectTo: location.origin + '/route.html' },
  });
  document.getElementById('login-msg').textContent =
    error ? error.message : 'Check your email for the login link.';
});
```

- [ ] **Step 2: Post-login router** — `web/route.html` (loads supa.js + this)

```js
await requireAuth('index.html');
const p = await currentProfile();
location.href = (p && p.role === 'admin') ? 'admin.html' : 'team.html';
```

- [ ] **Step 3: Verify** — Deploy or run locally over http; enter your email; click the emailed link; confirm you land on `team.html` (member) or `admin.html` (admin). Commit.

---

## Phase 3 — Team dashboard (upload files + notes)

### Task 4: Upload, list, remove files

**Files:** Create `web/team.html` (from the design) + `web/team.js`.

**Interfaces:** Consumes `isAccepted`, `classifyFile` (lib.js), `supa`, `currentProfile`, `activeMeeting`.

- [ ] **Step 1: Load context + list files**

```js
await requireAuth();
const me = await currentProfile();
const meeting = await activeMeeting();
document.getElementById('team-name').textContent = me.teams.name;
document.getElementById('meeting-title').textContent = meeting.title;

async function listFiles() {
  const { data } = await supa.from('submissions').select('*')
    .eq('meeting_id', meeting.id).eq('team_id', me.team_id).order('created_at');
  const ul = document.getElementById('file-list'); ul.innerHTML = '';
  for (const f of data) {
    const li = document.createElement('li');
    li.innerHTML = `<span>${f.file_name}</span> <button data-id="${f.id}" data-path="${f.file_path}">Remove</button>`;
    ul.appendChild(li);
  }
}
listFiles();
```

- [ ] **Step 2: Upload accepted files to Storage + record row**

```js
async function upload(files) {
  for (const file of files) {
    if (!isAccepted(file.name)) continue;
    const path = `${meeting.id}/${me.team_id}/${Date.now()}-${file.name}`;
    const { error } = await supa.storage.from('submissions').upload(path, file);
    if (error) { alert(error.message); continue; }
    await supa.from('submissions').insert({
      meeting_id: meeting.id, team_id: me.team_id,
      file_path: path, file_name: file.name, mime: file.type,
    });
  }
  listFiles();
}
document.getElementById('file-input').addEventListener('change', (e) => upload([...e.target.files]));
```

- [ ] **Step 3: Remove file** (delegated click on the list)

```js
document.getElementById('file-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-id]'); if (!btn) return;
  await supa.storage.from('submissions').remove([btn.dataset.path]);
  await supa.from('submissions').delete().eq('id', btn.dataset.id);
  listFiles();
});
```

- [ ] **Step 4: Verify** — as a team member, upload a `.md` and a `.png`; both appear; a `.zip` is rejected; Remove deletes them. In Supabase, confirm the `submissions` rows and Storage objects exist under `{meeting_id}/{team_id}/`. Commit.

### Task 5: Meeting-notes editor (feeds the minutes) — autosave + live preview

This is the **`content`** field (the note that fills the team's minutes section),
targeting ids `notes` / `notes-preview` / `save-status`.

**Files:** Modify `web/team.js`.

- [ ] **Step 1: Load, preview, autosave**

```js
const md = window.markdownit({ html: false, linkify: true, breaks: true });
const ta = document.getElementById('notes');
const pv = document.getElementById('notes-preview');

async function loadNote() {
  const { data } = await supa.from('notes').select('content')
    .eq('meeting_id', meeting.id).eq('team_id', me.team_id).maybeSingle();
  ta.value = data ? data.content : '';
  pv.innerHTML = md.render(ta.value);
}
let timer;
ta.addEventListener('input', () => {
  pv.innerHTML = md.render(ta.value);
  clearTimeout(timer);
  timer = setTimeout(saveNote, 800); // debounce autosave
});
async function saveNote() {
  await supa.from('notes').upsert(
    { meeting_id: meeting.id, team_id: me.team_id, content: ta.value, updated_at: new Date().toISOString() },
    { onConflict: 'meeting_id,team_id' });
  document.getElementById('save-status').textContent = 'Saved';
}
loadNote();
```

- [ ] **Step 2: Verify** — type notes, wait ~1s, reload the page: notes persist. In Supabase `notes` has one row for this team+meeting. Commit.

### Task 5b: Pre-meeting note (presentation) + Submitted toggle

The **`pre_note`** field (shown as a presentation slide) + the **`submitted`** flag,
targeting ids `pre-note` / `pre-note-preview` / `submit-toggle` / `submit-status`.
Both `pre_note` and `content` live in the same `notes` row — upsert merges them.

**Files:** Modify `web/team.js`.

- [ ] **Step 1: Load pre-note + submitted state, preview, autosave**

```js
const preTa = document.getElementById('pre-note');
const prePv = document.getElementById('pre-note-preview');
const toggle = document.getElementById('submit-toggle');

async function loadPre() {
  const { data } = await supa.from('notes').select('pre_note, submitted')
    .eq('meeting_id', meeting.id).eq('team_id', me.team_id).maybeSingle();
  preTa.value = data ? data.pre_note : '';
  prePv.innerHTML = md.render(preTa.value);
  setSubmitted(data ? data.submitted : false);
}
function setSubmitted(v) {
  toggle.dataset.submitted = v ? '1' : '0';
  document.getElementById('submit-status').textContent = v ? 'Submitted' : 'Draft';
}
let preTimer;
preTa.addEventListener('input', () => {
  prePv.innerHTML = md.render(preTa.value);
  clearTimeout(preTimer);
  preTimer = setTimeout(() => savePre({ pre_note: preTa.value }), 800);
});
async function savePre(fields) {
  await supa.from('notes').upsert(
    { meeting_id: meeting.id, team_id: me.team_id, updated_at: new Date().toISOString(), ...fields },
    { onConflict: 'meeting_id,team_id' });
}
loadPre();
```

- [ ] **Step 2: Wire the Submitted toggle**

```js
toggle.addEventListener('click', async () => {
  const next = toggle.dataset.submitted !== '1';
  setSubmitted(next);
  await savePre({ submitted: next });
});
```

- [ ] **Step 3: Verify** — type a pre-note (autosaves), toggle Submitted → reload:
  both the note and the Submitted state persist; `notes.pre_note` and `notes.submitted`
  are set, and `content` from Task 5 is untouched (upsert merged, not overwrote). Commit.

---

## Phase 4 — Admin dashboard

### Task 6: Meeting settings + team status

**Files:** Create `web/admin.html` (from design) + `web/admin.js`.

- [ ] **Step 1: Guard + load teams with counts**

```js
await requireAuth();
const me = await currentProfile();
if (me.role !== 'admin') location.href = 'team.html';
const meeting = await activeMeeting();

const md = window.markdownit({ html: false, linkify: true, breaks: true });
const [{ data: teams }, { data: subs }, { data: notes }] = await Promise.all([
  supa.from('teams').select('*').order('name'),
  supa.from('submissions').select('*').eq('meeting_id', meeting.id),
  supa.from('notes').select('*').eq('meeting_id', meeting.id),
]);
const filesOf = (id) => subs.filter((s) => s.team_id === id);
const noteOf = (id) => notes.find((n) => n.team_id === id) || {};
const tbody = document.getElementById('team-rows');
for (const t of teams) {
  const n = noteOf(t.id);
  const status = n.submitted ? '✓ submitted' : (n.content && n.content.trim() ? 'notes only' : '— nothing');
  const tr = document.createElement('tr');
  tr.dataset.teamId = t.id;
  tr.innerHTML = `<td>${t.name}</td><td>${filesOf(t.id).length} files</td><td>${status}</td>`;
  tbody.appendChild(tr);
}
document.getElementById('present-btn').onclick = () => location.href = 'present.html';
document.getElementById('preview-slideshow-btn').onclick = () => location.href = 'present.html';
document.getElementById('minutes-btn').onclick = () => location.href = 'minutes.html';
```

- [ ] **Step 2: Team drill-down (files + notes preview)**

```js
async function signed(path) {
  const { data } = await supa.storage.from('submissions').createSignedUrl(path, 3600);
  return data.signedUrl;
}
tbody.addEventListener('click', async (e) => {
  const tr = e.target.closest('tr[data-team-id]'); if (!tr) return;
  const n = noteOf(tr.dataset.teamId);
  document.getElementById('detail-notes').innerHTML =
    '<h4>Meeting notes</h4>' + md.render(n.content || '_none_') +
    '<h4>Pre-meeting note</h4>' + md.render(n.pre_note || '_none_');
  const list = document.getElementById('detail-files'); list.innerHTML = '';
  for (const f of filesOf(tr.dataset.teamId)) {
    const url = await signed(f.file_path);
    const li = document.createElement('li');
    li.innerHTML = `<a href="${url}" target="_blank" rel="noopener">${f.file_name}</a>`;
    list.appendChild(li);
  }
  document.getElementById('team-detail').hidden = false;
});
```

- [ ] **Step 3: Create/activate a meeting**

```js
document.getElementById('meeting-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  await supa.from('meetings').update({ is_active: false }).eq('is_active', true);
  await supa.from('meetings').insert({
    title: document.getElementById('m-title').value,
    meeting_date: document.getElementById('m-date').value,
    org: document.getElementById('m-org').value, is_active: true,
  });
  location.reload();
});
```

- [ ] **Step 4: Verify** — as admin, see all teams with file counts + submitted status;
  click a team → its files (openable) and rendered notes appear in the drawer; **Preview
  slideshow** opens the deck; create a new meeting and confirm it becomes active. Commit.

---

## Phase 5 — Present view (slideshow from cloud files)

### Task 7: Build the deck from Storage

**Files:** Create `web/present.html` (reuse the local deck markup + reveal CDN) + `web/present.js`. Reuse `classifyFile`.

- [ ] **Step 1: Fetch all teams' files, group, sign URLs, render**

```js
await requireAuth();
const meeting = await activeMeeting();
const md = window.markdownit({ html: false, linkify: true, breaks: true });

const { data: teams } = await supa.from('teams').select('*').order('name');
const { data: subs } = await supa.from('submissions').select('*').eq('meeting_id', meeting.id);
const { data: notes } = await supa.from('notes').select('team_id, pre_note').eq('meeting_id', meeting.id);
const preOf = (id) => (notes.find((n) => n.team_id === id) || {}).pre_note || '';

function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

async function signedUrl(path) {
  const { data } = await supa.storage.from('submissions').createSignedUrl(path, 3600);
  return data.signedUrl;
}
async function fileSection(s, teamName) {
  const kind = classifyFile(s.file_name);
  const head = `<div class="slide-head">${esc(teamName)} · ${esc(s.file_name)}</div>`;
  const url = await signedUrl(s.file_path);
  if (kind === 'markdown') {
    const text = await (await fetch(url)).text();
    return `<section class="doc">${head}<div class="doc-body">${md.render(text)}</div></section>`;
  }
  if (kind === 'image') return `<section class="media">${head}<img src="${url}"/></section>`;
  if (kind === 'pdf') return `<section class="media">${head}<embed src="${url}" type="application/pdf"/></section>`;
  return `<section class="doc">${head}<a class="filelink" href="${url}" target="_blank" rel="noopener">Open ${esc(s.file_name)}</a></section>`;
}

const parts = [];
for (const t of teams) {
  const mine = subs.filter((s) => s.team_id === t.id);
  const pre = preOf(t.id);
  if (!mine.length && !pre.trim()) continue; // team submitted nothing
  parts.push(`<section class="team-title"><h1>${esc(t.name)}</h1></section>`);
  if (pre.trim()) {
    parts.push(`<section class="doc"><div class="slide-head">${esc(t.name)} · pre-meeting note</div>` +
      `<div class="doc-body">${md.render(pre)}</div></section>`);
  }
  for (const s of mine) parts.push(await fileSection(s, t.name));
}
document.getElementById('slides').innerHTML = parts.join('') || '<section>No submissions yet.</section>';
new window.Reveal(document.getElementById('deck'), { hash: false }).initialize();
```

- [ ] **Step 2: Verify** — with files uploaded by ≥2 teams, the deck shows a title page per team then a page per file; images/PDFs render; press F to present. Commit. Copy `style.css` deck rules over.

---

## Phase 6 — Minutes (combined MoM)

### Task 8: Render + print

**Files:** Create `web/minutes.html` (from design) + `web/minutes.js`. Reuse `buildMinutesMarkdown`.

- [ ] **Step 1: Pull all notes, build MoM, print**

```js
await requireAuth();
const meeting = await activeMeeting();
const md = window.markdownit({ html: false, linkify: true, breaks: true });
const { data: teams } = await supa.from('teams').select('*').order('name');
const { data: notes } = await supa.from('notes').select('*').eq('meeting_id', meeting.id);
const noteFor = (id) => (notes.find((n) => n.team_id === id) || {}).content || '';

function generate() {
  const markdown = buildMinutesMarkdown({
    org: meeting.org, title: meeting.title, date: meeting.meeting_date,
    teams: teams.map((t) => ({ team: t.name, notes: noteFor(t.id) })),
    decisions: document.getElementById('decisions').value,
  });
  document.getElementById('minutes').innerHTML = md.render(markdown);
  return markdown;
}
document.getElementById('generate').onclick = generate;
document.getElementById('print').onclick = async () => {
  const markdown = generate();
  // Finalize: store the MoM on the meeting so teams can view it in History (admin-only via RLS).
  await supa.from('meetings').update({ minutes_final: markdown }).eq('id', meeting.id);
  window.print();
};
generate();
```

- [ ] **Step 2: Verify** — minutes show every team's notes, "No updates this week" for empty ones, and the Decisions section; Print produces a clean PDF (reuse the local print CSS hiding everything but `#minutes`) **and** `meetings.minutes_final` is now populated in Supabase. Commit.

### Task 8b: Team history page

**Files:** Create `web/history.html` (from the design) + `web/history.js`.

**Interfaces:** Consumes `supa`, `currentProfile`, `md`. Reads only this team's own
`notes`/`submissions` (RLS-allowed) and each past meeting's `minutes_final`
(readable because `meetings` is world-readable to authenticated users).

- [ ] **Step 1: List past meetings + render a selected one**

```js
await requireAuth();
const me = await currentProfile();
const md = window.markdownit({ html: false, linkify: true, breaks: true });
document.getElementById('team-name').textContent = me.teams.name;

// past = every meeting except the active one, newest first
const { data: meetings } = await supa.from('meetings').select('*')
  .eq('is_active', false).order('created_at', { ascending: false });
const list = document.getElementById('history-list');
for (const m of meetings) {
  const li = document.createElement('li');
  li.innerHTML = `<button data-id="${m.id}">${m.title} — ${m.meeting_date || ''}</button>`;
  list.appendChild(li);
}

async function signed(path) {
  const { data } = await supa.storage.from('submissions').createSignedUrl(path, 3600);
  return data.signedUrl;
}
list.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-id]'); if (!btn) return;
  const m = meetings.find((x) => x.id === btn.dataset.id);
  const [{ data: note }, { data: subs }] = await Promise.all([
    supa.from('notes').select('*').eq('meeting_id', m.id).eq('team_id', me.team_id).maybeSingle(),
    supa.from('submissions').select('*').eq('meeting_id', m.id).eq('team_id', me.team_id),
  ]);
  document.getElementById('history-notes').innerHTML =
    '<h4>Meeting notes</h4>' + md.render((note && note.content) || '_none_') +
    '<h4>Pre-meeting note</h4>' + md.render((note && note.pre_note) || '_none_');
  const files = document.getElementById('history-files'); files.innerHTML = '';
  for (const f of (subs || [])) {
    const url = await signed(f.file_path);
    const li = document.createElement('li');
    li.innerHTML = `<a href="${url}" target="_blank" rel="noopener">${f.file_name}</a>`;
    files.appendChild(li);
  }
  document.getElementById('history-minutes').innerHTML =
    m.minutes_final ? md.render(m.minutes_final) : '<em>Minutes not finalized.</em>';
  document.getElementById('history-detail').hidden = false;
});
```

- [ ] **Step 2: Verify** — as a team member, past meetings list newest-first; selecting
  one shows this team's notes + files and the meeting's final minutes; confirm a team
  can NOT see another team's notes/files (RLS) — try a second account. Commit.

---

## Phase 7 — Deploy

### Task 9: Host on Netlify + configure Supabase

- [ ] **Step 1:** Push the repo; connect it to Netlify (or drag the `web/` folder to app.netlify.com/drop). No build command; publish directory = `web`.
- [ ] **Step 2:** In Supabase → Authentication → URL Configuration, add the Netlify URL to **Site URL** and **Redirect URLs** (so magic links return to your site).
- [ ] **Step 3: Verify end-to-end** — from the live URL: a team member logs in, uploads files + notes; the admin logs in, sees status, presents, and exports the MoM PDF. Commit a `README.md` with the setup steps.

---

## Self-Review

- Every spec screen has a task: Login (T3), Team dashboard — files (T4), minutes-note (T5), pre-note + submitted (T5b); Admin + drill-down (T6), Present incl. pre-notes (T7), Minutes + finalize (T8), Team history (T8b). ✓
- Security: RLS + Storage policies in T1; anon-key-only in frontend (Global Constraints). History reads other teams' data only via `meetings.minutes_final` (world-readable, admin-written); raw per-team notes/files stay behind team RLS. ✓
- Reuse: `isAccepted` (T4), `classifyFile` (T7), `buildMinutesMarkdown` (T8), deck/print CSS reused. ✓
- Two-note model: `notes.pre_note` (presentation, T5b/T7) vs `notes.content` (minutes, T5/T8); both in one row, upsert merges — verified in T5b Step 3. ✓
- Async model: no realtime; teams submit before, admin presents/exports. ✓
- Placeholder scan: config.js has `YOUR-PROJECT`/`YOUR-ANON-PUBLIC-KEY` — intentional user-supplied values (Task 2 Step 1), not plan gaps.
- Open risk: the claude.ai/design output must expose every id the `*.js` files target. Full list: `login-form`, `email`, `login-msg`, `team-name`, `meeting-title`, `file-input`, `file-list`, `notes`, `notes-preview`, `save-status`, `pre-note`, `pre-note-preview`, `submit-toggle`, `submit-status`, `history-link`, `meeting-form`/`m-title`/`m-date`/`m-org`, `team-rows` (+ row `data-team-id`), `present-btn`, `preview-slideshow-btn`, `minutes-btn`, `team-detail`, `detail-files`, `detail-notes`, `deck`/`slides`, `decisions`, `generate`, `print`, `minutes`, `history-list`, `history-detail`, `history-notes`, `history-files`, `history-minutes`. The v2 design prompt lists these so markup matches wiring.
