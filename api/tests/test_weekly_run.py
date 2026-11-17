import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.guard.scope import word_count
from app.models import Action, Explainer, Theme
from app.weekly.run import run_weekly

FIX = Path(__file__).parent / "fixtures"
RAW = json.loads((FIX / "reviews.json").read_text())
NOW = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    return db_session


def run(db, fetcher=lambda p, w, m: [dict(r) for r in RAW]):
    return asyncio.run(run_weekly(db, now=NOW, fetcher=fetcher))


def test_full_run_without_manual_steps(corpus):
    r = run(corpus)
    assert r.status == "awaiting_approval", r.error
    themes = corpus.query(Theme).filter_by(run_id=r.id).order_by(Theme.rank).all()
    assert 1 <= len(themes) <= 5 and all(t.review_ids and t.window_start and t.window_end for t in themes)
    assert all(t.window_start == r.window_start for t in themes)   # run states the window it covers
    assert word_count(r.pulse_text) <= 250
    ex = corpus.query(Explainer).filter_by(run_id=r.id).one()
    assert ex.status == "draft" and 1 <= len(ex.bullets) <= 6
    acts = corpus.query(Action).filter_by(source_ref=f"weekly_run:{r.id}").all()
    assert sorted(a.type for a in acts) == ["doc_append", "email_draft"] and all(a.status == "pending" for a in acts)
    assert all("Last checked:" in a.content for a in acts)


def test_fetch_failure_marks_failed_and_keeps_previous(corpus):
    first = run(corpus)

    def boom(p, w, m):
        raise RuntimeError("network down")
    second = run(corpus, fetcher=boom)
    assert second.status == "failed" and "network down" in second.error
    assert corpus.query(Action).filter_by(source_ref=f"weekly_run:{second.id}").count() == 0
    assert corpus.query(Theme).filter_by(run_id=first.id).count() >= 1


def test_zero_reviews_fails_cleanly(corpus):
    r = run(corpus, fetcher=lambda p, w, m: [])
    assert r.status == "failed" and "0 reviews" in r.error


def test_no_pii_in_run_outputs(corpus):
    r = run(corpus)
    blob = r.pulse_text + " ".join(a.content for a in corpus.query(Action))
    for raw in ("Real Person", "9876543210", "ABCDE1234F", "ravi.k@example.com"):
        assert raw not in blob


def test_doc_action_label_does_not_claim_a_doc_title(corpus):
    # The real Doc is titled differently from the hard-coded name the label used to show;
    # an approver must not be told a title we never read.
    r = run(corpus)
    doc = corpus.query(Action).filter_by(source_ref=f"weekly_run:{r.id}", type="doc_append").one()
    assert "'" not in doc.target_label and doc.target_label.startswith("Append to the weekly pulse Google Doc (")
