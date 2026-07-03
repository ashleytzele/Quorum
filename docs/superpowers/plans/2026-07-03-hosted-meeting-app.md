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
  created_at timestamptz not null default now()
);

create table notes (
  id uuid primary key default gen_random_uuid(),
  meeting_id uuid not null references meetings on delete cascade,
  team_id uuid not null references teams,
  content text not null default '',
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

-- helper: is the caller an admin?
create or replace function is_admin() returns boolean language sql stable as $$
  select exists (select 1 from profiles where id = auth.uid() and role = 'admin');
$$;
-- helper: caller's team
create or replace function my_team() returns uuid language sql stable as $$
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
create or replace function handle_new_user() returns trigger language plpgsql security definer as $$
begin insert into profiles (id) values (new.id); return new; end; $$;
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

### Task 5: Notes editor with autosave + live preview

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

const [{ data: teams }, { data: subs }, { data: notes }] = await Promise.all([
  supa.from('teams').select('*').order('name'),
  supa.from('submissions').select('team_id').eq('meeting_id', meeting.id),
  supa.from('notes').select('team_id, content').eq('meeting_id', meeting.id),
]);
const fileCount = (id) => subs.filter((s) => s.team_id === id).length;
const hasNotes = (id) => notes.some((n) => n.team_id === id && n.content.trim());
const tbody = document.getElementById('team-rows');
for (const t of teams) {
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${t.name}</td><td>${fileCount(t.id)} files</td>
    <td>${hasNotes(t.id) ? '✓ notes' : '— no notes'}</td>`;
  tbody.appendChild(tr);
}
document.getElementById('present-btn').onclick = () => location.href = 'present.html';
document.getElementById('minutes-btn').onclick = () => location.href = 'minutes.html';
```

- [ ] **Step 2: Create/activate a meeting**

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

- [ ] **Step 3: Verify** — as admin, see all teams with file counts + note status; create a new meeting and confirm it becomes active. Commit.

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
  if (!mine.length) continue;
  parts.push(`<section class="team-title"><h1>${esc(t.name)}</h1></section>`);
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
}
document.getElementById('generate').onclick = generate;
document.getElementById('print').onclick = () => { generate(); window.print(); };
generate();
```

- [ ] **Step 2: Verify** — minutes show every team's notes, "No updates this week" for empty ones, and the Decisions section; Print produces a clean PDF (reuse the local print CSS hiding everything but `#minutes`). Commit.

---

## Phase 7 — Deploy

### Task 9: Host on Netlify + configure Supabase

- [ ] **Step 1:** Push the repo; connect it to Netlify (or drag the `web/` folder to app.netlify.com/drop). No build command; publish directory = `web`.
- [ ] **Step 2:** In Supabase → Authentication → URL Configuration, add the Netlify URL to **Site URL** and **Redirect URLs** (so magic links return to your site).
- [ ] **Step 3: Verify end-to-end** — from the live URL: a team member logs in, uploads files + notes; the admin logs in, sees status, presents, and exports the MoM PDF. Commit a `README.md` with the setup steps.

---

## Self-Review

- Every spec screen has a task: Login (T3), Team dashboard (T4+T5), Admin (T6), Present (T7), Minutes (T8). ✓
- Security: RLS + Storage policies in T1; anon-key-only in frontend (Global Constraints). ✓
- Reuse: `isAccepted` (T4), `classifyFile` (T7), `buildMinutesMarkdown` (T8), deck/print CSS reused. ✓
- Async model: no realtime; teams submit before, admin presents/exports. ✓
- Placeholder scan: config.js has `YOUR-PROJECT`/`YOUR-ANON-PUBLIC-KEY` — these are intentional user-supplied values, filled in Task 2 Step 1, not plan gaps.
- Open risk: the claude.ai/design output must expose the element ids the `*.js` files reference (`login-form`, `email`, `file-input`, `file-list`, `notes`, `notes-preview`, `team-rows`, `slides`, `deck`, `minutes`, `decisions`, `generate`, `print`, etc.). The design prompt lists these required ids so the markup matches the wiring.
