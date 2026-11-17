from datetime import date

from app.models import Explainer, Review, Theme, WeeklyRun


def test_weekly_tables_roundtrip(db_session):
    run = WeeklyRun(status="running", window_start=date(2026, 9, 22), window_end=date(2026, 11, 16), review_count=0)
    db_session.add(run); db_session.flush()
    db_session.add(Review(id="rv_abcdefghij", rating=1, date=date(2026, 11, 16), text_redacted="app crash"))
    db_session.add(Theme(run_id=run.id, theme_id="app_reliability", label="App reliability & updates", count=1,
                         recent_count=1, review_ids=["rv_abcdefghij"], window_start=run.window_start,
                         window_end=run.window_end, rank=1))
    db_session.add(Explainer(run_id=run.id, topic="exit_load", title="Exit load explained",
                             bullets=[{"text": "x", "url": "https://groww.in/a"}], last_checked="2026-11-17",
                             status="draft", evidence={"reviews": 0, "tickets": 0}))
    db_session.commit()
    t = db_session.query(Theme).one()
    assert t.review_ids == ["rv_abcdefghij"] and db_session.query(Explainer).one().status == "draft"


def test_settings_have_weekly_fields():
    from app.config import get_settings
    s = get_settings()
    assert s.reviews_weeks == 8 and s.reviews_max == 3000 and s.repeat_threshold == 5 and s.repeat_days == 7
    assert s.play_package == "com.nextbillion.groww"
