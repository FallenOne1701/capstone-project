from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db, init_db


def create_app(*, init_corpus: bool = True) -> FastAPI:
    app = FastAPI(title="Groww Support Desk API")
    init_db()

    @app.get("/health")
    def health(db: Session = Depends(get_db)):
        db.execute(text("select 1"))
        from app.corpus.status import corpus_status  # replaced in Task 7
        return {"db": "ok", "corpus": corpus_status()}

    return app
