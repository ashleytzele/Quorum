// Login page: email + password. Signs in, or creates the account on the fly if it
// doesn't exist yet (prototype — no email step). Invited emails auto-join their team
// via currentProfile(). Route admins to the console, everyone else to their team.
(function () {
  const form = document.getElementById('login-form');
  const email = document.getElementById('email');
  const password = document.getElementById('password');
  const msg = document.getElementById('login-msg');
  const btn = form.querySelector('button[type=submit]');
  const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  function fail(m) {
    msg.textContent = m; msg.className = 'auth-msg err';
    btn.disabled = false; btn.textContent = 'Sign in / Create account';
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const val = (email.value || '').trim();
    const pw = password.value || '';
    msg.className = 'auth-msg';
    if (!EMAIL.test(val)) { email.setAttribute('aria-invalid', 'true'); return fail('Please enter a valid email address.'); }
    if (pw.length < 6) { password.setAttribute('aria-invalid', 'true'); return fail('Password must be at least 6 characters.'); }
    btn.disabled = true; btn.textContent = 'Signing in…';

    try {
      let { error } = await supa.auth.signInWithPassword({ email: val, password: pw });
      if (error) {
        // No account yet → create one (prototype: expects email confirmation to be off).
        const up = await supa.auth.signUp({ email: val, password: pw });
        if (up.error) {
          if (/already registered/i.test(up.error.message || '')) return fail('Wrong password for this account.');
          console.error(up.error);
          return fail(up.error.message || 'Sign-in failed');
        }
        if (!up.data.session) {
          return fail('Account created, but email confirmation is on. Turn off "Confirm email" in Supabase → Auth for the demo.');
        }
      }
      const p = await currentProfile();
      location.href = (p && p.role === 'admin') ? 'admin.html' : 'team.html';
    } catch (e) {
      console.error(e);
      return fail('Network error — check your connection and try again.');
    }
  });

  // Forgot password: send a recovery/sign-in link (accounts are otherwise created silently on first sign-in).
  const forgot = document.getElementById('forgot-link');
  if (forgot) forgot.addEventListener('click', async function (e) {
    e.preventDefault();
    const val = (email.value || '').trim();
    if (!EMAIL.test(val)) { msg.textContent = 'Enter your email above first, then click “Forgot password”.'; msg.className = 'auth-msg err'; return; }
    try {
      const { error } = await supa.auth.resetPasswordForEmail(val, { redirectTo: location.origin + '/route.html' });
      if (error) throw error;
      msg.textContent = 'Check your email for a sign-in link.'; msg.className = 'auth-msg';
    } catch (err) { console.error(err); msg.textContent = 'Couldn’t send the reset email — please try again.'; msg.className = 'auth-msg err'; }
  });

  [email, password].forEach(function (el) {
    el.addEventListener('input', function () {
      el.removeAttribute('aria-invalid');
      if (msg.classList.contains('err')) { msg.className = 'auth-msg'; msg.textContent = "We'll never share your email."; }
    });
  });
})();
