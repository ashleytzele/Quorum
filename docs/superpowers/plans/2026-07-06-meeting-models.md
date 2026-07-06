# Meeting Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each meeting run under one of three operating models — Team self-serve, Admin-run (VIP, hidden from members), or Hybrid — by giving the admin the ability to author any team's content and hiding VIP meetings from members.

**Architecture:** Add a `model` column to `meetings`. Add admin-write RLS on `notes`/`submissions` so the admin can author on any team's behalf, and change the `read meetings` policy so members can't see `admin`-model meetings. Reuse the existing member workspace (`team.html`) as the admin's editor via `?meeting=&team=` params. No new editor UI.

**Tech Stack:** Static HTML/JS served over `python -m http.server`, Supabase (Postgres + RLS + Storage), supabase-js v2 via CDN. Verification via headless Chrome over the DevTools Protocol (Node 25 global `WebSocket`/`fetch`) + `node --check` + Supabase SQL.

## Global Constraints

- Frontend is plain browser JS — no build step, no bundler, no TypeScript, no new npm deps.
- Supabase public values live in `web/config.js`; RLS protects data. Project ref: `pxtahxgqgkybbevbybul`.
- Admin identity is `is_admin()` (existing SQL function); team scoping is `my_team()`.
- Local JS/CSS includes are cache-busted with `?v=N`; the dev server (`run.command`) sends `Cache-Control: no-store`.
- DB migrations may be blocked by the host safety classifier; if `apply_migration` is denied, output the exact SQL for the user to run in the Supabase SQL editor and continue once confirmed.
- Verification pattern: sign in as admin via `dev-login.html` (`<dev-email>` / `<dev-password>`), drive pages over CDP, assert DOM/DB state, then delete any test rows. Test rows are prefixed `__CDP`.
- Every DB write test must clean up after itself; leave the DB at its pre-test row counts.

---

### Task 1: DB — `model` column, admin-write RLS, hide VIP from members

**Files:**
- Migration (via `apply_migration` or Supabase SQL editor) — no repo file.

**Interfaces:**
- Produces: `meetings.model text not null default 'team'` in `('team','admin','hybrid')`; RLS policies `admin writes notes`, `admin writes submissions`; updated `read meetings` policy hiding `model='admin'` from non-admins.

- [ ] **Step 1: Inspect current state** (so the recreate of `read meetings` is exact)

Run this SQL and note the current `read meetings` definition:
```sql
select policyname, cmd, qual, with_check from pg_policies
where schemaname='public' and tablename='meetings';
select column_name from information_schema.columns
where table_schema='public' and table_name='meetings' and column_name='model';
```
Expected: `read meetings` SELECT with `qual = true`; no `model` column yet.

- [ ] **Step 2: Apply the migration**

Name: `meeting_models`. SQL:
```sql
-- 1. model column (existing rows backfill to 'team')
alter table public.meetings add column if not exists model text not null default 'team';
alter table public.meetings add constraint meetings_model_check check (model in ('team','admin','hybrid'));

-- 2. admin may author any team's notes + submissions (mirrors "admin writes teams")
create policy "admin writes notes" on public.notes
  for all to authenticated using (is_admin()) with check (is_admin());
create policy "admin writes submissions" on public.submissions
  for all to authenticated using (is_admin()) with check (is_admin());

-- 3. hide admin-model (VIP) meetings from members
drop policy "read meetings" on public.meetings;
create policy "read meetings" on public.meetings
  for select to authenticated using (model <> 'admin' or is_admin());
```
If `apply_migration` is denied by the classifier, print this SQL and ask the user to run it in Supabase → SQL editor, then continue.

- [ ] **Step 3: Verify schema + policies**

