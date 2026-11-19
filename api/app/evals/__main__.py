"""`python -m app.evals run {feasibility|isolation|grounding|all}` — prints a score card and saves the run."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.evals")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("suite", choices=["feasibility", "isolation", "grounding", "all"])
    run.add_argument("--results-dir", type=Path, default=None)
    args = p.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="support-desk-eval-"))
    log_path = tmp / "eval.log"
    from app.evals.runner import RESULTS_DIR, prepare_env
    prepare_env(tmp, log_path)

    from app import db as dbmod
    from app.config import get_settings
    from app.evals.result import score_card, write_result
    from app.evals.runner import suites
    dbmod.init_db()

    registry = suites()
    names = list(registry) if args.suite == "all" else [args.suite]
    missing = [n for n in names if n not in registry]
    if missing:
        print(f"suite not available yet: {', '.join(missing)}", file=sys.stderr)
        return 2
    ctx = {"tmp": tmp, "log_path": log_path}
    started = time.monotonic()
    results = []
    for name in names:
        db = dbmod.SessionLocal()
        try:
            out = registry[name](db, ctx)
            results.append(asyncio.run(out) if inspect.isawaitable(out) else out)
        finally:
            db.close()
    from app.evals.feasibility import intent_accuracy
    feas = next((r for r in results if r.name == "feasibility"), None)
    intent = intent_accuracy(feas) if feas else None
    meta = {"use_llm": get_settings().use_llm, "intent_accuracy": intent, "duration_s": round(time.monotonic() - started, 1),
            "commit": _commit(), "suites": names}
    path = write_result(args.results_dir or RESULTS_DIR, results, today=date.today(), meta=meta)
    print(score_card(results))
    if intent:
        print(f"intent accuracy  {intent[0]}/{intent[1]}")
    print(f"saved {path}")
    return 0 if all(s.passed == s.total for s in results) else 1


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
