import os
os.environ["USE_LLM"] = "0"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CONSOLE_PASSWORD"] = "test-pass"
os.environ["TICKET_WORKER_INLINE"] = "1"
os.environ["AUTO_APPROVE"] = "0"   # Plan 1-3 tests keep pending actions; Plan 3b tests turn it on

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app import db as dbmod


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    from app.guard.ratelimit import reset_limits
    from app.intent.cache import intent_cache
    reset_limits()
    intent_cache.clear()   # a classification cached by one test must never answer another test's faked AI
    yield


@pytest.fixture()
def db_session(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    dbmod.init_db()
    s = dbmod.SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def client(db_session):
    from app.main import create_app
    app = create_app(init_corpus=False)
    app.dependency_overrides[dbmod.get_db] = lambda: db_session
    return TestClient(app)
