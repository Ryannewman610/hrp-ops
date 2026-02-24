"""07_write_run_status.py — Write a status file after each pipeline run.

Produces outputs/last_run_status.json with:
  - success/fail
  - timestamp
  - horses exported
  - errors list
  - reports generated
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "outputs" / "last_run_status.json"
MANIFEST_PATH = ROOT / "inputs" / "export" / "export_manifest.json"
REPORTS_DIR = ROOT / "reports"


def main() -> None:
    status_code = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    phase = sys.argv[2] if len(sys.argv) > 2 else "unknown"

    status: dict = {
        "timestamp": datetime.now().isoformat(),
        "success": status_code == 0,
        "exit_code": status_code,
        "failed_phase": phase if status_code != 0 else None,
        "horses_exported": 0,
        "pages_exported": 0,
        "global_pages": [],
        "errors": [],
        "reports_generated": [],
    }

    # Read manifest if it exists
    if MANIFEST_PATH.exists():
        try:
            m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            status["horses_exported"] = len(m.get("horses", []))
            status["pages_exported"] = m.get("pages_exported", 0)
            status["export_status"] = m.get("status", "unknown")
            status["mode"] = m.get("mode", "unknown")
            gp = m.get("global_pages", {})
            status["global_pages"] = gp.get("saved", [])
            if gp.get("failed"):
                status["errors"].append(f"Global page failures: {gp['failed']}")
            # Collect horse-level failures
            for h in m.get("horses", []):
                if h.get("failed_pages"):
                    status["errors"].append(
                        f"{h['horse_name']}: {list(h['failed_pages'].keys())}"
                    )
        except Exception as e:
            status["errors"].append(f"Could not read manifest: {e}")

    # Check which reports exist
    for report_name in ["Stable_Dashboard.md", "Weekly_Plan.md", "Decisions_Log.md"]:
        rp = REPORTS_DIR / report_name
        if rp.exists():
            status["reports_generated"].append(report_name)

    # Check for snapshot
    from datetime import date
    snap_path = ROOT / "inputs" / date.today().isoformat() / "stable_snapshot.json"
    if snap_path.exists():
        try:
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            status["snapshot_horses"] = len(snap.get("horses", []))
            status["balance"] = snap.get("balance")
        except Exception:
            pass

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"Status written: {STATUS_PATH}")
    print(f"  Success: {status['success']}")
    print(f"  Horses: {status['horses_exported']}")
    print(f"  Pages: {status['pages_exported']}")
    print(f"  Errors: {len(status['errors'])}")


if __name__ == "__main__":
    main()
