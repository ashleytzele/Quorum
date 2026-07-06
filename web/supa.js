// Shared Supabase client + helpers. Loaded after config.js and the supabase-js CDN.
const supa = window.supabase.createClient(window.SUPA_URL, window.SUPA_ANON);

async function currentProfile() {
  const { data: { user } } = await supa.auth.getUser();
  if (!user) return null;
  let { data } = await supa.from('profiles').select('*, teams(name)').eq('id', user.id).maybeSingle();
  if (!data) {
    // First login for this user — create their profile row (no server-side trigger).
    await supa.from('profiles').insert({ id: user.id });
    ({ data } = await supa.from('profiles').select('*, teams(name)').eq('id', user.id).maybeSingle());
  }
  // Auto-join: if this user has no team yet and their email was invited to one, claim it.
  if (data && !data.team_id && user.email) {
    const email = user.email.toLowerCase();
    const { data: inv } = await supa.from('team_invites').select('team_id').eq('email', email).maybeSingle();
    if (inv && inv.team_id) {
      await supa.from('profiles').update({ team_id: inv.team_id }).eq('id', user.id);
      await supa.from('team_invites').update({ joined_at: new Date().toISOString() }).eq('email', email);
      ({ data } = await supa.from('profiles').select('*, teams(name)').eq('id', user.id).maybeSingle());
    }
  }
  return data; // { id, team_id, role, teams: { name } }
}

// Every non-archived meeting. Multiple can be open at once (e.g. Friday's and
// Wednesday's), so teams can keep contributing to each until it's archived.
async function openMeetings() {
  const { data } = await supa.from('meetings').select('*').eq('is_active', true)
    .order('meeting_date', { ascending: true, nullsFirst: false })
    .order('created_at', { ascending: false });
  return data || [];
}

const MEETING_KEY = 'meeteam.meeting';
// The meeting the user is currently working on. Remembered per-browser so it
// survives page navigation; falls back to the soonest open meeting.
async function selectedMeeting(list) {
  const meetings = list || await openMeetings();
  if (!meetings.length) return null;
  const saved = localStorage.getItem(MEETING_KEY);
  return meetings.find(m => m.id === saved) || meetings[0];
}
function setSelectedMeeting(id) { localStorage.setItem(MEETING_KEY, id); }
function clearSelectedMeeting() { localStorage.removeItem(MEETING_KEY); }

async function requireAuth(redirect = 'index.html') {
  const { data: { session } } = await supa.auth.getSession();
  if (!session) location.href = redirect;
}

async function signOut() {
  await supa.auth.signOut();
  location.href = 'index.html';
}

async function signedUrl(path, secs = 3600) {
  const { data } = await supa.storage.from('submissions').createSignedUrl(path, secs);
  return data ? data.signedUrl : '#';
}
