"""Start the judging demo on any OS (works in Windows PowerShell, no make needed).

    python run_demo.py            # port from $PORT, else 8501
    PORT=8600 python run_demo.py

Loads .env first (SEND_BACKEND, NTFY_TOPIC, PORT, DUBHACKS_DB). Variables already set in the
shell win over .env. DUBHACKS_DB defaults to vendor/dubhacks/data/sandbox.db.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        print("python-dotenv is missing: run  pip install -r requirements.txt", file=sys.stderr)
    os.environ.setdefault("DUBHACKS_DB", str(ROOT / "vendor" / "dubhacks" / "data" / "sandbox.db"))
    if not Path(os.environ["DUBHACKS_DB"]).exists():
        print(
            "Judge sandbox not found. Run once:  git clone --depth 1 "
            "https://github.com/mageshkumarj/dubhacks vendor/dubhacks",
            file=sys.stderr,
        )
        return 1
    port = os.environ.get("PORT", "").strip() or "8501"
    cmd = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "demo_app.py"),
           "--server.port", port, "--server.headless", "true"]
    print(f"Opening http://localhost:{port}")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
