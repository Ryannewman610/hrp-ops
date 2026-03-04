"""01_login_save_state.py — Auto-login to HRP using saved session.

Uses saved auth.json cookies if available. Falls back to manual login
only if the session has expired (detected by checking for login redirect).

Usage:
    python scripts/01_login_save_state.py          # auto or manual
    python scripts/01_login_save_state.py --force   # force fresh manual login
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URLS_PATH = ROOT / "scripts" / "hrp_urls.json"
AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"


def load_roster_url() -> str:
    if not URLS_PATH.exists():
        raise FileNotFoundError(f"Missing URL config: {URLS_PATH}")
    data = json.loads(URLS_PATH.read_text(encoding="utf-8"))
    url = data.get("stable_roster_url")
    if not url:
        raise ValueError("stable_roster_url is missing in scripts/hrp_urls.json")
    return url


def is_logged_in(page) -> bool:
    """Check if we're on the actual roster page (not redirected to login)."""
    url = page.url.lower()
    # If redirected to login page or see login form, session expired
    if "login" in url or "signin" in url or "account" in url:
        return False
    # Check for roster content
    try:
        page.wait_for_selector("table, .horse, #roster", timeout=5000)
        return True
    except Exception:
        # If no roster content, check if page has any stable content
        content = page.content().lower()
        return "stable" in content and "login" not in content


def main() -> None:
    force_manual = "--force" in sys.argv
    roster_url = load_roster_url()
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Try auto-login with saved session
        if AUTH_PATH.exists() and not force_manual:
            print("Using saved session from auth.json...")
            context = browser.new_context(storage_state=str(AUTH_PATH))
            page = context.new_page()
            page.goto(roster_url, wait_until="domcontentloaded", timeout=30000)

            if is_logged_in(page):
                print("✅ Auto-login successful! Session is still valid.")
                # Re-save to refresh cookie timestamps
                context.storage_state(path=str(AUTH_PATH))
                context.close()
                browser.close()
                return
            else:
                print("⚠ Saved session expired. Falling back to manual login...")
                context.close()

        # Manual login fallback
        browser.close()
        browser = p.chromium.launch(headless=False)  # visible browser for manual login
        context = browser.new_context()
        page = context.new_page()
        page.goto(roster_url, wait_until="domcontentloaded")
        print(f"Opened roster page: {roster_url}")
        input("Log in manually, then press Enter to save session state...")

        context.storage_state(path=str(AUTH_PATH))
        print(f"Saved auth state to: {AUTH_PATH}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
