import argparse
import json
import re
import shutil
import time
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
URLS_PATH = ROOT / "scripts" / "hrp_urls.json"
AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"
RAW_ROOT = ROOT / "inputs" / "export" / "raw"
MANIFEST_PATH = ROOT / "inputs" / "export" / "export_manifest.json"
DELAY_SECONDS = 2
GLOBAL_DIR = "_global"

# All horse page types (used in weekly mode)
PAGE_SPECS = [
    ("profile_allraces", "/stables/viewhorse.aspx?horsename={horse}&AllRaces=Yes"),
    ("profile_printable", "/stables/viewhorseprintable.aspx?horsename={horse}&AllRaces=Yes"),
    ("works_all", "/stables/viewWorkdetails.aspx?horsename={horse}&AllWorks=Yes"),
    ("meters", "/stables/viewmeters.aspx?horsename={horse}"),
    ("pedigree", "/stables/viewpedigree.aspx?horsename={horse}"),
    ("conformation", "/stables/viewconformation.aspx?horsename={horse}"),
    ("accessories", "/stables/accessorieshorse.aspx?horsename={horse}"),
    ("foals", "/stables/viewfoals.aspx?horsename={horse}"),
]

# High-frequency pages only (used in daily mode)
DAILY_PAGE_SPECS = [
    ("profile_allraces", "/stables/viewhorse.aspx?horsename={horse}&AllRaces=Yes"),
    ("works_all", "/stables/viewWorkdetails.aspx?horsename={horse}&AllWorks=Yes"),
    ("meters", "/stables/viewmeters.aspx?horsename={horse}"),
]

# Global (non-horse) pages for planning
GLOBAL_PAGES = [
    ("race_calendar", "/races/index.aspx"),
    ("stakes_calendar", "/races/stakes.aspx"),
    ("weather", "/stables/extendedweather.aspx"),
    ("account_history", "/myaccount/accounthistory.aspx"),
    ("results", "/stats/results.aspx"),
]


def polite_delay() -> None:
    print(f"Waiting {DELAY_SECONDS}s...")
    time.sleep(DELAY_SECONDS)


def load_roster_url() -> str:
    if not URLS_PATH.exists():
        raise FileNotFoundError(f"Missing URL config: {URLS_PATH}")
    data = json.loads(URLS_PATH.read_text(encoding="utf-8"))
    url = data.get("stable_roster_url")
    if not url:
        raise ValueError("stable_roster_url is missing in scripts/hrp_urls.json")
    return url


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    clean = parsed._replace(fragment="")
    return clean.geturl()


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return value or "horse"


def is_strict_horse_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.path.lower() != "/stables/viewhorse.aspx":
        return False
    qs = parse_qs(parsed.query)
    if "horsename" not in qs:
        return False
    return bool(qs["horsename"] and qs["horsename"][0].strip())


def parse_horse_name_from_url(url: str) -> str:
    qs = parse_qs(urlparse(url).query)
    horse_vals = qs.get("horsename", [])
    if not horse_vals or not horse_vals[0].strip():
        raise RuntimeError(f"Missing horsename in discovered URL: {url}")
    return horse_vals[0].strip()


def horse_folder_name(horse_name: str) -> str:
    return slugify(horse_name)


def ensure_unique_dir(base_name: str, used_names: Set[str]) -> str:
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name

    i = 2
    while True:
        candidate = f"{base_name}_{i}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        i += 1


