from __future__ import annotations

import logging
import threading

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

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


def create_app(*, init_corpus: bool = True) -> FastAPI:
    from app.guard.logfilter import install_log_redaction
    install_log_redaction()
    app = FastAPI(title="Groww Support Desk API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    init_db()

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
        threading.Thread(target=_bootstrap_corpus, daemon=True).start()
    return app
