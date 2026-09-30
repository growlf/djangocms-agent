"""Tests for scripts/visual_check.py (need playwright + chromium; skipped otherwise)."""
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = str(Path(__file__).with_name("visual_check.py"))

PAGES = {
    "/ok": "<html><head><title>Home</title></head><body><h1>Welcome</h1><p>Hello world content</p></body></html>",
    "/notfound": "<html><head><title>Page not found</title></head><body><h1>Page not found</h1></body></html>",
    "/mentions-404": "<html><head><title>Docs</title></head><body><h1>Docs</h1><p>If a page is not found, check the URL.</p></body></html>",
    "/console-error": '<html><head><title>X</title></head><body><h1>X</h1><script>console.error("something broke");</script></body></html>',
    "/django-err": '<html><head><title>E</title></head><body><div id="summary">Exception: boom</div></body></html>',
    "/empty": "<html><head><title>Empty</title></head><body></body></html>",
    "/missing-asset": '<html><head><title>A</title><link rel="stylesheet" href="/nope.css"></head><body><h1>A</h1></body></html>',
    "/mobile-width": '<html><head><title>M</title></head><body><h1 id="w">x</h1><script>document.getElementById("w").textContent="w="+window.innerWidth;</script></body></html>',
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write((body or "").encode())

    def log_message(self, *args):
        pass


def _has_playwright():
    try:
        __import__("playwright.sync_api")
        return True
    except ImportError:
        return False


@unittest.skipUnless(_has_playwright(), "playwright not installed; skipping visual_check tests")
class TestVisualCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_check(self, path, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, self.base + path, *args],
            capture_output=True, text=True, timeout=60,
        )

    def test_ok_page_passes(self):
        r = self.run_check("/ok")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RESULT: PASS", r.stdout)

    def test_404_page_fails(self):
        r = self.run_check("/notfound")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: 404 page", r.stdout)

    def test_page_merely_mentioning_not_found_passes(self):
        r = self.run_check("/mentions-404")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_http_404_fails(self):
        r = self.run_check("/does-not-exist")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: HTTP 404", r.stdout)

    def test_http_404_reported_once(self):
        r = self.run_check("/does-not-exist")
        self.assertEqual(r.stdout.count("ISSUE: HTTP 404"), 1)
        self.assertNotIn("ISSUE: request failed:", r.stdout)

    def test_login_with_unset_env_var_exits_2(self):
        r = self.run_check("/ok", "--login", "admin:VC_TEST_UNSET_VAR")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_console_error_fails(self):
        r = self.run_check("/console-error")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: console error:", r.stdout)

    def test_failed_subresource_fails(self):
        r = self.run_check("/missing-asset")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: request failed:", r.stdout)

    def test_django_error_page_fails(self):
        r = self.run_check("/django-err")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: django error page", r.stdout)

    def test_empty_page_fails(self):
        r = self.run_check("/empty")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: empty page", r.stdout)

    def test_expect_text(self):
        self.assertEqual(self.run_check("/ok", "--expect-text", "Hello world").returncode, 0)
        r = self.run_check("/ok", "--expect-text", "zzznotexist")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ISSUE: missing text: zzznotexist", r.stdout)

    def test_mobile_viewport(self):
        r = self.run_check("/mobile-width", "--mobile", "--expect-text", "w=390")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unreachable_exits_2(self):
        r = subprocess.run([sys.executable, SCRIPT, "http://127.0.0.1:1/"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
