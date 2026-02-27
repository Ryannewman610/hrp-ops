"""Knowledge Sprint Crawler — Fetch race results, sire stats, workouts, and forum data.

Fetches:
  1. Race results for our horses (entries/results page)
  2. Sire stats for our sires (horse search / profile)
  3. Public workouts (recent 2yo workouts)
  4. Track stats (statistics page)
  5. Additional forum threads
"""

import json, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "inputs" / "export" / "auth.json"
OUT = ROOT / "inputs" / "knowledge_sprint"
OUT.mkdir(parents=True, exist_ok=True)


def fetch_and_save(page, url, filename, desc=""):
    """Fetch a page and save its text + HTML."""
    print(f"  [{desc or filename}] {url[:80]}...")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        html = page.content()
        
        # Save raw HTML
        (OUT / f"{filename}.html").write_text(html, encoding="utf-8")
        
        # Parse and save text
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        (OUT / f"{filename}.txt").write_text(text, encoding="utf-8")
        
        return text, soup
    except Exception as e:
        print(f"    ERROR: {e}")
        return "", None


def crawl_race_results(page):
    """Fetch race results for our horses."""
    print("\n=== 1. RACE RESULTS ===")
    
    # Get results for our stable
    stable_url = "https://www.horseracingpark.com/stats/results.aspx?stablename=Ire+Iron+Stables"
    text, soup = fetch_and_save(page, stable_url, "our_race_results", "Our race results")
    
    if soup:
        # Also try getting recent results across all tracks
        recent_url = "https://www.horseracingpark.com/stats/results.aspx"
        text2, soup2 = fetch_and_save(page, recent_url, "all_recent_results", "All recent results")
    
    # Get our horse-specific past performances
    horses_with_races = [
        "Core N Light", "Golden Shuvee", "Hardline Anvil", "Hydration",
        "Desert Oath", "Stormy Sky", "Damascus Honey"
    ]
    
    for horse in horses_with_races:
        url_name = horse.replace(" ", "+")
        # Fetch view 2 (detailed past performances)
        pp_url = f"https://www.horseracingpark.com/stables/viewhorse.aspx?horsename={url_name}&v=2"
        text, soup = fetch_and_save(page, pp_url, f"pp_{horse.replace(' ', '_')}", f"PP: {horse}")
        page.wait_for_timeout(1000)


def crawl_sire_stats(page):
    """Fetch sire/dam information and offspring stats."""
    print("\n=== 2. SIRE DATABASE ===")
    
    # Our sires
    sires = ["Comanche", "Neon Artist", "Neon Wolf", "Compress"]
    
    for sire in sires:
        url_name = sire.replace(" ", "+")
        
        # Try horse search for sire to find offspring
        search_url = f"https://www.horseracingpark.com/stables/horsesearch.aspx?horsename={url_name}&virginhorses=1&activehorses=1&retiredhorses=1&deactivatedhorses=1"
        text, soup = fetch_and_save(page, search_url, f"sire_search_{sire.replace(' ', '_')}", f"Search: {sire}")
        page.wait_for_timeout(1000)
        
        # Try the sire's own profile/stats
        profile_url = f"https://www.horseracingpark.com/stables/viewhorse.aspx?horsename={url_name}"
        text, soup = fetch_and_save(page, profile_url, f"sire_profile_{sire.replace(' ', '_')}", f"Profile: {sire}")
        page.wait_for_timeout(1000)
    
    # Also fetch SRF charts for sire data
    srf_url = "https://www.horseracingpark.com/stats/charts.aspx"
    text, soup = fetch_and_save(page, srf_url, "srf_charts", "SRF Charts")


def crawl_workouts(page):
    """Fetch public workout data for scouting."""
    print("\n=== 3. COMPETITOR SCOUTING (WORKOUTS) ===")
    
    # Public workouts page
    workouts_url = "https://www.horseracingpark.com/stats/workouts.aspx"
    text, soup = fetch_and_save(page, workouts_url, "public_workouts", "Public workouts")
    
    # Try to get workouts for specific tracks where 2yos would debut
    tracks = ["CT", "GP", "CD", "SA", "AQU", "BEL", "TAM"]
    for track in tracks:
        track_url = f"https://www.horseracingpark.com/stats/workouts.aspx?track={track}"
        text, soup = fetch_and_save(page, track_url, f"workouts_{track}", f"Workouts: {track}")
        page.wait_for_timeout(1000)


