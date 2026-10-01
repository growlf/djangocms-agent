"""Visual validation for DjangoCMS pages — screenshots, console/request checks, and text analysis.

Asserts (each failure is an ISSUE line): HTTP status < 400, no console errors, no failed same-origin
subresource requests, not a 404 page, not a Django debug error page, non-empty visible text, no
horizontal overflow (documentElement.scrollWidth > clientWidth + 1px), and every --expect-text string
present. It does NOT check layout quality, colors/contrast, broken images that return 200, cross-origin
requests, or JavaScript behaviour: a human must look at the screenshot for those.
"""
import argparse
import os
import sys
import tempfile
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="Visual check for CMS pages. Takes a screenshot, "
                    "captures console/request errors, and reports visible text.",
    )
    parser.add_argument("url", help="Page URL to check (e.g. http://localhost:8000/)")
    parser.add_argument(
        "--out", default=None,
        help="Screenshot path (default: cms-check.png in the system temp dir)",
    )
    parser.add_argument(
        "--width", type=int, default=1280,
        help="Viewport width (default: 1280; height defaults to 800)",
    )
    parser.add_argument(
        "--mobile", action="store_true",
        help="Use mobile viewport 390x844 instead of desktop",
    )
    parser.add_argument(
        "--expect-text", action="append", default=[],
        metavar="TEXT",
        help="Require this string in visible body text (may repeat)",
    )
    parser.add_argument(
        "--login",
        help="USER:ENVVAR — log in before checking; password read from ENVVAR",
    )
    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _visible_text(page):
    """Return trimmed visible text from body element."""
    try:
        return page.inner_text("body").strip()
    except Exception:
        return ""


def _page_title(page):
    try:
        return page.title()
    except Exception:
        return ""


def _first_h1(page):
    try:
        h1 = page.query_selector("h1")
        return h1.inner_text().strip() if h1 else ""
    except Exception:
        return ""


def overflow_issue(scroll_width, client_width, tolerance=1):
    """Return an ISSUE string when the page scrolls horizontally, else None (pure; unit-tested)."""
    if scroll_width > client_width + tolerance:
        return (f"ISSUE: horizontal overflow: page is {scroll_width}px wide in a "
                f"{client_width}px viewport")
    return None


def _horizontal_overflow(page):
    """(scrollWidth, clientWidth) of the document element, or None if it cannot be read."""
    try:
        return tuple(page.evaluate(
            "[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

def check_url(url, out_path, width, height, expect_texts, login_spec):
    """Run the visual check.  Returns (issues_list, summary_dict)."""
    from playwright.sync_api import sync_playwright

    issues = []
    final_url = ""
    status = 0
    title = ""
    visible = ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(
                viewport={"width": width, "height": height},
                locale="en-US",
            )

            # Collect console errors and request failures
            console_errors = []
            failed_requests = []

            def _on_console(msg):
                if msg.type == "error":
                    console_errors.append(msg.text)

            def _on_response(response):
                if response.status >= 400:
                    try:
                        req = response.request
                        if req.is_navigation_request():
                            return  # already reported as "HTTP <code>"
                        orig = req.url
                        same_origin = (
                            urlparse(orig).netloc == urlparse(url).netloc
                        )
                        if same_origin:
                            failed_requests.append(
                                f"{orig} {response.status}"
                            )
                    except Exception:
                        pass

            context.on("console", _on_console)
            context.on("response", _on_response)

            page = context.new_page()

            # Login step
            if login_spec:
                user, env_var = login_spec.split(":", 1)
                if env_var not in os.environ:
                    raise ValueError(f"--login: environment variable {env_var} is not set")
                password = os.environ[env_var]
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                # Try common Django admin login patterns
                try:
                    page.get_by_label("Username", timeout=3000).fill(user)
                    page.get_by_label("Password", timeout=3000).fill(password)
                    page.get_by_role("button", name="log in", timeout=3000).click()
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    # If admin login fields not found, try generic form
                    try:
                        page.locator('input[name="username"], input[type="text"]').first.fill(user, timeout=3000)
                        page.locator('input[name="password"], input[type="password"]').first.fill(password, timeout=3000)
                        page.locator('button[type="submit"]').first.click(timeout=3000)
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass  # Login may not be possible on this page

            # Navigate
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Let subresources finish so missing assets are caught (tolerate slow pages)
            try:
                page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(500)

            final_url = page.url
            status = response.status if response else 0
            title = _page_title(page)
            visible = _visible_text(page)

            # Screenshot
            if out_path:
                page.screenshot(path=out_path, full_page=True)

            # --- Issue detection ---

            # 1. HTTP status >= 400
            if status and status >= 400:
                issues.append(f"ISSUE: HTTP {status}")

            # 2. Console errors
            for ce in console_errors:
                issues.append(f"ISSUE: console error: {ce}")

            # 3. Failed same-origin subresource requests
            for fr in failed_requests:
                issues.append(f"ISSUE: request failed: {fr}")

            # 4. 404 page (title or h1 is exactly "Page not found" / "Not Found")
            lower_title = title.lower()
            lower_h1 = _first_h1(page).lower()
            if lower_title in ("page not found", "not found") or \
               lower_h1 in ("page not found", "not found"):
                issues.append("ISSUE: 404 page")

            # 5. Django debug error page
            try:
                summary = page.query_selector("#summary")
                if summary:
                    stxt = summary.inner_text().lower()
                    if "exception" in stxt or "error" in stxt:
                        issues.append("ISSUE: django error page")
            except Exception:
                pass

            # 6. Empty visible body text
            if not visible:
                issues.append("ISSUE: empty page")

            # 7. horizontal overflow (page wider than the viewport)
            widths = _horizontal_overflow(page)
            if widths:
                msg = overflow_issue(*widths)
                if msg:
                    issues.append(msg)

            # 8. --expect-text checks
            for et in expect_texts:
                if et not in visible:
                    issues.append(f"ISSUE: missing text: {et}")

            browser.close()

    except Exception as e:
        # Script/browser error — print issue and exit 2
        print(f"ISSUE: script error: {e}", file=sys.stderr)
        # Write minimal output so the caller sees something
        print(f"URL: {url}")
        print("RESULT: FAIL (1 issues)")
        sys.exit(2)

    # --- Print summary ---
    print(f"URL: {url}")
    print(f"Final URL: {final_url}")
    print(f"Status: {status}")
    print(f"Title: {title}")
    if visible:
        print(f"Visible text (first 300 chars): {visible[:300]}")
    else:
        print("Visible text: (empty)")

    if issues:
        for iss in issues:
            print(iss)
    if issues:
        print(f"RESULT: FAIL ({len(issues)} issues)")
        sys.exit(1)
    print("RESULT: PASS")
    sys.exit(0)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    out_path = args.out or os.path.join(tempfile.gettempdir(), "cms-check.png")
    width = 390 if args.mobile else args.width
    height = 844 if args.mobile else 800

    check_url(
        url=args.url,
        out_path=out_path,
        width=width,
        height=height,
        expect_texts=args.expect_text,
        login_spec=args.login,
    )


if __name__ == "__main__":
    main()
