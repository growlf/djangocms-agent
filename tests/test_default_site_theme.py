"""Static checks of the default site's theme: contrast of the muted token and the active-menu / cite fixes."""
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "assets" / "default-site"
CSS = (SITE / "static" / "css" / "site.css").read_text(encoding="utf-8")
MENU = (SITE / "templates" / "menu" / "menu.html").read_text(encoding="utf-8")


def _block(selector_start):
    i = CSS.index(selector_start)
    return CSS[i:CSS.index("}", i)]


def _tokens(selector_start):
    return dict(re.findall(r"--site-color-([a-z-]+):\s*(#[0-9a-fA-F]{6})", _block(selector_start)))


def _lum(hexcolor):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


LIGHT = _tokens(":root, [data-bs-theme=\"light\"]")
DARK = _tokens("[data-bs-theme=\"dark\"] {")


def test_muted_text_contrast_in_both_schemes():
    for name, t in (("light", LIGHT), ("dark", DARK)):
        for bg in ("bg", "bg-alt"):
            assert ratio(t["text-muted"], t[bg]) >= 4.5, (name, bg)


def test_active_item_on_primary_contrast():
    for t in (LIGHT, DARK):
        assert ratio(t["on-primary"], t["primary"]) >= 4.5


def test_active_dropdown_item_overrides_secondary_text_colour():
    assert re.search(r"\.dropdown-item\.active\s+\.text-body-secondary\s*\{[^}]*color:\s*inherit\s*!important", CSS)


def test_blockquote_footer_uses_muted_token_not_bootstrap_grey():
    m = re.search(r"\.blockquote-footer\s*\{([^}]*)\}", CSS)
    assert m and "var(--site-color-text-muted)" in m.group(1)


def test_menu_never_pairs_muted_text_with_active_item_without_override():
    pairs = "dropdown-item" in MENU and "text-body-secondary" in MENU
    has_override = ".dropdown-item.active .text-body-secondary" in CSS
    assert not pairs or has_override
