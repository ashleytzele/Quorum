// Login page: send a Supabase magic link. Keeps the design's validation + button UX.
(function () {
  const form = document.getElementById('login-form');
  const email = document.getElementById('email');
  const msg = document.getElementById('login-msg');
  const btn = form.querySelector('button[type=submit]');
  const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const val = (email.value || '').trim();
    msg.className = 'auth-msg';
    if (!EMAIL.test(val)) {
      msg.textContent = 'Please enter a valid work email address.';
      msg.classList.add('err');
      email.focus();
      return;
    }
    btn.disabled = true;
    btn.textContent = 'Sending…';
    const { error } = await supa.auth.signInWithOtp({
      email: val,
      options: { emailRedirectTo: location.origin + location.pathname.replace(/index\.html$/, '') + 'route.html' },
    });
    if (error) {
      msg.textContent = error.message;
      msg.classList.add('err');
      btn.disabled = false;
      btn.textContent = 'Send me a login link';
      return;
    }
    msg.textContent = 'Login link sent to ' + val + '. Check your email.';
    msg.classList.add('ok');
    btn.textContent = 'Link sent';
  });

  email.addEventListener('input', function () {
    if (msg.classList.contains('err')) {
      msg.className = 'auth-msg';
      msg.textContent = "We'll never share your email.";
    }
  });
})();
