import os
os.environ["USE_LLM"] = "0"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CONSOLE_PASSWORD"] = "test-pass"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app import db as dbmod


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
