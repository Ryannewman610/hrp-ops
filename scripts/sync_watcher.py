"""sync_watcher.py — Background daemon that polls the cloud for sync requests.

When you hit Sync on the Railway dashboard, it queues a request.
This script polls for that request every 30s and runs the full pipeline.

Usage:
    python scripts/sync_watcher.py           # run in foreground
    pythonw scripts/sync_watcher.py          # run silently in background

Runs indefinitely until killed (Ctrl+C).
"""

import os
import subprocess
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable

CLOUD_URL = os.environ.get("CLOUD_URL", "https://web-production-6b5e6.up.railway.app")
API_KEY = os.environ.get("API_KEY", "hrp-sync-2026")
POLL_INTERVAL = 30  # seconds


def check_for_sync_request():
    """Check if the cloud has a pending sync request."""
    try:
        resp = requests.get(
            f"{CLOUD_URL}/api/sync-request",
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
        data = resp.json()
        return data.get("pending", False)
    except Exception as e:
        print(f"  ⚠️ Poll failed: {e}")
        return False


def run_sync():
    """Run the full sync pipeline (uses sync.py which handles everything)."""
    print(f"\n{'='*50}")
    print(f"  🚀 Remote sync request detected! Running full pipeline...")
    print(f"{'='*50}")

    result = subprocess.run(
        [PYTHON, os.path.join(ROOT, "scripts", "sync.py")],
        cwd=ROOT,
    )

    if result.returncode == 0:
        print(f"\n  ✅ Sync complete! Cloud dashboard updated.")
    else:
        print(f"\n  ❌ Sync failed (exit code {result.returncode})")

    return result.returncode == 0


def main():
    print(f"{'='*50}")
    print(f"  🔄 HRP Sync Watcher — monitoring for remote requests")
    print(f"  Cloud: {CLOUD_URL}")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*50}")

    while True:
        try:
            if check_for_sync_request():
                run_sync()
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\n\n  👋 Sync watcher stopped.")
            break
        except Exception as e:
            print(f"  ⚠️ Error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
