import argparse
import hashlib
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"
CONFIG_PATH = ROOT / "scripts" / "11_forums_urls.json"
RAW_ROOT = ROOT / "inputs" / "forums" / "raw"
MANIFEST_PATH = ROOT / "inputs" / "forums" / "forum_export_manifest.json"
SEEN_URLS_PATH = ROOT / "outputs" / "forums" / "seen_urls.json"
SUMMARY_PATH = ROOT / "outputs" / "forums" / "CRAWL_SUMMARY.md"
STABLE_INDEX_URL = "https://www.horseracingpark.com/stables/index.aspx"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str) -> str:
    p = urlparse(url)
    # Keep query intact for pagination determinism, drop fragment.
    return p._replace(fragment="").geturl()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
            f"Safety abort: page appears to be login while loading {expected_url}."
        )

    expected = expected_url.lower()
    if "/forums/" in expected and "/stables/index.aspx" in current_url:
        raise RuntimeError(
            f"Safety abort: redirected to stable index while loading forum URL {expected_url}."
        )


def jitter_sleep(delay_min: float, delay_max: float) -> None:
    lo = max(0.0, min(delay_min, delay_max))
    hi = max(delay_min, delay_max)
    wait = random.uniform(lo, hi)
    print(f"Waiting {wait:.2f}s...")
    time.sleep(wait)


def extract_links(page) -> List[Dict[str, str]]:
    return page.evaluate(
        """
        () => {
            const out = [];
            for (const a of Array.from(document.querySelectorAll('a[href]'))) {
                out.push({
                    href: (a.getAttribute('href') || '').trim(),
                    text: (a.innerText || a.textContent || '').trim(),
                    rel: (a.getAttribute('rel') || '').trim(),
                });
            }
            return out;
        }
        """
    )


def same_origin(url: str, origin: str) -> bool:
    p = urlparse(url)
    o = urlparse(origin)
    return p.scheme in {"http", "https"} and p.netloc.lower() == o.netloc.lower()


def looks_like_pagination(url: str, text: str, rel: str) -> bool:
    low_text = text.strip().lower()
    if rel.strip().lower() == "next":
        return True
    if low_text in {"next", ">", ">>"}:
        return True
    if low_text.startswith("page"):
        return True
    low_url = url.lower()
    return any(k in low_url for k in ["page=", "p=", "start=", "offset="])


def looks_like_forum_or_thread(url: str, text: str) -> bool:
    low_url = url.lower()
    low_text = text.lower()
    if "/forums/" in low_url:
        return True
    url_markers = [
        "thread",
        "topic",
        "showtopic",
        "showthread",
        "viewtopic",
        "discussion",
        "board",
        "forum",
    ]
    if any(m in low_url for m in url_markers):
        return True
    text_markers = ["forum", "thread", "topic", "discussion"]
    return any(m in low_text for m in text_markers)


def maybe_filter_by_since_days(url: str, since_days: Optional[int]) -> bool:
    if since_days is None:
        return True
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=since_days)
    # Best-effort parse common date tokens in URL: YYYY-MM-DD or YYYY/MM/DD.
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", url)
    if not m:
        return True
    try:
        d = datetime(
            year=int(m.group(1)),
            month=int(m.group(2)),
            day=int(m.group(3)),
            tzinfo=timezone.utc,
        ).date()
        return d >= cutoff
    except ValueError:
        return True


def deterministic_path_for_url(base_dir: Path, url: str, fetched_at: datetime) -> Path:
    domain = (urlparse(url).netloc or "unknown").replace(":", "_").lower()
    day = fetched_at.strftime("%Y-%m-%d")
    sha = hashlib.sha1(url.encode("utf-8")).hexdigest()
    out_dir = base_dir / domain / day
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{sha}.html"