```sql
select column_name, column_default from information_schema.columns
where table_schema='public' and table_name='meetings' and column_name='model';
select tablename, policyname, cmd, qual from pg_policies
where schemaname='public' and tablename in ('meetings','notes','submissions')
  and policyname in ('read meetings','admin writes notes','admin writes submissions')
order by tablename, policyname;
select model, count(*) from public.meetings group by model;
```
Expected: `model` default `'team'`; three policies present; every existing meeting has `model='team'`.

- [ ] **Step 4: Verify behavior over CDP** (admin write-on-behalf works; member can't see VIP)

Launch headless Chrome (`--remote-debugging-port`, temp `--user-data-dir`), sign in as admin, then evaluate in the page:
```js
// admin can author for a team that is NOT necessarily their own
const { data: teams } = await supa.from('teams').select('id').order('name');
const other = teams[0].id;
const { data: m } = await supa.from('meetings').insert({title:'__CDP_M1__',is_active:true,model:'admin'}).select().single();
const note = await supa.from('notes').upsert({meeting_id:m.id,team_id:other,pre_note:'__cdp'},{onConflict:'meeting_id,team_id'});
const sub  = await supa.from('submissions').insert({meeting_id:m.id,team_id:other,url:'https://x.test',file_name:'__cdp',mime:'link'}).select().single();
// VIP visible to admin via openMeetings
const openIds = (await openMeetings()).map(x=>x.id);
return JSON.stringify({ noteOk: !note.error, subOk: !sub.error, adminSeesVip: openIds.includes(m.id) });
```
Expected: `{"noteOk":true,"subOk":true,"adminSeesVip":true}`.

- [ ] **Step 5: Cleanup test rows**
```sql
delete from public.submissions where file_name='__cdp';
delete from public.notes where pre_note='__cdp';
delete from public.meetings where title='__CDP_M1__';
select (select count(*) from meetings where title like '\_\_CDP%' escape '\') as leftovers;
```
Expected: `leftovers = 0`.

- [ ] **Step 6: Commit** (if the user has opted into commits; otherwise skip)
```bash
git add docs/superpowers/plans/2026-07-06-meeting-models.md
git commit -m "chore: meeting-models migration applied (model column + admin-write RLS + hide VIP)"
```

---

### Task 2: Storage — allow admin uploads into any team's folder

**Files:**
- Migration/policy on `storage.objects` (via `apply_migration` or SQL editor) — no repo file.

**Interfaces:**
- Produces: admin can `upload`/`remove` objects in the `submissions` bucket regardless of the team path, so Model 2/3 file uploads work when the admin acts on behalf of a team.

- [ ] **Step 1: Inspect existing storage policies**
```sql
select policyname, cmd, qual, with_check from pg_policies
where schemaname='storage' and tablename='objects';
```
Expected: policies scoped to the `submissions` bucket, likely team-scoped for insert/delete (path or `my_team()` based).

- [ ] **Step 2: Decide + apply**

If an admin-covering policy already exists (e.g. `bucket_id='submissions' and is_admin()`), skip. Otherwise add, name `admin_writes_submission_objects`:
```sql
create policy "admin writes submission objects" on storage.objects
  for all to authenticated
  using (bucket_id = 'submissions' and is_admin())
  with check (bucket_id = 'submissions' and is_admin());
```
If denied by the classifier, print SQL for the user to run.

- [ ] **Step 3: Verify over CDP** (admin uploads a file into a team folder)
```js
const { data: teams } = await supa.from('teams').select('id').order('name');
const other = teams[0].id;
const { data: m } = await supa.from('meetings').insert({title:'__CDP_M2__',is_active:true,model:'admin'}).select().single();
const path = m.id + '/' + other + '/' + 'x-__cdp.txt';
const up = await supa.storage.from('submissions').upload(path, new File(['hi'],'__cdp.txt',{type:'text/plain'}));
const res = up.error ? ('ERR:'+up.error.message) : 'OK';
// cleanup
if(!up.error){ await supa.storage.from('submissions').remove([path]); }
await supa.from('meetings').delete().eq('id', m.id);
return res;
```
Expected: `OK`. (If `ERR:`, the storage policy from Step 2 is required/incorrect — fix and re-run.)

- [ ] **Step 4: Commit** (optional, per user's commit preference)
```bash
git commit -am "chore: storage policy allows admin uploads on behalf of any team" --allow-empty
```

---

### Task 3: `admin.html` — Model dropdown + persist + tab badges

**Files:**
- Modify: `web/admin.html` (meeting details card HTML; `persistMeeting`; meeting-tab rendering)

**Interfaces:**
- Consumes: `meetings.model` (Task 1).
- Produces: admin selects/saves a meeting's model; non-`team` meetings show a badge on their tab. `meeting.model` is read by Task 4.

- [ ] **Step 1: Add the Model field to the meeting form**

In the meeting details card body, add after the Organization field inside `<form id="meeting-form" class="form-row">`:
```html
            <div class="field">
              <label class="label" for="m-model">Model</label>
              <select class="input" id="m-model">
                <option value="team">Team self-serve</option>
                <option value="admin">Admin-run · VIP</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </div>
```

- [ ] **Step 2: Wire the field into load + save**

Find `const fOrg = document.getElementById('m-org');` and add after it:
```js
  const fModel = document.getElementById('m-model');
```
Find where the meeting values are loaded (`if (meeting){ fTitle.value = ... }`) and add inside that block:
```js
    fModel.value = meeting.model || 'team';
```
In `persistMeeting`, change the payload line to include the model:
```js
    const payload = { title: fTitle.value || 'Untitled', meeting_date: fDate.value || null, org: fOrg.value, model: fModel.value };
```
Add `fModel` to the autosave listener array (the `[fTitle, fDate, fOrg].forEach(...)` line):
```js
  [fTitle, fDate, fOrg, fModel].forEach(function(f){ f.addEventListener('input', function(){ flashSaving(); clearTimeout(mtimer); mtimer = setTimeout(persistMeeting, 600); }); });
```
(Note: `<select>` fires `input` on change in modern browsers — verified in Step 6.)

- [ ] **Step 3: Add a model badge to each meeting tab**

In the admin meeting-tab rendering (`tabsEl.innerHTML = meetings.map(function(m){ ... })`), compute a badge and append it to the `mt-sub` line. Replace the `label` construction and the returned `mt-sub` span:
```js
      const modelBadge = m.model === 'admin' ? ' <span class="mt-flag">VIP</span>'
                       : m.model === 'hybrid' ? ' <span class="mt-flag">Hybrid</span>' : '';
      const label = (m.title ? esc(m.title) + ' · ' : '') + subCount(m.id) + '/' + totalTeams + ' in';
```
and in the returned HTML change the `mt-sub` span to:
```js
        '<span class="mt-sub">' + label + modelBadge + '</span></span></button>';
```

- [ ] **Step 4: Add the badge style**

In `web/styles.css`, after the `.mt-dot.submitted` rule, add:
```css
.mt-flag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.03em;padding:1px 6px;border-radius:6px;background:var(--accent-100);color:var(--accent-700);vertical-align:middle;}
```

- [ ] **Step 5: Cache-bust styles + syntax check**

Since `styles.css` changed, bump its version across pages (it is currently `styles.css?v=2`):
```bash
cd web && sed -i '' 's#styles.css?v=2#styles.css?v=3#' *.html
node --check <(python3 -c "import re;print('\n'.join(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',open('admin.html').read(),re.S)))") && echo OK
```
Expected: `OK`.

- [ ] **Step 6: Verify over CDP** (select model, reload, persisted; badge shows)
Sign in as admin, then:
```js
// pick the first open meeting, set model=hybrid via the select, wait for autosave
const sel = document.getElementById('m-model'); sel.value='hybrid';
sel.dispatchEvent(new Event('input',{bubbles:true}));
await new Promise(r=>setTimeout(r,900));
const mId = document.querySelector('.meeting-tab.active').dataset.id;
const { data } = await supa.from('meetings').select('model').eq('id',mId).single();
return data.model; // expect 'hybrid'
```
Expected: `hybrid`. Then reload and confirm a `Hybrid` badge appears: `!!document.querySelector('.meeting-tab.active .mt-flag')` → `true`. Reset the meeting back to `team` afterward.

- [ ] **Step 7: Commit** (optional)
```bash
git add web/admin.html web/styles.css web/*.html
git commit -m "feat: admin can set a meeting's model; VIP/Hybrid badge on meeting tabs"
```

---

### Task 4: `admin.html` — "Edit as team" action for admin/hybrid meetings

**Files:**
- Modify: `web/admin.html` (team drawer body; drawer open handler)

**Interfaces:**
- Consumes: `meeting.model` (Task 3), `currentTeam` (existing drawer state), `mId` (selected meeting id).
- Produces: navigation to `team.html?meeting=<mId>&team=<teamId>` (consumed by Task 5).

- [ ] **Step 1: Add an Edit button to the drawer**

In the drawer body actions row (where `rename-team` / `delete-team` live), add:
```html
      <button class="btn btn-primary" id="edit-as-team" type="button" style="display:none;">Edit this team's content</button>
```

- [ ] **Step 2: Show it only for admin/hybrid meetings, and wire navigation**

In `openTeam(t, color)`, after `currentTeam = t;`, add:
```js
    var editBtn = document.getElementById('edit-as-team');
    editBtn.style.display = (meeting && (meeting.model === 'admin' || meeting.model === 'hybrid')) ? '' : 'none';
```
Near the other drawer handlers (e.g. after the `delete-team` handler), add:
```js
  document.getElementById('edit-as-team').addEventListener('click', function(){
    if (!currentTeam || !mId) return;
    location.href = 'team.html?meeting=' + mId + '&team=' + currentTeam.id;
  });
```

- [ ] **Step 3: Syntax check**
```bash
cd web && node --check <(python3 -c "import re;print('\n'.join(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',open('admin.html').read(),re.S)))") && echo OK
```
Expected: `OK`.

- [ ] **Step 4: Verify over CDP** (button hidden for team model, shown + links correctly for hybrid)
Set a meeting's model to `hybrid` (via SQL or Task 3 UI), open a team drawer, and check:
```js
// after opening admin.html and clicking a team row
document.querySelector('#team-rows tr').click();
await new Promise(r=>setTimeout(r,300));
const btn = document.getElementById('edit-as-team');
return getComputedStyle(btn).display; // '' -> shown (not 'none') for hybrid
```
Expected: not `none` for a hybrid meeting; `none` for a `team` meeting. Reset model to `team` after.

- [ ] **Step 5: Commit** (optional)
```bash
git add web/admin.html
git commit -m "feat: admin drawer offers 'Edit this team's content' for admin/hybrid meetings"
```

---

### Task 5: `team.html` — edit on behalf of a team (params + banner)

**Files:**
- Modify: `web/team.html` (top of IIFE: profile/meeting/team resolution; banner; meeting-tabs suppression; all `me.team_id` usages)

**Interfaces:**
- Consumes: `?meeting=<id>&team=<teamId>` (Task 4); admin-write RLS (Task 1); storage policy (Task 2).
- Produces: a working editor bound to `effectiveTeamId` for the target meeting when an admin acts on behalf.

- [ ] **Step 1: Resolve effective team + meeting from params**

Replace the top of the IIFE:
```js
  const me = await currentProfile();
  const meetings = await openMeetings();
  const meeting = await selectedMeeting(meetings);
```
with:
```js
  const me = await currentProfile();
  const params = new URLSearchParams(location.search);
  const teamParam = params.get('team');
  const meetingParam = params.get('meeting');
  const onBehalf = !!(teamParam && me && me.role === 'admin');
  const effectiveTeamId = onBehalf ? teamParam : (me ? me.team_id : null);
  const meetings = await openMeetings();
  const meeting = meetingParam
    ? ((await supa.from('meetings').select('*').eq('id', meetingParam).maybeSingle()).data || await selectedMeeting(meetings))
    : await selectedMeeting(meetings);
```

- [ ] **Step 2: Replace every `me.team_id` with `effectiveTeamId`**

There are four usages in the file — the note load, `saveNote`, the submissions load, and `uploadFiles`' storage path. Change each:
```js
// note load
    .eq('meeting_id', meeting.id).eq('team_id', effectiveTeamId).maybeSingle();
// saveNote upsert object
      Object.assign({ meeting_id: meeting.id, team_id: effectiveTeamId, updated_at: new Date().toISOString() }, fields),
// submissions load
    .eq('meeting_id', meeting.id).eq('team_id', effectiveTeamId).order('created_at');
// uploadFiles path + insert
      var path = meeting.id + '/' + effectiveTeamId + '/' + Date.now() + '-' + file.name;
      ...
        meeting_id: meeting.id, team_id: effectiveTeamId, file_path: path, file_name: file.name, mime: file.type
// addLink insert
      meeting_id: meeting.id, team_id: effectiveTeamId, url: url, file_name: linkLabel.value.trim() || url, mime: 'link'
// the tab-status query in Step 4 of the original file
    .eq('team_id', effectiveTeamId).in('meeting_id', meetings.map(m => m.id));
```
Verify none remain: `grep -n "me\.team_id" web/team.html` should return nothing after this step.

- [ ] **Step 3: Banner + suppress meeting tabs when on behalf**

Replace the tabs block guard. After computing `meeting`, when `onBehalf`, show the team name in the header and skip the switchable tabs (admin is pinned to one meeting+team). Add near the top of the tab-rendering section:
```js
  const tabsEl = document.getElementById('meeting-tabs');
  if (onBehalf) {
    const { data: trow } = await supa.from('teams').select('name').eq('id', effectiveTeamId).maybeSingle();
    const tname = trow ? trow.name : 'team';
    if (me && me.teams) document.getElementById('team-name').textContent = tname;
    document.getElementById('meeting-title').textContent =
      (meeting ? meeting.title : 'No meeting') + ' · editing as admin';
    tabsEl.innerHTML = '<div class="pf-banner">Editing as <b>' + esc(tname) +
      '</b> · admin — changes save to this team. <a href="admin.html">Back to admin</a></div>';
  } else {
    // ... existing tab-rendering code (unchanged) ...
  }
```
Wrap the existing member tab-rendering code (from `if (!meetings.length)` through the `titleEl.textContent = ...` line) inside that `else` branch. `esc` is the file's existing hoisted helper.

- [ ] **Step 4: Banner style**

In `web/styles.css`, after the `.mt-flag` rule, add:
```css
.pf-banner{background:var(--accent-50);color:var(--accent-700);border:1px solid var(--accent-100);border-radius:var(--radius-sm);padding:10px 14px;font-size:13.5px;margin-bottom:22px;}
.pf-banner a{margin-left:8px;font-weight:600;}
```

- [ ] **Step 5: Cache-bust + syntax check**
```bash
cd web && sed -i '' 's#styles.css?v=3#styles.css?v=4#' *.html
node --check <(python3 -c "import re;print('\n'.join(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',open('team.html').read(),re.S)))") && echo OK
grep -n "me\.team_id" team.html || echo "no me.team_id left"
```
Expected: `OK` and `no me.team_id left`.

- [ ] **Step 6: Verify over CDP** (admin edits a team's note via params; saved to that team)
Sign in as admin. Create a temp `hybrid` meeting, pick a team, then:
```js
const { data: teams } = await supa.from('teams').select('id,name').order('name');
const t = teams[0];
const { data: m } = await supa.from('meetings').insert({title:'__CDP_M5__',is_active:true,model:'hybrid'}).select().single();
location.href = 'team.html?meeting=' + m.id + '&team=' + t.id;
```
After navigation settles, assert the banner and drive an edit:
```js
const banner = document.querySelector('.pf-banner');
document.getElementById('pre-note').value = '__cdp onbehalf';
document.getElementById('pre-note').dispatchEvent(new Event('input',{bubbles:true}));
await new Promise(r=>setTimeout(r,1000));
const url = new URL(location.href);
const { data } = await supa.from('notes')
  .select('pre_note').eq('meeting_id', url.searchParams.get('meeting'))
  .eq('team_id', url.searchParams.get('team')).maybeSingle();
return JSON.stringify({ hasBanner: !!banner, saved: data && data.pre_note });
```
Expected: `{"hasBanner":true,"saved":"__cdp onbehalf"}`.

- [ ] **Step 7: Cleanup**
```js
const url = new URL(location.href);
await supa.from('notes').delete().eq('meeting_id', url.searchParams.get('meeting'));
await supa.from('meetings').delete().eq('id', url.searchParams.get('meeting'));
return 'clean';
```
Then confirm no `__CDP` meetings remain via SQL.

- [ ] **Step 8: Commit** (optional)
```bash
git add web/team.html web/styles.css web/*.html
git commit -m "feat: admin edits any team's content via team.html?meeting=&team= (Models 2 & 3)"
```

---

### Task 6: Regression + member-visibility verification

**Files:**
- No code changes (RLS from Task 1 enforces visibility). Verification only.

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: VIP hidden from members**

This project currently has a single account that is `admin`. To verify the member path without creating a permanent member, assert at the policy level with SQL (runs as the table owner, so simulate via a temp member is out of scope) — instead verify the policy qual and that admin sees VIP while the `read meetings` qual excludes it for non-admins:
```sql
select qual from pg_policies where schemaname='public' and tablename='meetings' and policyname='read meetings';
```
Expected: `(model <> 'admin'::text OR is_admin())`. Document that a real member session (role <> admin) therefore cannot select `model='admin'` rows, so VIP meetings never enter `openMeetings()` or history for members.

- [ ] **Step 2: Team-model regression over CDP**

Confirm a `team`-model meeting still behaves as before: as admin viewing the member workspace with no params, the meeting tabs render and a note still saves to the admin's own team.
```js
location.href = 'team.html';
// after load:
return JSON.stringify({
  tabs: document.querySelectorAll('.meeting-tab').length >= 1,
  noBanner: !document.querySelector('.pf-banner')
});
```
Expected: `{"tabs":true,"noBanner":true}`.

- [ ] **Step 3: Full DB cleanliness check**
```sql
select (select count(*) from meetings where title like '\_\_CDP%' escape '\') as m,
       (select count(*) from notes where pre_note like '\_\_cdp%' escape '\') as n,
       (select count(*) from submissions where file_name like '\_\_cdp%' escape '\') as s;
```
Expected: `0, 0, 0`.

- [ ] **Step 4: Final commit** (optional)
```bash
git commit -am "test: verify meeting-models (VIP hidden, admin-on-behalf, team regression)" --allow-empty
```

---

## Notes for the implementer

- **Cache versions**: this plan bumps `styles.css` to `?v=4`. If you add further CSS/JS edits, bump again and keep all pages in sync (`sed` across `web/*.html`).
- **Migrations may be denied** by the host classifier; if so, hand the exact SQL to the user and wait for "done" before the verification steps.
- **Single-account caveat**: only an admin account exists, and it also has a `team_id` (Tech). The admin-on-behalf tests therefore exercise the admin-write RLS even when the target team equals the admin's own team; still assert with an explicitly different `team_id` where possible.
- **Do not** change Present (pre-flight checklist), Export→archive, or History — they are out of scope and must keep working.
