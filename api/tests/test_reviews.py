import json
from datetime import date
from pathlib import Path

import pytest

from app.guard.pii import find_pii
from app.models import Review
from app.weekly.reviews import ingest_reviews, review_id, scrub

RAW = json.loads((Path(__file__).parent / "fixtures" / "reviews.json").read_text())


def fake_fetcher(package, weeks, max_reviews):
    return [dict(r) for r in RAW][:max_reviews]


def test_scrub_drops_identity_and_redacts_text():
    out = scrub(RAW[3])
    assert set(out) == {"id", "rating", "date", "text_redacted", "app_version"}
    assert "9876543210" not in out["text_redacted"] and "ravi" not in out["text_redacted"]
    assert out["id"] == review_id("gp:raw-003") and out["id"].startswith("rv_")


def test_review_ids_never_look_like_pii():
    ids = [review_id(f"gp:raw-{i}") for i in range(2000)]
    assert len(set(ids)) == 2000 and not any(find_pii(i) for i in ids)


def test_ingest_window_and_no_pii(db_session):
    res = ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=fake_fetcher)
    rows = db_session.query(Review).all()
    assert res.window_start == min(r.date for r in rows) >= date(2026, 9, 22)   # actual coverage
    assert res.window_end == date(2026, 11, 17)
    assert 0 < len(rows) == res.stored <= 40
    assert all(res.window_start <= r.date <= res.window_end for r in rows)
    blob = " ".join(f"{r.id} {r.text_redacted} {r.app_version}" for r in rows)
    for raw in ("Real Person", "9876543210", "ABCDE1234F", "ravi.k@example.com", "gp:raw"):
        assert raw not in blob


def test_ingest_is_idempotent(db_session):
    ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=fake_fetcher)
    n = db_session.query(Review).count()
    ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=fake_fetcher)
    assert db_session.query(Review).count() == n


def test_zero_reviews_raises(db_session):
    with pytest.raises(RuntimeError):
        ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=lambda p, w, m: [])
