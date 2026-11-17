import asyncio
from datetime import datetime, timedelta, timezone

from app.intent.classifier import classify_intent
from app.link.question_keys import label_for, question_key, repeated_questions
from app.models import Ticket
from app.weekly.fee_topics import topic_of

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def qk(text):
    return question_key(asyncio.run(classify_intent(text)), text)


def test_keys():
    assert qk("What is the exit load of HDFC Mid Cap?") == "fee_question:exit_load:hdfc-mid-cap-fund-direct-growth"
    assert qk("why was exit load deducted?") == "fee_question:exit_load"
    assert qk("brokerage charges on groww") == "fee_question:brokerage"
    assert qk("weather today") == "out_of_scope:general"


def test_topic_of():
    assert topic_of("expense ratio confusion") == "expense_ratio"
    assert topic_of("charged when I redeemed my fund") == "redemption_charges"
    assert topic_of("hello") is None


def _ticket(db, i, key, age):
    db.add(Ticket(code=f"GRW-T{i:05d}", question_redacted="q", question_key=key, created_at=NOW - age))


def test_repeated_threshold_and_window(db_session):
    k1, k2 = "fee_question:exit_load", "fee_question:brokerage"
    for i in range(5):
        _ticket(db_session, i, k1, timedelta(days=i))
    _ticket(db_session, 10, k1, timedelta(days=7, seconds=1))
    for i in range(4):
        _ticket(db_session, 20 + i, k2, timedelta(hours=i))
    db_session.commit()
    rep = repeated_questions(db_session, now=NOW, threshold=5, days=7)
    assert [r.key for r in rep] == [k1] and rep[0].count == 5
    assert rep[0].window_start.isoformat() == "2026-11-10" and rep[0].window_end.isoformat() == "2026-11-17"
    assert len(rep[0].ticket_codes) == 5


def test_boundary_exactly_seven_days_is_inside(db_session):
    for i in range(4):
        _ticket(db_session, i, "k", timedelta(days=1))
    _ticket(db_session, 9, "k", timedelta(days=7))
    db_session.commit()
    assert repeated_questions(db_session, now=NOW, threshold=5, days=7)[0].count == 5


def test_create_ticket_sets_key(db_session):
    from app.tickets.service import create_ticket
    t, _ = asyncio.run(create_ticket(db_session, "What is the exit load of HDFC Mid Cap?"))
    assert t.question_key == "fee_question:exit_load:hdfc-mid-cap-fund-direct-growth"


def test_label():
    assert label_for("fee_question:exit_load:hdfc-mid-cap-fund-direct-growth") == \
        "Fee question · Exit load · HDFC Mid Cap Fund Direct Growth"
