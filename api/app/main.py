from __future__ import annotations

import logging
import threading

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db, init_db

log = logging.getLogger(__name__)


def _bootstrap_corpus() -> None:
    from app.corpus.refresh import refresh_corpus
    from app.corpus.status import corpus_status
    if corpus_status()["ready"]:
        return
    db = SessionLocal()
    try:
        refresh_corpus(db)
    except Exception:  # noqa: BLE001
        log.exception("initial corpus refresh failed")
    finally:
        db.close()


def _recover_runs() -> None:
    from app import db as dbmod
    from app.weekly.run import recover_interrupted_runs
    s = dbmod.SessionLocal()
    try:
        n = recover_interrupted_runs(s)
        if n:
            log.warning("marked %d interrupted weekly run(s) as failed", n)
    finally:
        s.close()


def _recover_tickets() -> None:
    from app import db as dbmod
    from app.tickets import worker
    s = dbmod.SessionLocal()
    try:
        ids = worker.recover(s)
        if ids:
            log.warning("re-queued %d ticket(s) left unprocessed by a restart", len(ids))
    finally:
        s.close()


def _e2e_seed() -> None:
    s = get_settings()
    if not s.e2e_seed:
        return
    if s.use_llm:
        log.warning("E2E_SEED ignored: it only runs with USE_LLM=0")
        return
    from app import db as dbmod
    from app.e2e_seed import seed

    def go():
        db = dbmod.SessionLocal()
        try:
            seed(db)
        finally:
            db.close()
    # uvicorn --factory calls create_app inside its event loop; the seed's asyncio.run needs its own thread
    t = threading.Thread(target=go)
    t.start()
    t.join()


def create_app(*, init_corpus: bool = True) -> FastAPI:
    from app.guard.logfilter import install_log_redaction
    install_log_redaction()
    app = FastAPI(title="Groww Support Desk API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    init_db()
    _recover_runs()
    _recover_tickets()
    _e2e_seed()

    from app.api.console import router as console_router
    from app.api.public import router as public_router
    app.include_router(public_router)
    app.include_router(console_router)

    @app.get("/health")
    def health(db: Session = Depends(get_db)):
        db.execute(text("select 1"))
        from app.corpus.status import corpus_status
        return {"db": "ok", "corpus": corpus_status()}

    if init_corpus:
        if get_settings().corpus_bootstrap:
            threading.Thread(target=_bootstrap_corpus, daemon=True).start()
        from app.scheduler import start_scheduler
        app.state.scheduler = start_scheduler()
    return app
