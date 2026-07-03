// Shared Supabase client + helpers. Loaded after config.js and the supabase-js CDN.
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

async function signOut() {
  await supa.auth.signOut();
  location.href = 'index.html';
}

async function signedUrl(path, secs = 3600) {
  const { data } = await supa.storage.from('submissions').createSignedUrl(path, secs);
  return data ? data.signedUrl : '#';
}
