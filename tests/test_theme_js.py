"""Behaviour of assets/default-site/static/js/theme.js, executed under node with a small DOM stub.

Skipped when node is not installed. The browser behaviour (reload persistence, mobile layout, contrast) is
checked with Playwright by hand (see the PR); these tests pin the logic.
"""
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1] / "assets" / "default-site"
THEME = SITE / "static" / "js" / "theme.js"
BASE = (SITE / "templates" / "base.html").read_text(encoding="utf-8")
CSS = (SITE / "static" / "css" / "site.css").read_text(encoding="utf-8")

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const cfg = JSON.parse(process.argv[2]);

function makeEnv() {
  const store = Object.assign({}, cfg.stored || {});
  const attrs = {};
  const listeners = {doc: {}, win: {}, mq: []};
  const button = {
    hidden: true, attrs: {}, nodeType: 1, parentNode: null,
    hasAttribute(n) { return n === 'data-theme-toggle'; },
    setAttribute(n, v) { this.attrs[n] = v; },
  };
  const child = {nodeType: 1, parentNode: button, hasAttribute() { return false; }};
  const mq = {
    matches: !!cfg.osDark,
    addEventListener(t, fn) { listeners.mq.push(fn); },
  };
  const localStorage = cfg.storageThrows ? {
    getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); },
  } : {
    getItem(k) { return k in store ? store[k] : null; },
    setItem(k, v) { store[k] = String(v); },
  };
  const document = {
    documentElement: {
      getAttribute(n) { return n in attrs ? attrs[n] : null; },
      setAttribute(n, v) { attrs[n] = v; },
    },
    querySelectorAll() { return [button]; },
    addEventListener(t, fn) { (listeners.doc[t] = listeners.doc[t] || []).push(fn); },
  };
  const window = {
    matchMedia: cfg.noMatchMedia ? undefined : () => mq,
    localStorage, addEventListener(t, fn) { (listeners.win[t] = listeners.win[t] || []).push(fn); },
  };
  return {store, attrs, listeners, button, child, mq, document, window};
}

const env = makeEnv();
vm.runInContext(src, vm.createContext({window: env.window, document: env.document}));
const out = {};
for (const step of cfg.steps || []) {
  if (step === 'click') env.listeners.doc.click.forEach(f => f({target: env.child}));
  if (step === 'clickOutside') env.listeners.doc.click.forEach(f => f({target: {nodeType: 1, parentNode: null, hasAttribute() { return false; }}}));
  if (step === 'domready') (env.listeners.doc.DOMContentLoaded || []).forEach(f => f());
  if (step === 'osDark') { env.mq.matches = true; env.listeners.mq.forEach(f => f()); }
  if (step === 'osLight') { env.mq.matches = false; env.listeners.mq.forEach(f => f()); }
}
console.log(JSON.stringify({
  theme: env.attrs['data-bs-theme'], stored: env.store.theme === undefined ? null : env.store.theme,
  pressed: env.button.attrs['aria-pressed'], title: env.button.attrs.title, hidden: env.button.hidden,
}));
"""


def run(**cfg):
    out = subprocess.run([NODE, "-e", HARNESS, str(THEME), json.dumps(cfg)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_follows_os_when_nothing_is_stored():
    assert run(osDark=False)["theme"] == "light"
    r = run(osDark=True)
    assert (r["theme"], r["stored"], r["pressed"]) == ("dark", None, "true")


def test_stored_choice_wins_over_os():
    assert run(osDark=True, stored={"theme": "light"})["theme"] == "light"
    assert run(osDark=False, stored={"theme": "dark"})["theme"] == "dark"


def test_garbage_stored_value_is_ignored():
    assert run(osDark=True, stored={"theme": "purple"})["theme"] == "dark"


def test_click_flips_and_persists():
    r = run(osDark=False, steps=["click"])
    assert (r["theme"], r["stored"], r["pressed"]) == ("dark", "dark", "true")
    assert "light" in r["title"]
    r = run(osDark=False, steps=["click", "click"])
    assert (r["theme"], r["stored"], r["pressed"]) == ("light", "light", "false")


def test_click_outside_the_button_does_nothing():
    r = run(osDark=False, steps=["clickOutside"])
    assert (r["theme"], r["stored"]) == ("light", None)


def test_live_os_change_followed_only_without_a_stored_choice():
    assert run(osDark=False, steps=["osDark"])["theme"] == "dark"
    assert run(osDark=True, steps=["osLight"])["theme"] == "light"
    assert run(osDark=False, stored={"theme": "light"}, steps=["osDark"])["theme"] == "light"
    # a choice made with the toggle also pins the theme against later OS changes
    assert run(osDark=False, steps=["click", "osLight"])["theme"] == "dark"


def test_storage_failure_is_tolerated():
    r = run(osDark=False, storageThrows=True)
    assert r["theme"] == "light"
    r = run(osDark=False, storageThrows=True, steps=["click"])
    assert (r["theme"], r["stored"], r["pressed"]) == ("dark", None, "true")  # works for this page, not persisted


def test_no_matchmedia_defaults_to_light():
    assert run(noMatchMedia=True)["theme"] == "light"


def test_button_is_revealed_by_the_script():
    assert run(osDark=False)["hidden"] is False


# --- template and stylesheet (no node needed for the logic above, but these are cheap) ---

def test_base_template_has_an_accessible_toggle_button_outside_the_collapse():
    assert "data-theme-toggle" in BASE
    btn = BASE[BASE.index("<button type=\"button\" class=\"btn theme-toggle\""):]
    btn = btn[:btn.index("</button>")]
    assert 'aria-label="Dark mode"' in btn and 'aria-pressed="false"' in btn and "hidden" in btn
    assert BASE.index("data-theme-toggle") < BASE.index('class="collapse navbar-collapse"')  # visible on mobile
    assert 'src="{% static \'js/theme.js\' %}"' in BASE.split("</head>")[0]  # early: no flash


def test_css_keeps_the_no_js_media_fallback_and_hides_the_button_until_js():
    assert "@media (prefers-color-scheme: dark)" in CSS and ":root:not([data-bs-theme])" in CSS
    assert ".theme-toggle[hidden]" in CSS and ".theme-toggle:focus-visible" in CSS
