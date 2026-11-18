"""Public weekly summary and per-answer checks (Plan 3b Task 3)."""

import json
from datetime import date, datetime, timedelta, timezone

from app.approvals.auto import AUTO_ACTOR
from app.approvals.service import audit
from app.models import Action, Draft, Explainer, Theme, Ticket, WeeklyRun

PULSE = ('# Groww Weekly Review Pulse — week ending {d}\n\n## What users said\n'
         '- "App crashes when I open portfolio" (rv_abc234)\n- "Exit load was not clear" (rv_def567)\n')


def _run(db, *, end: date, status="awaiting_approval", doc="executed", email="executed", doc_error=None):
    r = WeeklyRun(status=status, window_start=end - timedelta(weeks=8), window_end=end, review_count=120,
                  pulse_text=PULSE.format(d=end.isoformat()), finished_at=datetime.now(timezone.utc))
    db.add(r)
    db.flush()
    db.add(Theme(run_id=r.id, theme_id="app", label="App stability", count=12, recent_count=3,
                 review_ids=["rv_abc234"], window_start=r.window_start, window_end=end, rank=1))
    db.add(Theme(run_id=r.id, theme_id="fees", label="Fees and charges", count=8, recent_count=2,
                 review_ids=["rv_def567"], window_start=r.window_start, window_end=end, rank=2))
    db.add(Explainer(run_id=r.id, topic="exit_load", title="Exit load explained", last_checked=end.isoformat(),
                     bullets=[{"text": "Exit load is a fee on early redemption.", "url": "https://www.amfiindia.com/x"}],
                     status="canonical", evidence={"reviews": 3, "tickets": 1}))
    for t, st, err in (("doc_append", doc, doc_error), ("email_draft", email, None)):
        db.add(Action(type=t, target_label="secret label team@example.com DOC123", target_ref="DOC123",
                      content="c", source_ref=f"weekly_run:{r.id}", status=st, error=err))
    db.commit()
    return r


def test_summary_404_without_runs(client):
    r = client.get("/api/weekly/summary")
    assert r.status_code == 404 and r.json()["detail"] == "no weekly pulse yet"


def test_summary_uses_last_successful_run(client, db_session):
    today = date.today()
    _run(db_session, end=today - timedelta(days=1))
    _run(db_session, end=today, status="failed")
    body = client.get("/api/weekly/summary").json()
    assert body["week_ending"] == (today - timedelta(days=1)).isoformat()
    assert body["stale"] is False
    assert [t["label"] for t in body["themes"]] == ["App stability", "Fees and charges"]
    assert body["quotes"][0] == {"text": "App crashes when I open portfolio", "theme": "App stability"}
    assert body["explainer"]["bullets"][0]["url"].startswith("https://www.amfiindia.com")
    assert body["delivery"] == {"doc": "delivered", "email_draft": "delivered"}


def test_summary_marks_stale_week(client, db_session):
    _run(db_session, end=date.today() - timedelta(days=10))
    assert client.get("/api/weekly/summary").json()["stale"] is True


def test_summary_has_no_private_fields(client, db_session):
    _run(db_session, end=date.today())
    text = json.dumps(client.get("/api/weekly/summary").json())
    for secret in ("rv_", "@", "DOC123", "recipient", "target"):
        assert secret not in text


def test_delivery_words(client, db_session):
    r = _run(db_session, end=date.today(), doc="failed", email="pending", doc_error="McpDeliveryError: invalid_grant")
    doc = db_session.query(Action).filter_by(source_ref=f"weekly_run:{r.id}", type="doc_append").one()
    for _ in range(2):
        audit(db_session, AUTO_ACTOR, "retry", "action", doc.id)
    db_session.commit()
    d = client.get("/api/weekly/summary").json()["delivery"]
    assert d == {"doc": "pending (retrying)", "email_draft": "not started"}
    for _ in range(4):
        audit(db_session, AUTO_ACTOR, "retry", "action", doc.id)
    db_session.commit()
    assert client.get("/api/weekly/summary").json()["delivery"]["doc"] == "failed — sign-in expired"
    doc.error = "McpDeliveryError: server crashed"
    db_session.commit()
    assert client.get("/api/weekly/summary").json()["delivery"]["doc"] == "failed"


def _answered(db, *, disposition="reply", why="Facts covered.", reused=None, status="answered"):
    t = Ticket(code="GRW-CHECK1", channel="text", language="en", question_redacted="my pan [PAN] exit load?",
               pii_types=["PAN"], intent="fee_question", status=status, answer_text="ans")
    db.add(t)
    db.flush()
    d = Draft(ticket_id=t.id, reply="ans", citation="https://groww.in/mutual-funds/x", last_checked="2026-11-17",
              disposition=disposition, routing_team="x", routing_priority="P3", routing_why=why,
              review_status="pass", reused_explainer_id=reused)
    db.add(d)
    db.flush()
    db.add(Action(type="reply_publish", target_label="r", target_ref=t.code, draft_id=d.id,
                  status="executed" if status == "answered" else "pending"))
    db.commit()
    return t


def test_ticket_checks_only_when_answered(client, db_session):
    _answered(db_session, status="in_review")
    assert client.get("/api/tickets/GRW-CHECK1").json()["checks"] is None


def test_ticket_checks_for_an_answer(client, db_session):
    _answered(db_session, reused=4)
    c = client.get("/api/tickets/GRW-CHECK1").json()["checks"]
    assert c["review"] == "pass" and c["citation"] == "https://groww.in/mutual-funds/x"
    assert c["last_checked"] == "2026-11-17" and c["reused_explainer"] == 4 and c["fallback"] is None
    assert set(c["checks"]) == {"citation", "advice", "performance", "pii", "shape"}
    assert "reviewer" in c["agents"]


def test_ticket_checks_show_fallback_reason(client, db_session):
    _answered(db_session, disposition="fallback", why="Fallback: advice. Official page: https://groww.in/x")
    c = client.get("/api/tickets/GRW-CHECK1").json()["checks"]
    assert c["fallback"] == "The drafted answer read like advice, so a safe reply was sent instead."