def extract_roster_table_links(page) -> List[Dict[str, str]]:
    tables = page.evaluate(
        """
        () => {
            const strictHorseLinks = (table) => {
                const links = Array.from(table.querySelectorAll('a[href]'));
                return links
                    .filter(a => a.closest('table') === table)
                    .map(a => ({
                        href: (a.getAttribute('href') || '').trim(),
                        text: (a.innerText || a.textContent || '').trim(),
                    }))
                    .filter(a => {
                        const low = a.href.toLowerCase();
                        return low.includes('/stables/viewhorse.aspx') && low.includes('horsename=');
                    });
            };

            const out = [];
            const allTables = Array.from(document.querySelectorAll('table'));
            for (let i = 0; i < allTables.length; i++) {
                const t = allTables[i];
                const text = (t.innerText || '').toLowerCase();
                const horseLinks = strictHorseLinks(t);
                out.push({
                    idx: i,
                    text,
                    horseLinks,
                });
            }
            return out;
        }
        """
    )

    best = None
    best_score = -10**9
    for t in tables:
        horse_links = t.get("horseLinks", [])
        if not horse_links:
            continue
        text = t.get("text", "")
        score = 0
        if "horse name" in text:
            score += 50
        if "stam" in text:
            score += 10
        if "consist" in text:
            score += 10
        if "mode" in text:
            score += 10
        if "recent races" in text:
            score -= 30
        if "recent claims" in text:
            score -= 30
        if "nominations" in text:
            score -= 30
        score += min(len(horse_links), 100)

        if score > best_score:
            best_score = score
            best = t

    if not best:
        raise RuntimeError("Could not find stable roster table with horse links.")

    links = best.get("horseLinks", [])
    print(
        f"Using roster table index {best.get('idx')} with {len(links)} horse links (score={best_score})"
    )

    out: List[Dict[str, str]] = []
    for a in links:
        href = (a.get("href") or "").strip()
        text = (a.get("text") or "").strip()
        if href:
            out.append({"href": href, "text": text})
    return out


def discover_horse_urls(page, roster_url: str) -> List[Dict[str, str]]:
    base_host = urlparse(roster_url).netloc.lower()
    try:
        links = extract_roster_table_links(page)
    except RuntimeError as e:
        print(f"WARN: {e} Falling back to scanning all anchors.")
        links = page.evaluate(
            """
            () => {
                const out = [];
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                for (const a of anchors) {
                    const href = (a.getAttribute('href') || '').trim();
                    const low = href.toLowerCase();
                    if (low.includes('/stables/viewhorse.aspx') && low.includes('horsename=')) {
                        out.push({
                            href,
                            text: (a.innerText || a.textContent || '').trim(),
                        });
                    }
                }
                return out;
            }
            """
        )
    seen: Set[str] = set()
    horses: List[Dict[str, str]] = []

    for item in links:
        href_low = item["href"].lower()
        if "/stables/viewhorse.aspx" not in href_low:
            continue
        if "horsename=" not in href_low:
            continue

        abs_url = normalize_url(urljoin(roster_url, item["href"]))
        parsed = urlparse(abs_url)
        if not parsed.scheme.startswith("http"):
            continue
        if parsed.netloc.lower() != base_host:
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        horses.append({"url": abs_url, "text": item["text"]})

    invalid = [h["url"] for h in horses if not is_strict_horse_profile_url(h["url"])]
    if invalid:
        preview = "\n".join(invalid[:10])
        raise RuntimeError(
            "Safety abort: discovered URL(s) outside strict pattern "
            "/stables/viewhorse.aspx?horsename=...\n"
            f"{preview}"
        )

    return horses


def save_page(page, dest_dir: Path, page_type: str) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    html_path = dest_dir / f"{page_type}.html"
    png_path = dest_dir / f"{page_type}.png"

    html_path.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(png_path), full_page=True)
    print(f"Saved {page_type}: {html_path}")
    return 1


def safe_goto(page, url: str) -> None:
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except PlaywrightTimeoutError:
            try:
                page.goto(url, wait_until="load", timeout=60000)
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
        except PlaywrightError as e:
            last_err = e
            if attempt < 3:
                print(f"Goto retry {attempt}/3 for: {url}")
                time.sleep(2)
                continue
            break
    if last_err:
        raise last_err


def assert_not_login_page(page, expected_url: str) -> None:
    current_url = (page.url or "").lower()
    if "/login/" in current_url or "/login" in current_url:
        raise RuntimeError(
            f"Safety abort: redirected to login page while loading {expected_url}. Current URL: {page.url}"
        )

    body_text = (page.inner_text("body") or "").lower()
    login_markers = ["log in", "login", "sign in", "username", "password"]
    marker_hits = sum(1 for marker in login_markers if marker in body_text)
    if marker_hits >= 3:
        raise RuntimeError(
            f"Safety abort: page content appears to be a login page while loading {expected_url}."
        )
    # Catch redirect to site homepage (not /stables/index.aspx which is the roster)
    if "/stables/" not in current_url and "/index.aspx" in current_url and "/stables/" in expected_url.lower():
        raise RuntimeError(
            f"Safety abort: redirected to site index while loading {expected_url}. Session may be invalid."
        )


