"""Throwaway eval environment + suite registry. `prepare_env` must run before any other `app.*` import,
because the database engine is created when `app.db` is first imported."""

from __future__ import annotations

import logging
import os
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = API_ROOT / "evals" / "results"
DATASETS_DIR = API_ROOT / "evals" / "datasets"


def prepare_env(tmp_dir: Path, log_path: Path) -> None:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "DATABASE_URL": f"sqlite:///{(tmp_dir / 'eval.db').as_posix()}",
        "TICKET_WORKER_INLINE": "1",
        "AUTO_APPROVE": "0",
        "SCHEDULER_ENABLED": "0",
        "CORPUS_BOOTSTRAP": "0",
        "DATA_OUTBOX_DIR": (tmp_dir / "outbox").as_posix(),
    })
    os.environ.setdefault("USE_LLM", "1")
    _file_log(log_path)


def _file_log(log_path: Path) -> None:
    """Everything the app logs during the run goes to this file, redacted exactly as in production."""
    from app.guard.logfilter import RedactingFilter, install_log_redaction
    install_log_redaction()
    h = logging.FileHandler(log_path, encoding="utf-8")
    h.setLevel(logging.INFO)
    h.addFilter(RedactingFilter())
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(h)
    logging.getLogger().setLevel(logging.INFO)


def suites() -> dict:
    """name -> callable(db, ctx) returning a SuiteResult (sync or async). Filled in as suites are built."""
    from app.evals.feasibility import run_feasibility
    from app.evals.grounding import run_grounding
    from app.evals.isolation import run_isolation
    reviews = API_ROOT / "tests" / "fixtures" / "reviews.json"
    reg: dict = {
        "feasibility": lambda db, ctx: run_feasibility(db, questions_path=DATASETS_DIR / "questions.yaml",
                                                       reviews_fixture=reviews),
        "isolation": lambda db, ctx: run_isolation(db),
        "grounding": lambda db, ctx: run_grounding(db, adversarial_path=DATASETS_DIR / "adversarial.yaml",
                                                   reviews_fixture=reviews, log_path=ctx["log_path"]),
    }
    return reg
