// In-brand dialogs + toasts — replaces native prompt()/confirm()/alert().
// Uses <dialog> (native focus trap + Esc), styled via app tokens. Promise-based.
(function () {
  function el(tag, props, html) {
    var n = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) { n.setAttribute(k, props[k]); });
    if (html != null) n.innerHTML = html;
    return n;
  }

  // Toast: brief, non-blocking feedback. type: 'info' | 'ok' | 'error'
  window.toast = function (message, type) {
    var host = document.getElementById('toast-host');
    if (!host) { host = el('div', { id: 'toast-host' }); document.body.appendChild(host); }
    var t = el('div', { class: 'toast toast-' + (type || 'info'), role: (type === 'error' ? 'alert' : 'status') });
    t.textContent = message;
    host.appendChild(t);
    requestAnimationFrame(function () { t.classList.add('in'); });
    var kill = function () { t.classList.remove('in'); setTimeout(function () { t.remove(); }, 200); };
    setTimeout(kill, type === 'error' ? 5200 : 3200);
    t.addEventListener('click', kill);
  };

  function buildDialog(opts) {
    var d = el('dialog', { class: 'app-dialog' + (opts.danger ? ' danger' : ''), 'aria-labelledby': 'ad-title' });
    var form = el('form', { method: 'dialog' });
    var h = el('h2', { class: 'ad-title', id: 'ad-title' }); h.textContent = opts.title || ''; form.appendChild(h);
    if (opts.body) { var p = el('p', { class: 'ad-body', id: 'ad-body' }); p.textContent = opts.body; form.appendChild(p); d.setAttribute('aria-describedby', 'ad-body'); }
    var input = null, inputs = null;
    if (opts.fields) {
      // Multi-field prompt: resolves an object keyed by each field's `name`.
      inputs = {};
      opts.fields.forEach(function (f, i) {
        if (f.label) { var fl = el('label', { class: 'ad-label', for: 'ad-f-' + i }); fl.textContent = f.label; form.appendChild(fl); }
        var node = el('input', { class: 'input', id: 'ad-f-' + i, type: 'text' });
        if (f.placeholder) node.setAttribute('placeholder', f.placeholder);
        if (f.value) node.value = f.value;
        form.appendChild(node);
        inputs[f.name] = node;
      });
    } else if (opts.prompt) {
      if (opts.label) { var lb = el('label', { class: 'ad-label', for: 'ad-input' }); lb.textContent = opts.label; form.appendChild(lb); }
      input = el('input', { class: 'input', id: 'ad-input', type: 'text' });
      if (opts.placeholder) input.setAttribute('placeholder', opts.placeholder);
      if (opts.value) input.value = opts.value;
      form.appendChild(input);
    }
    var actions = el('div', { class: 'ad-actions' });
    var cancel = el('button', { type: 'button', class: 'btn btn-ghost', 'data-act': 'cancel' }); cancel.textContent = opts.cancelText || 'Cancel';
    var ok = el('button', { type: 'submit', class: 'btn ' + (opts.danger ? 'btn-danger' : 'btn-primary'), 'data-act': 'ok' }); ok.textContent = opts.confirmText || 'Confirm';
    actions.appendChild(cancel); actions.appendChild(ok);
    form.appendChild(actions);
    d.appendChild(form);
    document.body.appendChild(d);
    return { d: d, form: form, input: input, inputs: inputs, cancel: cancel };
  }

  function open(opts) {
    return new Promise(function (resolve) {
      var built = buildDialog(opts), d = built.d, done = false;
      function finish(val) { if (done) return; done = true; resolve(val); if (d.open) d.close(); setTimeout(function () { d.remove(); }, 0); }
      var emptyVal = opts.fields ? null : (opts.prompt ? null : false);
      built.cancel.addEventListener('click', function () { finish(emptyVal); });
      built.form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (opts.fields) {
          var out = {};
          Object.keys(built.inputs).forEach(function (k) { out[k] = built.inputs[k].value.trim(); });
          finish(out);
        } else {
          finish(opts.prompt ? built.input.value.trim() : true);
        }
      });
      d.addEventListener('cancel', function (e) { e.preventDefault(); finish(emptyVal); }); // Esc
      d.showModal();
      var focusEl = built.input || (built.inputs && built.inputs[Object.keys(built.inputs)[0]]);
      if (focusEl) { focusEl.focus(); if (focusEl.select) focusEl.select(); }
    });
  }

  // confirm({title, body, confirmText, danger}) -> Promise<boolean>
  window.confirmDialog = function (opts) { return open(Object.assign({ confirmText: 'Confirm' }, opts, { prompt: false })); };
  // prompt({title, label, value, placeholder, confirmText}) -> Promise<string|null>  ('' if cleared, null if cancelled)
  window.promptDialog = function (opts) { return open(Object.assign({ confirmText: 'Save' }, opts, { prompt: true })); };

  // Flash toast: survives one page reload — for actions that reload after a write.
  window.flashToast = function (message, type) {
    try { sessionStorage.setItem('mt.flash', JSON.stringify({ m: message, t: type || 'info' })); } catch (e) {}
  };
  try {
    var pending = sessionStorage.getItem('mt.flash');
    if (pending) { sessionStorage.removeItem('mt.flash'); var o = JSON.parse(pending); requestAnimationFrame(function () { window.toast(o.m, o.t); }); }
  } catch (e) {}
})();