def build_page_urls(roster_url: str, horse_name: str) -> List[Dict[str, str]]:
    origin = f"{urlparse(roster_url).scheme}://{urlparse(roster_url).netloc}"
    encoded_name = quote_plus(horse_name)
    out = []
    for page_type, template in PAGE_SPECS:
        rel = template.format(horse=encoded_name)
        out.append({"page_type": page_type, "url": f"{origin}{rel}"})
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export HRP stable data")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="List discovered horse profile URLs and exit.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of horses to export.",
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly"],
        default="daily",
        help="daily = roster + globals + 3 key pages/horse (~21 min). weekly = full 8-page export (~56 min).",
    )
    parser.add_argument(
        "--skip-global",
        action="store_true",
        help="Skip global page exports (race calendar, weather, etc.).",
    )
    return parser.parse_args()


def export_global_pages(page, roster_url: str, manifest: dict) -> None:
    """Export global (non-horse) pages for planning."""
    origin = f"{urlparse(roster_url).scheme}://{urlparse(roster_url).netloc}"
    global_dir = RAW_ROOT / GLOBAL_DIR
    global_dir.mkdir(parents=True, exist_ok=True)
    manifest["global_pages"] = {"saved": [], "failed": {}}

    for page_type, rel_url in GLOBAL_PAGES:
        url = f"{origin}{rel_url}"
        polite_delay()
        try:
            safe_goto(page, url)
            assert_not_login_page(page, url)
            save_page(page, global_dir, page_type)
            manifest["pages_exported"] += 1
            manifest["global_pages"]["saved"].append(page_type)
            print(f"  Global: {page_type} ✓")
        except Exception as e:  # noqa: BLE001
            msg = str(e).splitlines()[0]
            print(f"  Global: {page_type} FAILED — {msg}")
            manifest["global_pages"]["failed"][page_type] = msg