def crawl_track_stats(page):
    """Fetch track statistics for bias analysis."""
    print("\n=== 4. TRACK BIAS ANALYSIS ===")
    
    # Main statistics page
    stats_url = "https://www.horseracingpark.com/stats/index.aspx"
    text, soup = fetch_and_save(page, stats_url, "stats_index", "Stats index")
    
    # Try track-specific stats
    tracks = ["CT", "GP", "CD", "SA", "AQU", "BEL", "TAM", "KEE", "MNR", "GG"]
    for track in tracks:
        track_url = f"https://www.horseracingpark.com/stats/results.aspx?track={track}"
        text, soup = fetch_and_save(page, track_url, f"track_results_{track}", f"Track: {track}")
        page.wait_for_timeout(1000)
    
    # Owner stats page
    owner_url = "https://www.horseracingpark.com/stats/ownerstats.aspx"
    text, soup = fetch_and_save(page, owner_url, "owner_stats", "Owner stats")


def crawl_forums(page):
    """Crawl additional forum sections beyond Ask The Experts."""
    print("\n=== 5. ADDITIONAL FORUMS ===")
    
    # Forum index to discover all forum IDs
    forum_index_url = "https://www.horseracingpark.com/forums/index.aspx"
    text, soup = fetch_and_save(page, forum_index_url, "forum_index", "Forum index")
    
    if soup:
        # Find all forum links
        links = soup.find_all("a", href=True)
        forum_ids = set()
        for link in links:
            href = link.get("href", "")
            match = re.search(r"forumid=(\d+)", href, re.IGNORECASE)
            if match:
                fid = match.group(1)
                forum_ids.add(fid)
                label = link.get_text(strip=True)
                print(f"    Found forum: {fid} = {label}")
        
        # Crawl each forum (first 2 pages each, skip ForumID=1 which we already did)
        for fid in sorted(forum_ids):
            if fid == "1":
                print(f"    Skipping ForumID=1 (already crawled)")
                continue
            
            for pg in range(1, 3):
                url = f"https://www.horseracingpark.com/forums/forum.aspx?forumid={fid}&page={pg}"
                text, soup = fetch_and_save(page, url, f"forum_{fid}_p{pg}", f"Forum {fid} p{pg}")
                page.wait_for_timeout(1500)
                
                if not text or "No threads" in text:
                    break
            
            # Grab first 5 threads from each forum for depth
            if soup:
                thread_links = soup.find_all("a", href=re.compile(r"threadid=", re.I))
                for tlink in thread_links[:5]:
                    href = tlink.get("href", "")
                    tid_match = re.search(r"threadid=(\d+)", href)
                    if tid_match:
                        tid = tid_match.group(1)
                        t_url = f"https://www.horseracingpark.com/forums/thread.aspx?threadid={tid}"
                        text, _ = fetch_and_save(page, t_url, f"thread_{tid}", f"Thread {tid}")
                        page.wait_for_timeout(1000)


if __name__ == "__main__":
    print("=" * 60)
    print("KNOWLEDGE SPRINT CRAWLER")
    print("=" * 60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(AUTH)) if AUTH.exists() else browser.new_context()
        page = ctx.new_page()
        
        crawl_race_results(page)
        crawl_sire_stats(page)
        crawl_workouts(page)
        crawl_track_stats(page)
        crawl_forums(page)
        
        ctx.close()
        browser.close()
    
    # Count files downloaded
    files = list(OUT.glob("*.txt"))
    total_kb = sum(f.stat().st_size for f in files) / 1024
    print(f"\n{'=' * 60}")
    print(f"DONE: {len(files)} pages fetched, {total_kb:.0f} KB total")
    print(f"Saved to: {OUT}")
