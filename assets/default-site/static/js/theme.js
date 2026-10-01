/* Follow the OS colour scheme: set data-bs-theme (Bootstrap 5.3) on <html>. Loaded in <head> to avoid a flash. */
(function () {
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  function apply() {
    document.documentElement.setAttribute('data-bs-theme', mq && mq.matches ? 'dark' : 'light');
  }
  apply();
  if (mq && mq.addEventListener) { mq.addEventListener('change', apply); }
})();
