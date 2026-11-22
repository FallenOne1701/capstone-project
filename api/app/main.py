from __future__ import annotations

import logging
import threading
import time

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


def _warm_up(tries: int = 2) -> None:
    """Load the embedding model once at startup (~5 s locally, ~18 s on Railway) so the first question after a deploy
    isn't the one that waits. On Railway the first try once hit an ImportError while other startup threads were
    importing: try again after a short pause."""
    for attempt in range(1, tries + 1):
        try:
            from app.corpus import embedder
            embedder.get_embedding_service().embed_query("warm up")
            log.info("warm-up done (try %d)", attempt)
            return
        except Exception as exc:  # noqa: BLE001  (a failed warm-up only means the first question loads it)
            log.warning("warm-up try %d failed: %s: %s", attempt, type(exc).__name__, exc)
            if attempt < tries:
                time.sleep(3)


def create_app(*, init_corpus: bool = True) -> FastAPI:
    from app.guard.logfilter import install_log_redaction
    install_log_redaction()
    app = FastAPI(title="Groww Support Desk API")
    from app.config import cors_origin_list
    app.add_middleware(CORSMiddleware, allow_origins=cors_origin_list(get_settings().cors_origins),
                       allow_methods=["*"], allow_headers=["*"])
    init_db()
    _recover_runs()
    _recover_tickets()
    _e2e_seed()

    from app.api.console import router as console_router
    from app.api.desk import router as desk_router
    from app.api.public import router as public_router
    app.include_router(public_router)
    app.include_router(console_router)
    app.include_router(desk_router)

    @app.get("/health")
    def health(db: Session = Depends(get_db)):
        db.execute(text("select 1"))
        from app.corpus.status import corpus_status
        from app.delivery.mcp_client import google_status
        return {"db": "ok", "corpus": corpus_status(), "google": google_status()}

    if init_corpus:
        from app.corpus import embedder as _embedder  # noqa: F401  (import on the main thread, before startup threads)
        threading.Thread(target=lambda: _warm_up(), name="warm-up", daemon=True).start()
        if get_settings().corpus_bootstrap:
            threading.Thread(target=_bootstrap_corpus, daemon=True).start()
        from app.scheduler import start_scheduler
        app.state.scheduler = start_scheduler()
    return app