def save_manifest(manifest: dict) -> None:
    """Write manifest to disk (used for normal + partial saves)."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    roster_url = load_roster_url()
    if not AUTH_PATH.exists():
        raise FileNotFoundError(
            f"Missing auth file: {AUTH_PATH}. Run scripts\\01_login_save_state.py first."
        )

    RAW_ROOT.mkdir(parents=True, exist_ok=True)

    # Choose page spec based on mode
    active_specs = DAILY_PAGE_SPECS if args.mode == "daily" else PAGE_SPECS
    print(f"Export mode: {args.mode} ({len(active_specs)} pages/horse)")

    manifest: Dict = {
        "roster_url": roster_url,
        "mode": args.mode,
        "horses_discovered": 0,
        "pages_exported": 0,
        "horses": [],
        "status": "running",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(AUTH_PATH))
        page = context.new_page()

        # --- Verify auth with roster page (no delay — go immediately) ---
        safe_goto(page, roster_url)
        try:
            assert_not_login_page(page, roster_url)
        except RuntimeError:
            print("\n❌ AUTH_EXPIRED: session is not valid. Re-run 01_login_save_state.py first.")
            manifest["status"] = "auth_failed"
            save_manifest(manifest)
            context.close()
            browser.close()
            raise SystemExit(1)

        print(f"Final roster URL: {page.url}")
        debug_dir = ROOT / "outputs" / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "roster.html").write_text(page.content(), encoding="utf-8")

        # --- Save roster page itself as a global page ---
        roster_dir = RAW_ROOT / GLOBAL_DIR
        roster_dir.mkdir(parents=True, exist_ok=True)
        save_page(page, roster_dir, "stable_roster")
        manifest["pages_exported"] += 1

        # --- Export global pages ---
        if not args.skip_global:
            print("\n=== Exporting Global Pages ===")
            export_global_pages(page, roster_url, manifest)

        # --- Discover horses ---
        safe_goto(page, roster_url)
        horse_links = discover_horse_urls(page, roster_url)
        manifest["horses_discovered"] = len(horse_links)
        print(f"\nDiscovered {len(horse_links)} horse profile links")

        if args.list_only:
            print("First 10 horse URLs:")
            for url in [h["url"] for h in horse_links[:10]]:
                print(url)
            context.close()
            browser.close()
            return

        # --- Clean up stale horse directories not in the live roster ---
        discovered_dirs = {
            horse_folder_name(parse_horse_name_from_url(h["url"]))
            for h in horse_links
        }
        stale_removed = 0
        for existing in list(RAW_ROOT.iterdir()):
            if existing.is_dir() and existing.name != GLOBAL_DIR and existing.name not in discovered_dirs:
                shutil.rmtree(existing)
                print(f"  Removed stale: {existing.name}")
                stale_removed += 1
        if stale_removed:
            print(f"  Cleaned up {stale_removed} stale horse directories")

        if args.limit is not None:
            if args.limit < 1:
                raise ValueError("--limit must be >= 1")
            horse_links = horse_links[: args.limit]

        used_horse_dirs: Set[str] = set()
        auth_expired = False

        print(f"\n=== Exporting {len(horse_links)} Horses ({args.mode} mode) ===")
        for idx, horse in enumerate(horse_links, start=1):
            profile_url = horse["url"]
            horse_name = parse_horse_name_from_url(profile_url)
            base_dir_name = horse_folder_name(horse_name)
            horse_dir_name = ensure_unique_dir(base_dir_name, used_horse_dirs)
            horse_dir = RAW_ROOT / horse_dir_name

            horse_record: Dict = {
                "horse_name": horse_name,
                "horse_dir": horse_dir_name,
                "source_profile_url": profile_url,
                "page_urls": {},
                "saved_pages": [],
                "failed_pages": {},
            }

            print(f"[{idx}/{len(horse_links)}] {horse_name}")
            page_targets = build_page_urls(roster_url, horse_name)

            # Filter to active specs for this mode
            active_types = {spec[0] for spec in active_specs}
            page_targets = [t for t in page_targets if t["page_type"] in active_types]

            for target in page_targets:
                polite_delay()
                horse_record["page_urls"][target["page_type"]] = target["url"]
                try:
                    safe_goto(page, target["url"])
                    assert_not_login_page(page, target["url"])
                    manifest["pages_exported"] += save_page(page, horse_dir, target["page_type"])
                    horse_record["saved_pages"].append(target["page_type"])
                except RuntimeError as e:
                    msg = str(e).splitlines()[0]
                    if "Safety abort" in msg:
                        print(f"\n❌ SESSION EXPIRED after {idx - 1} horses.")
                        print(f"   Re-run: python scripts/01_login_save_state.py")
                        print(f"   Then:   python scripts/02_export_stable.py --mode {args.mode}")
                        horse_record["failed_pages"][target["page_type"]] = msg
                        manifest["horses"].append(horse_record)
                        auth_expired = True
                        break
                    print(f"  WARN: {target['page_type']} — {msg}")
                    horse_record["failed_pages"][target["page_type"]] = msg
                except Exception as e:  # noqa: BLE001
                    msg = str(e).splitlines()[0]
                    print(f"  WARN: {target['page_type']} — {msg}")
                    horse_record["failed_pages"][target["page_type"]] = msg

            manifest["horses"].append(horse_record)
            if auth_expired:
                break

        context.close()
        browser.close()

    manifest["status"] = "partial" if auth_expired else "complete"
    save_manifest(manifest)

    print(f"\nExport {'PARTIAL' if auth_expired else 'finished'}.")
    print(f"  Mode: {args.mode}")
    print(f"  Horses: {len(manifest['horses'])}/{manifest['horses_discovered']}")
    print(f"  Pages: {manifest['pages_exported']}")
    print(f"  Manifest: {MANIFEST_PATH}")
    if auth_expired:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