def discover_seed_url(page, delay_min: float, delay_max: float) -> str:
    jitter_sleep(delay_min, delay_max)
    safe_goto(page, STABLE_INDEX_URL)
    assert_not_login_page(page, STABLE_INDEX_URL)
    links = extract_links(page)
    for item in links:
        text = (item.get("text") or "").strip()
        href = (item.get("href") or "").strip()
        if not href:
            continue
        if "simracing form" in text.lower() or "forum" in text.lower():
            seed = normalize_url(urljoin(page.url, href))
            print(f"Discovered seed URL: {seed}")
            return seed
    raise RuntimeError(
        "Could not auto-discover forum seed URL from stables index nav."
    )


def apply_since_days_query(url: str, since_days: Optional[int]) -> str:
    if since_days is None:
        return url
    p = urlparse(url)
    qs = parse_qs(p.query)
    if "since_days" not in qs:
        qs["since_days"] = [str(since_days)]
    new_q = urlencode(qs, doseq=True)
    return normalize_url(urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, "")))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Automatic forum crawler (Playwright, incremental).")
    ap.add_argument("--seed", default="", help="Optional seed URL.")
    ap.add_argument("--max-pages", type=int, default=200, help="Max pages to fetch.")
    ap.add_argument("--since-days", type=int, default=None, help="Optional best-effort recency hint.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", help="Run browser headless.")
    mode.add_argument("--headed", action="store_true", help="Run browser with UI.")
    ap.add_argument("--auth", default=str(DEFAULT_AUTH_PATH), help="Optional storage_state path.")
    ap.add_argument("--allow-external", action="store_true", help="Allow crawling external origins.")
    ap.add_argument("--delay-min", type=float, default=None, help="Min delay seconds.")
    ap.add_argument("--delay-max", type=float, default=None, help="Max delay seconds.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_json(CONFIG_PATH, {})
    cfg_seed_urls = list(cfg.get("seed_urls", []))
    cfg_allow_external = bool(cfg.get("allow_external", False))
    cfg_delay_min = float(cfg.get("delay_seconds_min", 2.0))
    cfg_delay_max = float(cfg.get("delay_seconds_max", 4.0))

    delay_min = cfg_delay_min if args.delay_min is None else float(args.delay_min)
    delay_max = cfg_delay_max if args.delay_max is None else float(args.delay_max)
    allow_external = bool(args.allow_external or cfg_allow_external)
    max_pages = max(1, int(args.max_pages))

    manifest: List[Dict[str, str]] = load_json(MANIFEST_PATH, [])
    seen_urls: Set[str] = set(load_json(SEEN_URLS_PATH, []))

    stats = {
        "started_at": utc_now_iso(),
        "seed_url": "",
        "max_pages": max_pages,
        "fetched": 0,
        "skipped_seen": 0,
        "queued": 0,
        "discovered_links": 0,
        "failures": 0,
        "allow_external": allow_external,
    }
    failures: List[Dict[str, str]] = []

    try:
        with sync_playwright() as p:
            headless = not args.headed
            if args.headless:
                headless = True
            browser = p.chromium.launch(headless=headless)

            auth_path = Path(args.auth) if args.auth else None
            context = None
            if auth_path and auth_path.exists():
                context = browser.new_context(storage_state=str(auth_path))
            else:
                print("Auth state missing or not provided; running unauthenticated.")
                context = browser.new_context()
            page = context.new_page()

            seed = args.seed.strip()
            if not seed and cfg_seed_urls:
                seed = cfg_seed_urls[0]
            if not seed:
                seed = discover_seed_url(page, delay_min=delay_min, delay_max=delay_max)
            seed = apply_since_days_query(normalize_url(seed), args.since_days)
            stats["seed_url"] = seed

            seed_origin = f"{urlparse(seed).scheme}://{urlparse(seed).netloc}"

            frontier: List[str] = [seed]
            queued_set: Set[str] = {seed}

            while frontier and stats["fetched"] < max_pages:
                current = frontier.pop(0)
                if current in seen_urls:
                    stats["skipped_seen"] += 1
                    continue

                try:
                    jitter_sleep(delay_min, delay_max)
                    safe_goto(page, current)
                    assert_not_login_page(page, current)
                    final_url = normalize_url(page.url or current)

                    fetched_at_dt = datetime.now(timezone.utc)
                    save_path = deterministic_path_for_url(RAW_ROOT, final_url, fetched_at_dt)
                    html = page.content()
                    save_path.write_text(html, encoding="utf-8")

                    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
                    manifest.append(
                        {
                            "url": final_url,
                            "saved_path": str(save_path.relative_to(ROOT)).replace("\\", "/"),
                            "sha256": sha256,
                            "fetched_at": fetched_at_dt.isoformat(),
                            "status": "ok",
                        }
                    )

                    seen_urls.add(final_url)
                    seen_urls.add(current)
                    stats["fetched"] += 1

                    links = extract_links(page)
                    stats["discovered_links"] += len(links)
                    discovered_next: Set[str] = set()
                    discovered_threadish: Set[str] = set()
                    for item in links:
                        href = (item.get("href") or "").strip()
                        text = (item.get("text") or "").strip()
                        rel = (item.get("rel") or "").strip()
                        if not href:
                            continue
                        abs_url = normalize_url(urljoin(final_url, href))
                        if not allow_external and not same_origin(abs_url, seed_origin):
                            continue
                        if not maybe_filter_by_since_days(abs_url, args.since_days):
                            continue
                        if looks_like_pagination(abs_url, text, rel):
                            discovered_next.add(abs_url)
                        if looks_like_forum_or_thread(abs_url, text):
                            discovered_threadish.add(abs_url)

                    for nxt in sorted(discovered_next) + sorted(discovered_threadish):
                        if nxt in seen_urls or nxt in queued_set:
                            continue
                        frontier.append(nxt)
                        queued_set.add(nxt)
                        stats["queued"] += 1
                        if len(frontier) + stats["fetched"] >= max_pages * 5:
                            # Deterministic cap to avoid runaway queues.
                            break
                except Exception as e:  # noqa: BLE001
                    stats["failures"] += 1
                    failures.append({"url": current, "error": str(e).splitlines()[0]})
                    manifest.append(
                        {
                            "url": current,
                            "saved_path": "",
                            "sha256": "",
                            "fetched_at": utc_now_iso(),
                            "status": "failed",
                            "error": str(e).splitlines()[0],
                        }
                    )
                    seen_urls.add(current)
                    continue

            context.close()
            browser.close()
    except Exception as e:  # noqa: BLE001
        stats["failures"] += 1
        failures.append({"url": stats.get("seed_url", ""), "error": str(e).splitlines()[0]})

    # Persist outputs even on failure.
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_json(MANIFEST_PATH, manifest)
    save_json(SEEN_URLS_PATH, sorted(seen_urls))

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Forum Crawl Summary",
        "",
        f"- Started: {stats['started_at']}",
        f"- Seed URL: {stats.get('seed_url', '') or '(none)'}",
        f"- Max pages: {stats['max_pages']}",
        f"- Allow external: {stats['allow_external']}",
        f"- Fetched pages: {stats['fetched']}",
        f"- Skipped seen URLs: {stats['skipped_seen']}",
        f"- Queued URLs: {stats['queued']}",
        f"- Links discovered: {stats['discovered_links']}",
        f"- Failures: {stats['failures']}",
        "",
        f"- Manifest: `{MANIFEST_PATH.relative_to(ROOT)}`",
        f"- Seen URLs: `{SEEN_URLS_PATH.relative_to(ROOT)}`",
        "",
        "## Failures",
    ]
    if failures:
        for f in failures[:200]:
            lines.append(f"- {f.get('url','')}: {f.get('error','')}")
    else:
        lines.append("- None")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Summary: {SUMMARY_PATH}")
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"Seen URLs: {SEEN_URLS_PATH}")
    print(f"Fetched pages: {stats['fetched']}, Failures: {stats['failures']}")


if __name__ == "__main__":
    main()
