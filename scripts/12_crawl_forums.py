import argparse
import hashlib
import json
import random
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"
CONFIG_PATH = ROOT / "scripts" / "forum_urls.json"
DEFAULT_OUT_DIR = ROOT / "inputs" / "forums" / "raw" / "auto"
DEFAULT_SEED_URL = "https://www.horseracingpark.com/forums/index.aspx"


def normalize_url(url: str) -> str:
    p = urlparse(url)
    return p._replace(fragment="").geturl()


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
    expected = expected_url.lower()
    if "/login/" in current_url or "/login" in current_url:
        raise RuntimeError(
            f"Safety abort: redirected to login while loading {expected_url}. Current URL: {page.url}"
        )

    body_text = (page.inner_text("body") or "").lower()
    login_markers = ["log in", "login", "sign in", "username", "password"]
    marker_hits = sum(1 for marker in login_markers if marker in body_text)
    if marker_hits >= 3:
        raise RuntimeError(
            f"Safety abort: page content appears to be login while loading {expected_url}."
        )

    if "/forums/" in expected and "/stables/index.aspx" in current_url:
        raise RuntimeError(
            f"Safety abort: redirected to stable index while loading forum URL {expected_url}."
        )


def polite_delay_with_jitter(delay_seconds: float) -> None:
    wait = max(0.0, delay_seconds + random.uniform(-0.35, 0.35))
    print(f"Waiting {wait:.2f}s...")
    time.sleep(wait)


def load_config() -> Dict[str, List[str]]:
    if not CONFIG_PATH.exists():
        return {
            "forum_index_urls": [],
            "thread_url_allow": ["/forums/"],
            "thread_url_deny": ["login", "register", "reply", "quote", "print"],
        }
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "forum_index_urls": list(data.get("forum_index_urls", [])),
        "thread_url_allow": list(data.get("thread_url_allow", ["/forums/"])),
        "thread_url_deny": list(data.get("thread_url_deny", ["login", "register", "reply", "quote", "print"])),
    }


def extract_anchor_links(page) -> List[Dict[str, str]]:
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


def to_abs_url(base_url: str, href: str) -> str:
    return normalize_url(urljoin(base_url, href))


def is_same_origin(url: str, origin: str) -> bool:
    p = urlparse(url)
    o = urlparse(origin)
    return p.scheme.startswith("http") and p.netloc.lower() == o.netloc.lower()


def contains_any(text: str, parts: List[str]) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in parts)


def is_forum_listing_url(url: str) -> bool:
    low = url.lower()
    if "/forums/" not in low:
        return False
    if any(m in low for m in ["threadid=", "showthread", "/thread", "viewtopic", "topic=", "newthread"]):
        return False
    return any(m in low for m in ["forum", "forumid", "forum.aspx", "forumdisplay", "board", "index.aspx", "f="])


def is_thread_url(url: str) -> bool:
    low = url.lower()
    if "/forums/" not in low:
        return False
    if "newthread" in low:
        return False
    return any(m in low for m in ["threadid=", "showthread", "/thread", "viewtopic", "topic=", "t="])


def is_pagination_link(url: str, text: str, rel: str) -> bool:
    t = text.strip().lower()
    r = rel.strip().lower()
    if r == "next":
        return True
    if t in {"next", ">", ">>"}:
        return True
    if t.startswith("page"):
        return True
    if t.isdigit():
        return True
    low = url.lower()
    return any(k in low for k in ["page=", "p=", "start=", "offset=", "currentpage="])


def with_page_param(url: str, param: str, value: int) -> str:
    p = urlparse(url)
    qs = parse_qs(p.query)
    qs[param] = [str(value)]
    new_q = urlencode(qs, doseq=True)
    return normalize_url(urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, "")))


def infer_paged_urls(url: str, max_pages: int, for_thread: bool) -> List[str]:
    if max_pages <= 1:
        return [url]
    p = urlparse(url)
    qs = parse_qs(p.query)
    keys = ["CurrentPage", "page", "p", "start", "offset"]
    chosen = None
    for k in keys:
        if k in qs:
            chosen = k
            break
    if chosen is None:
        chosen = "CurrentPage" if "forum.aspx" in p.path.lower() or for_thread else "page"

    out = [url]
    for i in range(2, max_pages + 1):
        if chosen in {"start", "offset"}:
            out.append(with_page_param(url, chosen, i - 1))
        else:
            out.append(with_page_param(url, chosen, i))
    # deterministic dedupe
    dedup: List[str] = []
    seen: Set[str] = set()
    for u in out:
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    return dedup


