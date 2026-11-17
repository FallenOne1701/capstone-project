"""Regressions found in the Task 13 live run (real Play Store data)."""

import asyncio
from datetime import date, datetime, timedelta

from app.models import Review
from app.weekly.pulse import select_quotes
from app.weekly.reviews import ingest_reviews
from app.weekly.themes import ThemeOut, assign_themes, build_themes


def rid(i):
    return "rv_" + "".join("abcdefghij"[int(c)] for c in f"{i:010d}")


def test_window_is_actual_coverage_when_cap_hit(db_session):
    """3000-review cap covered ~10 days; the stated window must not claim 8 weeks."""
    base = datetime(2026, 11, 16, 12)
    raws = [{"reviewId": f"gp:{i}", "content": "app crash after update", "score": 1,
             "at": base - timedelta(days=i % 3), "appVersion": "1"} for i in range(30)]
    res = ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=lambda p, w, m: raws)
    assert res.window_start == date(2026, 11, 14) and res.window_end == date(2026, 11, 17)


def test_reviews_without_any_signal_are_unthemed():
    revs = [Review(id=rid(1), rating=5, date=date(2026, 11, 15), text_redacted="good app"),
            Review(id=rid(2), rating=1, date=date(2026, 11, 15), text_redacted="app crashes after update")]
    assign, _ = asyncio.run(assign_themes(revs))
    assert assign == {rid(2): "app_reliability"}
    themes = build_themes(assign, revs, window_start=date(2026, 11, 1), window_end=date(2026, 11, 17),
                          today=date(2026, 11, 17))
    assert sum(t.count for t in themes) == 1


def test_quote_prefers_review_that_matches_its_theme():
    revs = {r.id: r for r in [
        Review(id=rid(1), rating=1, date=date(2026, 11, 16), text_redacted="Angel one is good app worst"),
        Review(id=rid(2), rating=1, date=date(2026, 11, 10),
               text_redacted="App crashes after the latest update and the screen freezes on loading"),
    ]}
    t = ThemeOut("app_reliability", "App reliability & updates", 2, 2, [rid(1), rid(2)],
                 date(2026, 11, 1), date(2026, 11, 17), 1)
    assert select_quotes([t], revs)[0].review_id == rid(2)
