"""00_auth_check.py — Verify HRP session is still authenticated.

Loads inputs/export/auth.json, opens /stables/index.aspx headless,
checks for stable name or login redirect.

Exit codes:
  0 = AUTH_OK (session valid)
  1 = AUTH_EXPIRED (re-login required)
  2 = AUTH_MISSING (no auth.json found)
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"
STABLE_URL = "https://www.horseracingpark.com/stables/index.aspx"
EXPECTED_STABLE = "Ire Iron Stables"


def main() -> None:
    if not AUTH_PATH.exists():
        print(f"AUTH_MISSING: {AUTH_PATH} not found.")
        print("Fix: run  python scripts/01_login_save_state.py")
        sys.exit(2)

    # Quick sanity: can we parse the file?
    try:
        data = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        n_cookies = len(data.get("cookies", []))
        print(f"Loaded auth.json ({n_cookies} cookies)")
    except Exception as e:
        print(f"AUTH_MISSING: auth.json is corrupt — {e}")
        sys.exit(2)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(AUTH_PATH))
        page = context.new_page()

        try:
            page.goto(STABLE_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"AUTH_EXPIRED: could not load stable page — {e}")
            context.close()
            browser.close()
            sys.exit(1)

        url = (page.url or "").lower()
        body = page.inner_text("body") or ""

        context.close()
        browser.close()

    # Check for login redirect
    if "/login" in url:
        print("AUTH_EXPIRED: redirected to login page.")
        print("Fix: run  python scripts/01_login_save_state.py")
        sys.exit(1)

    # Check for stable name
    if EXPECTED_STABLE.lower() in body.lower():
        # Extract balance if possible
        for line in body.splitlines():
            if "balance" in line.lower():
                print(f"  {line.strip()}")
                break
        print(f"AUTH_OK: logged in as {EXPECTED_STABLE}")
        sys.exit(0)

    # Check for logout link (another auth indicator)
    if "logout" in body.lower():
        print(f"AUTH_OK: session valid (Logout link found)")
        sys.exit(0)

    # Ambiguous — probably expired
    print("AUTH_EXPIRED: page loaded but stable name not found.")
    print(f"  URL: {url}")
    print(f"  Body preview: {body[:200]}")
    print("Fix: run  python scripts/01_login_save_state.py")
    sys.exit(1)


if __name__ == "__main__":
    main()
