"""Plan 3c final-review fixes."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import get_settings
from app.models import Action, AuditLog, Draft, Explainer, Ticket, WeeklyRun

FIX = Path(__file__).parent / "fixtures"
RAW = json.loads((FIX / "reviews.json").read_text())


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    monkeypatch.setattr(s, "pulse_doc_id", "DOC123")
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")


def _run(db, day):
    from app.weekly.run import run_weekly
    r = asyncio.run(run_weekly(db, now=datetime(2026, 11, day, 9, tzinfo=timezone.utc),
                               fetcher=lambda p, w, m: [dict(x) for x in RAW]))
    assert r.status == "awaiting_approval", r.error
    return r


def _deliveries(db, run):
    return db.query(Action).filter_by(source_ref=f"weekly_run:{run.id}").order_by(Action.id).all()


# Important 1 — older weekly writes can't hang around unseen, and a failed newer attempt can't hide them
def test_new_run_supersedes_older_waiting_deliveries(db_session, corpus):
    r1 = _run(db_session, 17)
    old_doc, old_mail = _deliveries(db_session, r1)
    old_mail.status, old_mail.error = "failed", "expired"
    db_session.commit()
    r2 = _run(db_session, 24)
    for a in (old_doc, old_mail):
        db_session.refresh(a)
        assert a.status == "rejected"
        assert db_session.query(AuditLog).filter_by(verb="supersede", entity="action", entity_id=a.id).count() == 1
    assert {a.status for a in _deliveries(db_session, r2)} == {"pending"}
    assert db_session.query(Explainer).filter_by(run_id=r1.id).one().status == "rejected"


def test_desk_weekly_keeps_showing_the_ready_run_when_a_newer_attempt_fails(client, db_session, corpus):
    r1 = _run(db_session, 17)
    db_session.add(WeeklyRun(status="failed", error="Play Store fetch failed", window_start=r1.window_start,
                             window_end=r1.window_end))
    db_session.commit()
    body = client.get("/api/desk/weekly/latest").json()
    assert body["run"]["id"] == r1.id
    assert len(body["actions"]) == 2
    assert body["latest_attempt"]["status"] == "failed"
    assert body["latest_attempt"]["error"] == "Play Store fetch failed"


# Important 3 — Approve publishes only the text the approver saw
def _pending_reply(db, code="GRW-SEEN01"):
    t = Ticket(code=code, channel="text", language="en", question_redacted="q", pii_types=[],
               intent="fee_question", status="in_review")
    db.add(t)
    db.flush()
    d = Draft(ticket_id=t.id, reply="The expense ratio is 0.77%.", citation="https://groww.in/x",
              last_checked="2026-11-17", disposition="reply", routing_team="x", routing_priority="P3",
              routing_why="y", review_status="pass")
    db.add(d)
    db.flush()
    a = Action(type="reply_publish", target_label=f"Reply to ticket {code}", target_ref=code, draft_id=d.id)
    db.add(a)
    db.commit()
    return t, d, a


def test_approve_refuses_a_draft_that_changed_since_it_was_seen(client, db_session):
    _, d, a = _pending_reply(db_session)
    seen = d.reply
    d.reply = "The expense ratio is 0.80% per year, as listed on the official page."
    db_session.commit()
    r = client.post(f"/api/desk/actions/{a.id}/approve", json={"reply": seen})
    assert r.status_code == 409
    assert r.json()["detail"] == "This draft changed — review it again."
    db_session.refresh(a)
    assert a.status == "pending"


def test_approve_needs_the_reply_that_was_seen(client, db_session):
    _, d, a = _pending_reply(db_session)
    assert client.post(f"/api/desk/actions/{a.id}/approve").status_code == 422
    assert client.post(f"/api/desk/actions/{a.id}/approve", json={"reply": d.reply}).json()["status"] == "executed"


# Minor 1 (re-graded) — Google failures in plain words; the raw error stays in the audit log
def test_plain_google_errors():
    from app.approvals.service import plain_error
    assert plain_error("McpDeliveryError: google_docs_append_content failed: invalid_grant") == (
        "Google sign-in has expired — the owner needs to reconnect Google, then press Retry.")
    assert plain_error("TimeoutError: ") == (
        "Google didn't answer in time. Check the Doc or Gmail drafts before pressing Retry — it may have gone through.")
    assert plain_error("McpDeliveryError: PULSE_DOC_ID was not set when this run was created; start a new weekly run") == (
        "The Google write failed: PULSE_DOC_ID was not set when this run was created; start a new weekly run")


def test_failed_delivery_shows_plain_words_and_audits_raw(db_session, monkeypatch):
    from app.approvals import executors, service
    def boom(db, a):
        raise RuntimeError("google_docs_append_content failed: invalid_grant: Token has been expired or revoked.")
    monkeypatch.setitem(executors.EXECUTORS, "doc_append", boom)
    a = Action(type="doc_append", target_label="Doc", target_ref="DOC1", content="x", source_ref="weekly_run:99")
    db_session.add(a)
    db_session.commit()
    service.approve(db_session, a.id, "page")
    assert a.status == "failed"
    assert a.error == "Google sign-in has expired — the owner needs to reconnect Google, then press Retry."
    raw = db_session.query(AuditLog).filter_by(verb="fail", entity_id=a.id).one().detail
    assert "invalid_grant" in raw


# Minor 2 (re-graded) — auto mode never shows the asker "couldn't answer" before its fallback reply
def test_reject_can_leave_the_ticket_open(db_session):
    from app.approvals.service import reject
    t, _, a = _pending_reply(db_session, "GRW-OPEN01")
    reject(db_session, a.id, "auto-reviewer", close_ticket=False)
    db_session.refresh(t)
    assert t.status == "in_review"


def test_auto_decide_keeps_blocked_tickets_open_for_the_fallback(db_session, monkeypatch):
    from app.approvals import auto
    t, d, _ = _pending_reply(db_session, "GRW-OPEN02")
    d.review_status = "blocked"
    db_session.commit()
    seen = []
    real = auto.reject
    monkeypatch.setattr(auto, "reject", lambda db, i, actor, **kw: seen.append(kw) or real(db, i, actor, **kw))
    auto.auto_decide(db_session, t.id)
    assert seen == [{"close_ticket": False}]
    db_session.refresh(t)
    assert t.status == "answered"
