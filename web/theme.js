// No-flash light/dark theme. Loaded synchronously in <head> so data-theme is set
// before first paint. Injects a floating toggle (except in the embedded VIP workspace).
(function () {
  var KEY = 'meeteam.theme';
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  var theme = saved || (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', theme);

  window.toggleTheme = function () {
    var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem(KEY, next); } catch (e) {}
  };

  // Keep other same-origin documents in sync — embedded iframe (VIP workspace) and other tabs.
  window.addEventListener('storage', function (e) {
    if (e.key === KEY && e.newValue) document.documentElement.setAttribute('data-theme', e.newValue);
  });

  // Don't add a toggle inside the embedded workspace iframe (it inherits the parent's theme).
  var embedded = new URLSearchParams(location.search).get('embed') === '1';

  function injectToggle() {
    if (embedded || document.getElementById('theme-toggle')) return;
    var btn = document.createElement('button');
    btn.id = 'theme-toggle'; btn.type = 'button'; btn.className = 'theme-toggle';
    btn.title = 'Toggle light / dark'; btn.setAttribute('aria-label', 'Toggle light or dark theme');
    btn.innerHTML =
      '<svg class="ic-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>' +
      '<svg class="ic-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
    btn.addEventListener('click', window.toggleTheme);
    document.body.appendChild(btn);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', injectToggle);
  else injectToggle();
})();
