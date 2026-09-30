"""Unit tests for scripts/visual_check.py."""
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ---------------------------------------------------------------------------
# Test HTML fixtures
# ---------------------------------------------------------------------------

HTML_OK = """\
<!DOCTYPE html>
<html><head><title>Home</title></head>
<body><h1>Welcome</h1><p>Hello world content</p></body></html>
"""

HTML_NOT_FOUND = """\
<!DOCTYPE html>
<html><head><title>Page not found</title></head>
<body><h1>Page not found</h1></body></html>
"""

HTML_CONSOLE_ERROR = """\
<!DOCTYPE html>
<html><head><title>Error Page</title></head>
<body><h1>Error</h1><script>console.error("something broke");</script></body></html>
"""

HTML_DJANGO_ERR = """\
<!DOCTYPE html>
<html><head><title>Error</title></head>
<body><div id="summary">Exception: Something went wrong</div></body></html>
"""

HTML_EMPTY = """\
<!DOCTYPE html>
<html><head><title>Empty</title></head>
<body></body></html>
"""


class _Handler(SimpleHTTPRequestHandler):
    """Maps paths to our HTML fixtures."""
    fixtures = {
        "/ok": HTML_OK,
        "/notfound": HTML_NOT_FOUND,
        "/console-error": HTML_CONSOLE_ERROR,
        "/django-err": HTML_DJANGO_ERR,
        "/empty": HTML_EMPTY,
    }

    def do_GET(self):
        if self.path in self.fixtures:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(self.fixtures[self.path].encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # silence request logs


class TestVisualCheck(unittest.TestCase):
    """Run visual_check.py as a subprocess against a local HTTP server."""

    @classmethod
    def setUpClass(cls):
        cls._server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls._port = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()

    def _run(self, *extra_args):
        """Run visual_check.py and return CompletedProcess."""
        base = [sys.executable, "-m", "scripts.visual_check"]
        # Use the module path so relative imports work
        cmd = [os.path.join(os.path.dirname(__file__), "visual_check.py")]
        return subprocess.run(
            cmd + [f"http://127.0.0.1:{self._port}"] + list(extra_args),
            capture_output=True, text=True, timeout=30,
        )

    def test_ok_page_exits_0(self):
        """A normal page with content should exit 0 and show PASS."""
        result = self._run(f"/ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RESULT: PASS", result.stdout)

    def test_404_page_exits_1(self):
        """Page titled 'Page not found' should exit 1."""
        result = self._run(f"/notfound")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ISSUE: 404 page", result.stdout)

    def test_console_error_exits_1(self):
        """Page with console.error should exit 1."""
        result = self._run(f"/console-error")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ISSUE: console error:", result.stdout)

    def test_django_error_page_exits_1(self):
        """Page with #summary containing Exception should exit 1."""
        result = self._run(f"/django-err")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ISSUE: django error page", result.stdout)

    def test_empty_page_exits_1(self):
        """Empty body text should exit 1."""
        result = self._run(f"/empty")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ISSUE: empty page", result.stdout)

    def test_expect_text_pass(self):
        """--expect-text matching visible text should not add an issue."""
        result = self._run(f"/ok", "--expect-text", "Hello world")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ISSUE: missing text", result.stdout)

    def test_expect_text_fail(self):
        """--expect-text not found should add ISSUE: missing text."""
        result = self._run(f"/ok", "--expect-text", "zzznotexist")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ISSUE: missing text: zzznotexist", result.stdout)


# ---------------------------------------------------------------------------
# Skip guard — playwright must be importable
# ---------------------------------------------------------------------------
def _has_playwright():
    try:
        __import__("playwright.sync_api")
        return True
    except ImportError:
        return False


class _SkipAll(unittest.TestCase):
    """Fallback when playwright is not installed."""
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def test_skip(self):
        self.skipTest("playwright not installed; skipping visual_check tests")

    def _run(self, *extra):
        self.skipTest("playwright not installed; skipping visual_check tests")


# ---------------------------------------------------------------------------
# Swap in fallback if playwright is missing
# ---------------------------------------------------------------------------
if not _has_playwright():
    # Replace the real test class with the skip-all stub
    import types
    import sys as _sys
    _mod = _sys.modules[__name__]
    _mod.TestVisualCheck = _SkipAll  # type: ignore


if __name__ == "__main__":
    unittest.main()
