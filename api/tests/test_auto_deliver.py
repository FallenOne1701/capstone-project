"""Weekly delivery runs itself and retries failed Google writes hourly, at most 6 times (Plan 3b Task 2)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.approvals import auto
from app.approvals.executors import EXECUTORS
from app.config import get_settings
from app.models import Action, AuditLog, Draft, Explainer, Ticket, WeeklyRun

FIX = Path(__file__).parent / "fixtures"
RAW = json.loads((FIX / "reviews.json").read_text())
NOW = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    monkeypatch.setattr(s, "auto_approve", True)
    monkeypatch.setattr(s, "pulse_doc_id", "DOC123")
    monkeypatch.setattr(s, "pulse_draft_recipient", "team@example.com")
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    return db_session


@pytest.fixture()
def fake_google(monkeypatch):
    calls = []
    monkeypatch.setitem(EXECUTORS, "doc_append", lambda db, a: calls.append("doc_append") or "doc:DOC123")
    monkeypatch.setitem(EXECUTORS, "email_draft", lambda db, a: calls.append("email_draft") or "draft:1")
    return calls


def _fetch(p, w, m):
    return [dict(r) for r in RAW]


def test_successful_run_delivers_doc_then_email(corpus, fake_google):
    run = auto.weekly_and_deliver(corpus, now=NOW, fetcher=_fetch)
    assert run.status == "awaiting_approval"
    assert fake_google == ["doc_append", "email_draft"]
    acts = corpus.query(Action).filter_by(source_ref=f"weekly_run:{run.id}").all()
    assert {a.status for a in acts} == {"executed"}
    assert corpus.query(Explainer).filter_by(run_id=run.id).one().status == "canonical"
    assert corpus.query(AuditLog).filter_by(actor=auto.AUTO_ACTOR, verb="approve").count() == 2


def test_failed_run_delivers_nothing(corpus, fake_google):
    def boom(p, w, m):
        raise RuntimeError("play store down")
    run = auto.weekly_and_deliver(corpus, now=NOW, fetcher=boom)
    assert run.status == "failed" and fake_google == []


def test_auto_approve_off_leaves_actions_pending(corpus, fake_google, monkeypatch):
    monkeypatch.setattr(get_settings(), "auto_approve", False)
    run = auto.weekly_and_deliver(corpus, now=NOW, fetcher=_fetch)
    assert fake_google == []
    assert {a.status for a in corpus.query(Action).filter_by(source_ref=f"weekly_run:{run.id}")} == {"pending"}


def _failed_action(db, type_="doc_append"):
    a = Action(type=type_, target_label="x", target_ref="DOC123", content="c", source_ref="weekly_run:99",
               status="failed", error="McpDeliveryError: invalid_grant")
    db.add(a)
    db.commit()
    return a


def test_retry_caps_at_six_attempts(db_session, monkeypatch):
    calls = []

    def always_fails(db, a):
        calls.append(1)
        raise RuntimeError("invalid_grant")
    monkeypatch.setitem(EXECUTORS, "doc_append", always_fails)
    _failed_action(db_session)
    for _ in range(8):
        auto.retry_failed_deliveries(db_session)
    assert len(calls) == 6


def test_retry_succeeds_and_stops(db_session, monkeypatch):
    monkeypatch.setitem(EXECUTORS, "email_draft", lambda db, a: "draft:1")
    a = _failed_action(db_session, "email_draft")
    assert auto.retry_failed_deliveries(db_session) == 1
    db_session.refresh(a)
    assert a.status == "executed"
    assert auto.retry_failed_deliveries(db_session) == 0


def test_retry_ignores_reply_actions(db_session, monkeypatch):
    called = []
    monkeypatch.setitem(EXECUTORS, "reply_publish", lambda db, a: called.append(1) or "x")
    t = Ticket(code="GRW-RETRY1", channel="text", language="en", question_redacted="q", pii_types=[],
               intent="fee_question", status="in_review")
    db_session.add(t)
    db_session.flush()
    d = Draft(ticket_id=t.id, reply="r", disposition="reply", routing_team="x", routing_priority="P3",
              routing_why="y", review_status="pass")
    db_session.add(d)
    db_session.flush()
    db_session.add(Action(type="reply_publish", target_label="r", target_ref=t.code, draft_id=d.id, status="failed"))
    db_session.commit()
    assert auto.retry_failed_deliveries(db_session) == 0 and called == []


def test_scheduler_registers_hourly_retry(monkeypatch):
    from app import scheduler
    monkeypatch.setattr(get_settings(), "scheduler_enabled", True)
    sch = scheduler.start_scheduler()
    try:
        assert {"weekly_loop", "corpus_refresh", "delivery_retry"} <= {j.id for j in sch.get_jobs()}
    finally:
        sch.shutdown(wait=False)
