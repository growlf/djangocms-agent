/* Light/dark theme for Bootstrap 5.3 (data-bs-theme on <html>). Loaded synchronously in <head>, so the
 * right theme is set before first paint (no flash).
 *   1. A choice stored by the header toggle (localStorage key "theme": "light" | "dark") wins.
 *   2. Otherwise the OS preference (prefers-color-scheme), including live OS changes.
 * Without JavaScript the media query in site.css still follows the OS and the toggle stays hidden.
 * localStorage may throw (private mode, blocked site data): every access is guarded, and the toggle then
 * works for the current page only. */
(function () {
  var KEY = 'theme';
  var root = document.documentElement;
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function stored() {
    try {
      var v = window.localStorage.getItem(KEY);
      return v === 'light' || v === 'dark' ? v : null;
    } catch (e) { return null; }
  }
  function save(v) {
    try { window.localStorage.setItem(KEY, v); } catch (e) { /* storage unavailable: choice lasts for this page */ }
  }
  function current() { return root.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light'; }

  function sync() {
    var dark = current() === 'dark';
    var buttons = document.querySelectorAll ? document.querySelectorAll('[data-theme-toggle]') : [];
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].hidden = false;
      buttons[i].setAttribute('aria-pressed', dark ? 'true' : 'false');
      buttons[i].setAttribute('title', dark ? 'Switch to light theme' : 'Switch to dark theme');
    }
  }
  function apply() {
    root.setAttribute('data-bs-theme', stored() || (mq && mq.matches ? 'dark' : 'light'));
    sync();
  }

  apply();
  if (mq) {
    if (mq.addEventListener) { mq.addEventListener('change', function () { if (!stored()) { apply(); } }); }
    else if (mq.addListener) { mq.addListener(function () { if (!stored()) { apply(); } }); }
  }
  window.addEventListener('storage', function (e) { if (e.key === KEY || e.key === null) { apply(); } });
  document.addEventListener('DOMContentLoaded', sync);
  document.addEventListener('click', function (e) {
    var t = e.target;
    while (t && t.nodeType === 1 && !(t.hasAttribute && t.hasAttribute('data-theme-toggle'))) { t = t.parentNode; }
    if (!t || t.nodeType !== 1) { return; }
    var next = current() === 'dark' ? 'light' : 'dark';
    save(next);
    root.setAttribute('data-bs-theme', next);
    sync();
  });
})();