def maybe_matches_since_days(url: str, since_days: Optional[int]) -> bool:
    if since_days is None:
        return True
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", url)
    if not m:
        return True
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).date()
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


def slug_from_url(url: str) -> str:
    p = urlparse(url)
    base = p.path.strip("/").replace("/", "_")
    if not base:
        base = "thread"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_")
    return base[:64] if base else "thread"


def load_manifest(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return d if isinstance(d, list) else []


def save_manifest(path: Path, items: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def discover_subforums(
    page,
    seed_url: str,
    origin: str,
    max_subforums: int,
) -> List[str]:
    safe_goto(page, seed_url)
    assert_not_login_page(page, seed_url)
    links = extract_anchor_links(page)
    out: Set[str] = set()
    for item in links:
        href = (item.get("href") or "").strip()
        if not href:
            continue
        abs_url = to_abs_url(page.url, href)
        if not is_same_origin(abs_url, origin):
            continue
        if is_forum_listing_url(abs_url):
            out.add(abs_url)
    return sorted(out)[:max_subforums]


def crawl_listing_pages_for_threads(
    page,
    subforum_url: str,
    origin: str,
    max_forum_pages: int,
    max_threads: int,
    thread_allow: List[str],
    thread_deny: List[str],
    delay_seconds: float,
    since_days: Optional[int],
) -> Tuple[List[str], List[str]]:
    queue: List[str] = infer_paged_urls(subforum_url, max_forum_pages, for_thread=False)
    visited_pages: Set[str] = set()
    queued: Set[str] = set(queue)
    thread_urls: Set[str] = set()
    visited_order: List[str] = []

    while queue and len(visited_pages) < max_forum_pages and len(thread_urls) < max_threads:
        current = queue.pop(0)
        if current in visited_pages:
            continue
        visited_pages.add(current)
        visited_order.append(current)

        polite_delay_with_jitter(delay_seconds)
        safe_goto(page, current)
        assert_not_login_page(page, current)

        links = extract_anchor_links(page)
        for item in links:
            href = (item.get("href") or "").strip()
            text = (item.get("text") or "").strip()
            rel = (item.get("rel") or "").strip()
            if not href:
                continue
            abs_url = to_abs_url(page.url, href)
            if not is_same_origin(abs_url, origin):
                continue
            low = abs_url.lower()
            if thread_deny and contains_any(low, thread_deny):
                continue

            if is_thread_url(abs_url):
                if thread_allow and not contains_any(low, thread_allow):
                    continue
                if not maybe_matches_since_days(abs_url, since_days):
                    continue
                thread_urls.add(abs_url)
                if len(thread_urls) >= max_threads:
                    break
                continue

            if is_forum_listing_url(abs_url) and is_pagination_link(abs_url, text, rel):
                if abs_url not in visited_pages and abs_url not in queued:
                    queue.append(abs_url)
                    queued.add(abs_url)

    return sorted(thread_urls), visited_order


def build_thread_page_candidates(
    thread_url: str,
    max_thread_pages: int,
) -> List[str]:
    if max_thread_pages == 0:
        return [thread_url]
    pages = max(1, max_thread_pages)
    return infer_paged_urls(thread_url, pages, for_thread=True)


def fetch_pages(
    page,
    urls: List[str],
    out_dir: Path,
    delay_seconds: float,
    resume: bool,
) -> Tuple[int, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "forum_manifest.json"
    manifest = load_manifest(manifest_path)
    existing = {m.get("url", "") for m in manifest}
    downloaded = 0
    skipped = 0

    for url in urls:
        if resume and url in existing:
            skipped += 1
            continue

        polite_delay_with_jitter(delay_seconds)
        safe_goto(page, url)
        assert_not_login_page(page, url)
        html = page.content()

        sha1_url = hashlib.sha1(url.encode("utf-8")).hexdigest()
        slug = slug_from_url(url)
        save_path = out_dir / f"{slug}__{sha1_url}.html"
        save_path.write_text(html, encoding="utf-8")
        sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()

        manifest.append(
            {
                "url": url,
                "saved_path": str(save_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        downloaded += 1
        existing.add(url)

    manifest_sorted = sorted(manifest, key=lambda x: x.get("url", ""))
    save_manifest(manifest_path, manifest_sorted)
    return downloaded, skipped


def run_forum_parse() -> None:
    subprocess.run(["py", "scripts/10_parse_forum_notes.py"], check=True, cwd=ROOT)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Deep crawl HRP forums with deterministic pagination.")
    ap.add_argument("--seed", default=DEFAULT_SEED_URL, help=f"Seed URL (default {DEFAULT_SEED_URL})")
    ap.add_argument("--list-only", action="store_true", help="Discover and print thread URLs only.")
    ap.add_argument("--max-subforums", type=int, default=8, help="Max subforums to crawl.")
    ap.add_argument("--max-forum-pages", type=int, default=5, help="Max listing pages per subforum.")
    ap.add_argument("--max-thread-pages", type=int, default=2, help="Max pages per thread; 0 means first page only.")
    ap.add_argument("--max-threads", type=int, default=200, help="Max threads to discover.")
    ap.add_argument("--delay-seconds", type=float, default=4.0, help="Base delay between requests with jitter.")
    ap.add_argument("--since-days", type=int, default=None, help="Optional best-effort date filter from URL patterns.")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for downloaded pages.")
    ap.add_argument("--parse", action="store_true", help="Run forum parser after crawl.")
    ap.add_argument("--allow-external", action="store_true", help="Allow non-origin URLs.")
    ap.add_argument("--resume", action="store_true", default=True, help="Skip already-downloaded URLs from manifest (default on).")
    ap.add_argument("--no-resume", action="store_true", help="Disable resume behavior and fetch all discovered URLs.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    seed = normalize_url(args.seed.strip() or DEFAULT_SEED_URL)
    if not args.seed.strip():
        cfg_seeds = cfg.get("forum_index_urls", [])
        if cfg_seeds:
            seed = normalize_url(cfg_seeds[0])

    origin = f"{urlparse(seed).scheme}://{urlparse(seed).netloc}"
    use_resume = bool(args.resume and not args.no_resume)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        if AUTH_PATH.exists():
            context = browser.new_context(storage_state=str(AUTH_PATH))
        else:
            print(f"WARN: auth state not found at {AUTH_PATH}; continuing without storage_state.")
            context = browser.new_context()
        page = context.new_page()

        try:
            subforums = discover_subforums(
                page=page,
                seed_url=seed,
                origin=origin,
                max_subforums=max(1, args.max_subforums),
            )
            print(f"Discovered subforums: {len(subforums)}")
            for s in subforums:
                print(f"SUBFORUM {s}")

            all_threads: Set[str] = set()
            for subforum in subforums:
                if len(all_threads) >= max(1, args.max_threads):
                    break
                threads, visited_pages = crawl_listing_pages_for_threads(
                    page=page,
                    subforum_url=subforum,
                    origin=origin,
                    max_forum_pages=max(1, args.max_forum_pages),
                    max_threads=max(1, args.max_threads) - len(all_threads),
                    thread_allow=cfg.get("thread_url_allow", ["/forums/"]),
                    thread_deny=cfg.get("thread_url_deny", ["login", "register", "reply", "quote", "print"]),
                    delay_seconds=max(0.0, args.delay_seconds),
                    since_days=args.since_days,
                )
                print(f"Listing pages visited for subforum: {len(visited_pages)}")
                for t in threads:
                    all_threads.add(t)
                    if len(all_threads) >= max(1, args.max_threads):
                        break

            thread_urls = sorted(all_threads)[: max(1, args.max_threads)]
            print(f"Discovered thread URLs: {len(thread_urls)}")
            for u in thread_urls:
                print(u)

            if args.list_only:
                return

            # Expand into page URLs for each thread.
            page_urls: List[str] = []
            seen_page_urls: Set[str] = set()
            for t in thread_urls:
                for pu in build_thread_page_candidates(t, args.max_thread_pages):
                    if not args.allow_external and not is_same_origin(pu, origin):
                        continue
                    if pu in seen_page_urls:
                        continue
                    seen_page_urls.add(pu)
                    page_urls.append(pu)

            downloaded, skipped = fetch_pages(
                page=page,
                urls=page_urls,
                out_dir=out_dir,
                delay_seconds=max(0.0, args.delay_seconds),
                resume=use_resume,
            )
            print(f"Downloaded new pages: {downloaded}")
            print(f"Skipped existing pages: {skipped}")
            print(f"Manifest: {out_dir / 'forum_manifest.json'}")

            if args.parse:
                run_forum_parse()
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
