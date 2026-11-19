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
    smp = sub.add_parser("samples", help="write the README samples (reviews CSV + Q&As) from a result file")
    smp.add_argument("--result", type=Path, required=True)
    smp.add_argument("--out", type=Path, required=True)
    smp.add_argument("--reviews", type=int, default=20)
    args = p.parse_args(argv)
    if args.cmd == "samples":
        return _samples(args)

    tmp = Path(tempfile.mkdtemp(prefix="support-desk-eval-"))
    log_path = tmp / "eval.log"
    from app.evals.runner import RESULTS_DIR, prepare_env
    prepare_env(tmp, log_path)

    from app import db as dbmod
    from app.config import get_settings
    from app.evals.result import score_card, write_result
    from app.evals.runner import suites
    dbmod.init_db()
    from app.evals.runner import LOCAL_APP_DB, copy_sources
    seed = dbmod.SessionLocal()
    try:
        print(f"copied {copy_sources(seed, LOCAL_APP_DB)} source records from {LOCAL_APP_DB.name}")
    finally:
        seed.close()

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


def _samples(args) -> int:
    """Reviews: the newest public Play Store reviews, scrubbed exactly as the weekly loop stores them."""
    import json

    from app.config import get_settings
    from app.evals.samples import pick_qas, reviews_csv
    from app.weekly.reviews import play_store_fetcher, scrub
    args.out.mkdir(parents=True, exist_ok=True)
    s = get_settings()
    try:
        raws = play_store_fetcher(s.play_package, 1, args.reviews * 3)
        source = "Google Play (public reviews, newest first)"
    except Exception as exc:  # noqa: BLE001
        print(f"live fetch failed ({type(exc).__name__}); using the test fixture")
        raws = json.loads((Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "reviews.json").read_text())
        source = "test fixture"
    scrubbed = [r for r in (scrub(x) for x in raws) if r]
    wordy = [r for r in scrubbed if len(r["text_redacted"].split()) >= 6]   # "nice" says little in a sample
    rows = (wordy + [r for r in scrubbed if r not in wordy])[: args.reviews]
    (args.out / "reviews_sample.csv").write_text(reviews_csv(rows), encoding="utf-8")
    result = json.loads(args.result.read_text(encoding="utf-8"))
    qas = pick_qas(result, n=5)
    lines = [f"# Sample Q&As", "", f"Taken from eval `{args.result.name}` (real AI). On the live site each answer waits "
             "for a person to approve it before the asker sees it.", ""]
    for i, q in enumerate(qas, 1):
        lines += [f"## {i}. {q['question']}", "", q["answer"], ""]
    (args.out / "sample_qa.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {len(rows)} reviews ({source}) and {len(qas)} Q&As to {args.out}")
    return 0


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
