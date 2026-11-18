"""Seed data for the Playwright stack: one offline weekly run and the source registry (Plan 3 Task 10)."""

from pathlib import Path

import pytest

from app import e2e_seed, main
from app.config import get_settings
from app.models import Action, Source, WeeklyRun

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    db_session.query(Source).delete()   # the e2e DB starts with no source rows
    db_session.commit()
    return db_session


def test_e2e_seed_creates_run_and_sources(corpus):
    e2e_seed.seed(corpus)
    run = corpus.query(WeeklyRun).one()
    assert run.status == "awaiting_approval", run.error
    acts = corpus.query(Action).filter_by(source_ref=f"weekly_run:{run.id}").all()
    assert sorted(a.type for a in acts) == ["doc_append", "email_draft"]
    assert all(a.status == "pending" for a in acts)
    assert corpus.query(Source).count() >= 15


def test_e2e_seed_is_idempotent(corpus):
    e2e_seed.seed(corpus)
    n_sources = corpus.query(Source).count()
    e2e_seed.seed(corpus)
    assert corpus.query(WeeklyRun).count() == 1
    assert corpus.query(Source).count() == n_sources


def test_e2e_seed_requires_offline_mode(corpus, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "e2e_seed", True)
    monkeypatch.setattr(s, "use_llm", True)
    main.create_app(init_corpus=False)
    assert corpus.query(WeeklyRun).count() == 0


def test_e2e_seed_runs_at_startup_when_offline(corpus, monkeypatch):
    monkeypatch.setattr(get_settings(), "e2e_seed", True)
    main.create_app(init_corpus=False)
    corpus.expire_all()
    assert corpus.query(WeeklyRun).count() == 1


def test_seed_never_downloads(corpus, monkeypatch):
    import app.corpus.reference as ref
    import app.weekly.reviews as rv
    monkeypatch.setattr(ref, "_download", lambda url: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(rv, "play_store_fetcher", lambda *a: (_ for _ in ()).throw(AssertionError("network")))
    e2e_seed.seed(corpus)
    assert corpus.query(WeeklyRun).one().status == "awaiting_approval"
