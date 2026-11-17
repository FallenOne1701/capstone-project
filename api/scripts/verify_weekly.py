"""Write a manual verification page for a weekly run. Read-only.

Usage: python scripts/verify_weekly.py [--run-id N] [--log path/to/server.log ...]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import API_ROOT  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.weekly.verify import build_report  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--run-id", type=int, default=None)
p.add_argument("--log", action="append", default=[], help="log file(s) to sweep for PII")
a = p.parse_args()
db = SessionLocal()
rep = build_report(db, a.run_id, log_paths=[Path(x) for x in a.log])
out = API_ROOT / "data" / "verify" / f"weekly-run-{rep.run_id}.md"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(rep.markdown, encoding="utf-8")
print(f"wrote {out} — {len(rep.flags)} flag(s)")
for f in rep.flags:
    print("  FLAG", f)
