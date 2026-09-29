"""Visual validation for DjangoCMS pages — takes screenshots and reports what's visible."""
import sys
import os

def run(url="http://localhost:8000/home/", output="/tmp/cms-check.png"):
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        
        # Navigate and wait for network to be idle
        response = page.goto(url, wait_until="networkidle", timeout=15000)
        
        if response and response.status >= 400:
            print(f"ERROR: HTTP {response.status} for {url}")
            browser.close()
            sys.exit(1)
        
        # Take screenshot
        page.screenshot(path=output, full_page=True)
        print(f"Screenshot saved: {output}")
        
        # Extract visible text content for analysis
        body_text = page.inner_text("body")
        html = page.content()
        
        # Check for common issues
        issues = []
        
        # Check for 404
        if "page not found" in html.lower() or "<h1>404</h1>" in html or "not found" in html.lower():
            issues.append("PAGE NOT FOUND (404)")
        
        # Check for template errors
        if "template does not exist" in html.lower():
            issues.append("TEMPLATE ERROR — template file not found")
        
        # Check for server error
        if "operationalerror" in html.lower() or "modulenotfounderror" in html.lower() or "traceback" in html.lower():
            issues.append("SERVER ERROR — check logs")
        
        # Check for empty placeholders
        if not body_text.strip():
            issues.append("EMPTY PAGE — no visible content")
        
        # Check for Django error page
        if "systemcheckerror" in html.lower() or "raised by: cms.views.details" in html.lower():
            issues.append("CMS ERROR — check server logs")
        
        # Report what's visible
        print(f"\n=== VISUAL CHECK RESULTS ===")
        print(f"URL: {url}")
        print(f"Status: {response.status if response else 'N/A'}")
        print(f"Visible text (first 500 chars):")
        print(body_text[:500])
        print("\n=== ISSUES ===")
        if issues:
            for issue in issues:
                print(f"  ❌ {issue}")
        else:
            print("  ✅ No obvious issues detected")
        
        browser.close()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/home/"
    output = sys.argv[2] if len(sys.argv) > 2 else "/tmp/cms-check.png"
    run(url, output)
