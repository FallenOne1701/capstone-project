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


LOCAL_APP_DB = API_ROOT / "data" / "app.db"


def copy_sources(db, from_db: Path) -> int:
    """Copy the page records (with their real fetch dates) from the local app database, as the live site has them;
    "Last checked" dates for the fee explainer come from here. Returns rows copied."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Source
    if not Path(from_db).exists():
        return 0
    src = sessionmaker(bind=create_engine(f"sqlite:///{Path(from_db).as_posix()}"))()
    try:
        cols = [c.name for c in Source.__table__.columns if c.name != "id"]
        n = 0
        for row in src.query(Source).all():
            if db.query(Source).filter_by(url=row.url).first() is None:
                db.add(Source(**{c: getattr(row, c) for c in cols}))
                n += 1
        db.commit()
        return n
    finally:
        src.close()


def run_isolation_apart(tmp_dir: Path):
    """Isolation seeds and approves its own fake rows (incl. a canonical explainer), so it gets its own database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import models  # noqa: F401
    from app.db import Base
    from app.evals.isolation import run_isolation
    engine = create_engine(f"sqlite:///{(Path(tmp_dir) / 'isolation.db').as_posix()}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        return run_isolation(db)
    finally:
        db.close()
        engine.dispose()


def suites() -> dict:
    """name -> callable(db, ctx) returning a SuiteResult (sync or async). Filled in as suites are built."""
    from app.evals.feasibility import run_feasibility
    from app.evals.grounding import run_grounding
    reviews = API_ROOT / "tests" / "fixtures" / "reviews.json"
    reg: dict = {
        "feasibility": lambda db, ctx: run_feasibility(db, questions_path=DATASETS_DIR / "questions.yaml",
                                                       reviews_fixture=reviews),
        "isolation": lambda db, ctx: run_isolation_apart(ctx["tmp"]),
        "grounding": lambda db, ctx: run_grounding(db, adversarial_path=DATASETS_DIR / "adversarial.yaml",
                                                   reviews_fixture=reviews, log_path=ctx["log_path"]),
    }
    return reg
