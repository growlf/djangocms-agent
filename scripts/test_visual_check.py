"""Tests for scripts/visual_check.py (need playwright + chromium; skipped otherwise)."""
import subprocess
import os
import sys
from urllib.parse import parse_qs
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
    "/overflow": '<html><head><title>O</title></head><body><h1>Wide</h1><div style="width:3000px;height:10px;background:red"></div></body></html>',
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


class TestOverflowRule(unittest.TestCase):
    """Pure logic; runs without Playwright."""

    @staticmethod
    def rule():
        import importlib.util
        spec = importlib.util.spec_from_file_location("vc", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.overflow_issue

    def test_fits(self):
        self.assertIsNone(self.rule()(390, 390))

    def test_one_pixel_rounding_tolerated(self):
        self.assertIsNone(self.rule()(391, 390))

    def test_overflow_reported(self):
        msg = self.rule()(520, 390)
        self.assertIn("horizontal overflow", msg)
        self.assertTrue(msg.startswith("ISSUE:"))


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

    def test_horizontal_overflow_fails(self):
        r = self.run_check("/overflow", "--mobile")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: horizontal overflow", r.stdout)

    def test_no_overflow_passes(self):
        r = self.run_check("/ok", "--mobile")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_mobile_viewport(self):
        r = self.run_check("/mobile-width", "--mobile", "--expect-text", "w=390")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unreachable_exits_2(self):
        r = subprocess.run([sys.executable, SCRIPT, "http://127.0.0.1:1/"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


LOGIN_FORM = (
    "<html><head><title>Log in | Django site admin</title></head><body><h1>Django administration</h1>"
    '{note}<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="tok123">'
    '<input type="text" name="username" id="id_username"><input type="password" name="password" id="id_password">'
    '<input type="submit" value="Log in"></form></body></html>'
)
ODD_FORM = (
    "<html><head><title>Sign in</title></head><body><h1>Sign in</h1>"
    '<form method="post"><input name="email"><input name="pw" type="text"><div role="button">Go</div></form></body></html>'
)


class _AdminStub(BaseHTTPRequestHandler):
    """Mimics Django admin login: redirect to /admin/login/, csrf field, POST sets a session cookie."""
    USER, PASSWORD = "admin", "right-password"

    def _send(self, code, body="", headers=()):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/admin/":
            if "sessionid=ok" in self.headers.get("Cookie", ""):
                return self._send(200, "<html><head><title>Site administration | Django site admin</title></head>"
                                       "<body><h1>Site administration</h1><p>Welcome, admin.</p></body></html>")
            return self._send(302, headers=[("Location", "/admin/login/?next=/admin/")])
        if path == "/admin/login/":
            return self._send(200, LOGIN_FORM.format(note=""))
        if path == "/plain/":
            return self._send(200, "<html><head><title>Plain</title></head><body><h1>Plain</h1></body></html>")
        if path == "/odd/":
            return self._send(302, headers=[("Location", "/odd/login/")])
        if path == "/odd/login/":
            return self._send(200, ODD_FORM)
        self._send(404)

    def do_POST(self):
        data = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        ok = (data.get("csrfmiddlewaretoken") == ["tok123"] and data.get("username") == [self.USER]
              and data.get("password") == [self.PASSWORD])
        if ok:
            return self._send(302, headers=[("Location", "/admin/"), ("Set-Cookie", "sessionid=ok; Path=/")])
        self._send(200, LOGIN_FORM.format(note='<p class="errornote">Please enter the correct username and password.</p>'))

    def log_message(self, *args):
        pass


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vc", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLoginRule(unittest.TestCase):
    def test_login_url_means_failed(self):
        self.assertTrue(_load().login_failed("http://x/admin/login/?next=/admin/", False))

    def test_form_present_means_failed(self):
        self.assertTrue(_load().login_failed("http://x/admin/", True))

    def test_clean_state_is_success(self):
        self.assertFalse(_load().login_failed("http://x/admin/", False))


@unittest.skipUnless(_has_playwright(), "playwright not installed; skipping login tests")
class TestLogin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _AdminStub)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_login(self, path, password, out=None):
        env = dict(os.environ, VC_TEST_PW=password)
        args = [sys.executable, SCRIPT, self.base + path, "--login", "admin:VC_TEST_PW"]
        if out:
            args += ["--out", out]
        return subprocess.run(args, capture_output=True, text=True, timeout=90, env=env)

    def test_correct_credentials_pass_on_post_login_page(self):
        r = self.run_login("/admin/", "right-password")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RESULT: PASS", r.stdout)
        self.assertIn("Title: Site administration", r.stdout)
        self.assertNotIn("/login", r.stdout.split("Final URL:")[1].splitlines()[0])

    def test_wrong_credentials_fail(self):
        r = self.run_login("/admin/", "wrong")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: login failed", r.stdout)
        self.assertIn("RESULT: FAIL", r.stdout)
        self.assertNotIn("RESULT: PASS", r.stdout)

    def test_different_login_markup_fails_not_passes(self):
        r = self.run_login("/odd/", "right-password")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: login", r.stdout)
        self.assertNotIn("RESULT: PASS", r.stdout)

    def test_no_login_form_on_page_fails(self):
        r = self.run_login("/plain/", "right-password")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ISSUE: login: no login form found", r.stdout)

    def test_password_not_printed(self):
        r = self.run_login("/admin/", "wrong-secret-xyz")
        self.assertNotIn("wrong-secret-xyz", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
