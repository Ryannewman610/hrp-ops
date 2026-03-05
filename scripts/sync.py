"""sync.py — One-click: login → export → analyze → push to cloud.

Runs the full HRP data pipeline and pushes fresh data to the Railway dashboard.
Uses saved session cookies for auto-login (no manual intervention needed).

Usage:
    python scripts/sync.py                    # full sync + push to cloud
    python scripts/sync.py --local            # sync locally only, no cloud push
    python scripts/sync.py --push-only        # skip export, just push existing data

Environment variables:
    CLOUD_URL  — Dashboard URL (default: https://web-production-6b5e6.up.railway.app)
    API_KEY    — Must match the API_KEY set on the cloud server
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

CLOUD_URL = os.environ.get("CLOUD_URL", "https://web-production-6b5e6.up.railway.app")
API_KEY = os.environ.get("API_KEY", "hrp-sync-2026")


def run_step(label: str, cmd: list[str], timeout: int = 300) -> bool:
    """Run a pipeline step. Returns True on success."""
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    result = subprocess.run(cmd, cwd=str(ROOT), timeout=timeout)
    if result.returncode != 0:
        print(f"  ❌ Failed (exit code {result.returncode})")
        return False
    print(f"  ✅ Done")
    return True


def main():
    push_only = "--push-only" in sys.argv
    local_only = "--local" in sys.argv

    if not push_only:
        # Step 1: Login (auto-reuses saved session)
        if not run_step("Logging into HRP...",
                        [PYTHON, str(ROOT / "scripts" / "01_login_save_state.py")],
                        timeout=120):
            print("\n❌ Login failed. Run with --force to re-login manually.")
            sys.exit(1)

        # Step 2: Export fresh data from HRP
        mode = "weekly" if "--weekly" in sys.argv else "daily"
        if not run_step(f"Exporting stable data from HRP ({mode})...",
                        [PYTHON, str(ROOT / "scripts" / "02_export_stable.py"), "--mode", mode],
                        timeout=1200):
            print("\n❌ Export failed.")
            sys.exit(1)

        # Step 3: Build snapshot
        snapshot_script = ROOT / "scripts" / "05_build_stable_snapshot.py"
        if not snapshot_script.exists():
            snapshot_script = ROOT / "scripts" / "03_build_snapshot.py"
        if snapshot_script.exists():
            run_step("Building stable snapshot...",
                     [PYTHON, str(snapshot_script)], timeout=120)

        # Step 4: Analysis pipeline
        analysis_scripts = [
            ("Building model dataset...", "scripts/09_build_model_dataset.py"),
            ("Fitting Trainer Brain...", "scripts/10_fit_trainer_brain.py"),
            ("Running deep analysis...", "scripts/deep_analysis.py"),
            ("Auditing stable...", "scripts/stable_audit.py"),
            ("Generating daily decisions...", "scripts/daily_decisions.py"),
            ("Building playbook...", "scripts/playbook_engine.py"),
            ("Generating recommendations...", "scripts/recommend_actions.py"),
        ]
        for label, script in analysis_scripts:
            script_path = ROOT / script
            if script_path.exists():
                run_step(label, [PYTHON, str(script_path)], timeout=120)

    # Step 5: Push to cloud
    if not local_only:
        print(f"\n{'='*50}")
        print(f"  Pushing to cloud: {CLOUD_URL}")
        print(f"{'='*50}")
        env = os.environ.copy()
        env["CLOUD_URL"] = CLOUD_URL
        env["API_KEY"] = API_KEY
        result = subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "push_to_cloud.py")],
            cwd=str(ROOT), env=env, timeout=60
        )
        if result.returncode != 0:
            print("\n❌ Cloud push failed.")
            sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  🎉 Sync complete!")
    if not local_only:
        print(f"  Live site: {CLOUD_URL}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
