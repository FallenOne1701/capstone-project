from pathlib import Path

from app.corpus import refresh as rf
from app.models import Source

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


def _settings(tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "data_raw_dir", tmp_path / "raw")
    monkeypatch.setattr(s, "data_processed_dir", tmp_path / "processed")
    monkeypatch.setattr(s, "data_index_dir", tmp_path / "index")
    return s


def test_refresh_from_fixtures_creates_sources(db_session, tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    res = rf.refresh_corpus(db_session, fetch=False, raw_dir=FIXTURES)
    assert res.ok == 15 and res.reindexed
    rows = db_session.query(Source).all()
    assert len(rows) == 15 and all(r.status == "ok" and r.fetched_at for r in rows)


def test_fetch_failure_marks_stale_and_keeps_date(db_session, tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    rf.refresh_corpus(db_session, fetch=False, raw_dir=FIXTURES)
    before = {r.url: r.fetched_at for r in db_session.query(Source)}

    def failing_fetch(**kwargs):
        from app.corpus.fetcher import FetchReport, FetchResult
        return FetchReport(fetched_at="now", raw_dir="x", expected_scheme_count=len(kwargs["schemes"]),
                           results=[FetchResult(scheme_id=s["scheme_id"], scheme_name=s["scheme_name"],
                                                source_url=s["url"], status="error", error="timeout")
                                    for s in kwargs["schemes"]])
    monkeypatch.setattr(rf, "fetch_scheme_pages", failing_fetch)
    res = rf.refresh_corpus(db_session, fetch=True, raw_dir=FIXTURES)
    assert res.stale == 15
    for r in db_session.query(Source):
        assert r.status == "stale" and r.fetched_at == before[r.url]


def test_status_reports_vectors_after_refresh(db_session, tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    rf.refresh_corpus(db_session, fetch=False, raw_dir=FIXTURES)
    from app.corpus.status import corpus_status
    st = corpus_status()
    assert st["ready"] and st["vectors"] > 0
