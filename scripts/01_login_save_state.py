import json
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


def main() -> None:
    roster_url = load_roster_url()
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
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
