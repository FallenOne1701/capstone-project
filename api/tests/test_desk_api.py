"""Plan 3c Task 2: the page's own approval endpoints — no password, audited as `page`, rate-limited."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models import Action, AuditLog, Draft, Ticket

FIX = Path(__file__).parent / "fixtures"


def _ticket(db, code, review="pass", status="in_review", action_status="pending", created=None):
    t = Ticket(code=code, channel="text", language="en", question_redacted="q", pii_types=[],
               intent="fee_question", status=status)
    if created is not None:
        t.created_at = created
    db.add(t)
    db.flush()
    d = Draft(ticket_id=t.id, reply="The expense ratio is 0.77%.", citation="https://groww.in/x",
              last_checked="2026-11-17", disposition="reply", routing_team="x", routing_priority="P3",
              routing_why="y", review_status=review)
    db.add(d)
    db.flush()
    a = Action(type="reply_publish", target_label=f"Reply to ticket {code}", target_ref=code, draft_id=d.id,
               status=action_status)
    db.add(a)
    db.commit()
    return t, d, a


def test_desk_needs_no_key(client):
    assert client.get("/api/desk/queue").status_code == 200
    assert client.get("/api/console/queue").status_code == 401


def test_page_approve_publishes_and_audits_as_page(client, db_session):
    t, d, a = _ticket(db_session, "GRW-DESK01")
    r = client.post(f"/api/desk/actions/{a.id}/approve", json={"reply": d.reply})
    assert r.status_code == 200 and r.json()["status"] == "executed"
    db_session.refresh(t)
    assert t.status == "answered"
    verbs = {r.verb for r in db_session.query(AuditLog).filter_by(actor="page", entity="action", entity_id=a.id)}
    assert {"approve", "execute"} <= verbs


def test_second_approve_is_409(client, db_session):
    _, d, a = _ticket(db_session, "GRW-DESK02")
    assert client.post(f"/api/desk/actions/{a.id}/approve", json={"reply": d.reply}).status_code == 200
    assert client.post(f"/api/desk/actions/{a.id}/approve", json={"reply": d.reply}).status_code == 409
    assert db_session.query(AuditLog).filter_by(verb="execute", entity="action", entity_id=a.id).count() == 1


def test_blocked_draft_approve_is_409(client, db_session):
    _, d, a = _ticket(db_session, "GRW-DESK03", review="blocked")
    assert client.post(f"/api/desk/actions/{a.id}/approve", json={"reply": d.reply}).status_code == 409


def test_page_edit_redacts_pii(client, db_session):
    _, d, _ = _ticket(db_session, "GRW-DESK04")
    r = client.post(f"/api/desk/drafts/{d.id}/edit",
                    json={"reply": "Your PAN ABCDE1234F is noted. The expense ratio is 0.77% (source)."})
    assert r.status_code == 200
    assert "ABCDE1234F" not in r.json()["reply"]
    assert db_session.query(AuditLog).filter_by(actor="page", verb="edit", entity_id=d.id).count() == 1


def test_page_reject_closes_ticket(client, db_session):
    t, _, a = _ticket(db_session, "GRW-DESK05")
    assert client.post(f"/api/desk/actions/{a.id}/reject").json()["status"] == "rejected"
    db_session.refresh(t)
    assert t.status == "closed"


def test_page_reprocess_reruns_failed_ticket(client, db_session, monkeypatch):
    from app.tickets import worker
    monkeypatch.setattr(worker, "submit", lambda _id: None)
    t = Ticket(code="GRW-DESK06", channel="text", language="en", question_redacted="q", pii_types=[],
               intent="fee_question", status="failed")
    db_session.add(t)
    db_session.commit()
    assert client.post("/api/desk/tickets/GRW-DESK06/reprocess").json() == {"code": "GRW-DESK06", "status": "received"}
    assert db_session.query(AuditLog).filter_by(actor="page", verb="reprocess", entity_id=t.id).count() == 1


def test_queue_lists_pending_first_and_caps_30(client, db_session):
    base = datetime(2026, 11, 1, tzinfo=timezone.utc)
    _ticket(db_session, "GRW-OLDPEN", created=base)                       # oldest, but still waiting
    for i in range(34):
        _ticket(db_session, f"GRW-DONE{i:02d}", status="answered", action_status="executed",
                created=base + timedelta(hours=i + 1))
    items = client.get("/api/desk/queue").json()
    assert len(items) == 30
    assert items[0]["code"] == "GRW-OLDPEN"
    assert items[1]["code"] == "GRW-DONE33"   # then newest first


@pytest.fixture()
def ran(client, db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    monkeypatch.setattr(s, "pulse_draft_recipient", "product.lead@example.com")
    monkeypatch.setattr(s, "pulse_doc_id", "DOC123")
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    from app.weekly.run import run_weekly
    raw = json.loads((FIX / "reviews.json").read_text())
    r = asyncio.run(run_weekly(db_session, now=datetime(2026, 11, 17, 9, tzinfo=timezone.utc),
                               fetcher=lambda p, w, m: [dict(x) for x in raw]))
    assert r.status == "awaiting_approval", r.error
    return r


def test_weekly_latest_never_leaks_recipient(client, ran):
    r = client.get("/api/desk/weekly/latest")
    assert r.status_code == 200
    body = r.text
    assert "product.lead@example.com" not in body
    assert all("target_ref" not in a for a in r.json()["actions"])
    assert client.get("/api/desk/sources").status_code == 200
    assert client.get("/api/desk/explainers").status_code == 200


def test_desk_action_rate_limit(client, db_session):
    for _ in range(30):
        assert client.post("/api/desk/actions/99999/approve").status_code == 404
    assert client.post("/api/desk/actions/99999/approve").status_code == 429


def test_weekly_run_once_an_hour(client, db_session, monkeypatch):
    from app.api import desk
    monkeypatch.setattr(desk, "_run_in_background", lambda run_id: None)
    assert client.post("/api/desk/weekly/run").status_code == 202
    r = client.post("/api/desk/weekly/run")
    assert r.status_code == 429
    assert r.json()["detail"] == "The weekly pulse was run in the last hour — please try again later."
