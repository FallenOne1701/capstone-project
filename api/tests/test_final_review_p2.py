"""Plan 2 final-review fixes: stale canonical, stuck runs, executed target = shown target, retry, small items."""

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.approvals import executors
from app.approvals.service import approve, retry
from app.delivery.mcp_client import McpDeliveryError
from app.models import Action, Explainer, WeeklyRun

H = {"X-Console-Key": "test-pass"}
FIX = Path(__file__).parent / "fixtures"
CALLS: list = []


@pytest.fixture()
def fake_mcp(monkeypatch):
    CALLS.clear()

    def fake(name, args):
        CALLS.append((name, args))
        return {"ok": True}
    monkeypatch.setattr(executors, "call_tool", fake)
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "pulse_doc_id", "DOC_NOW")
    monkeypatch.setattr(s, "pulse_draft_recipient", "team@example.com")
    return CALLS


def _run_with_actions(db, *, doc_ref="DOC_SHOWN", topic="brokerage"):
    r = WeeklyRun(status="awaiting_approval", window_start=date(2026, 10, 26), window_end=date(2026, 11, 17))
    db.add(r); db.flush()
    ex = Explainer(run_id=r.id, topic=topic, title="t", bullets=[{"text": "a", "url": "https://groww.in/a"}],
                   last_checked="2026-11-17", status="draft", evidence={})
    doc = Action(type="doc_append", target_label="doc", target_ref=doc_ref, content="BODY",
                 source_ref=f"weekly_run:{r.id}")
    mail = Action(type="email_draft", target_label="mail", target_ref=executors.recipient_ref("team@example.com"),
                  content="Subject: S\n\nBODY", source_ref=f"weekly_run:{r.id}")
    db.add_all([ex, doc, mail]); db.commit()
    return r, ex, doc, mail


# --- Important 1: an older run's approval must not replace a newer canonical explainer -----------------------

def test_approving_older_run_doc_does_not_replace_newer_canonical(db_session, fake_mcp):
    _, old_ex, old_doc, _ = _run_with_actions(db_session)
    _, new_ex, new_doc, _ = _run_with_actions(db_session)
    approve(db_session, new_doc.id, "console")
    approve(db_session, old_doc.id, "console")       # still appends to the Doc (human chose to), but…
    db_session.expire_all()
    assert db_session.get(Explainer, new_ex.id).status == "canonical"
    assert db_session.get(Explainer, old_ex.id).status == "superseded"


# --- Important 2: stuck/duplicate weekly runs --------------------------------------------------------------

def test_interrupted_running_rows_are_failed_at_startup(db_session):
    db_session.add(WeeklyRun(status="running", window_start=date(2026, 10, 1), window_end=date(2026, 11, 17)))
    db_session.commit()
    from app.weekly.run import recover_interrupted_runs
    assert recover_interrupted_runs(db_session) == 1
    r = db_session.query(WeeklyRun).one()
    assert r.status == "failed" and "interrupted" in r.error


def test_weekly_run_endpoint_inserts_row_first_and_returns_id(client, db_session, monkeypatch):
    from app.api import console
    started = []
    monkeypatch.setattr(console, "_run_in_background", lambda run_id: started.append(run_id))
    body = client.post("/api/console/weekly/run", headers=H).json()
    assert body["status"] == "started" and started == [body["run_id"]]
    assert db_session.get(WeeklyRun, body["run_id"]).status == "running"
    assert client.post("/api/console/weekly/run", headers=H).status_code == 409   # a second click is refused


def test_run_weekly_uses_the_precreated_row(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    from app.weekly.run import run_weekly, start_run
    now = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
    pre = start_run(db_session, now=now)
    raw = json.loads((FIX / "reviews.json").read_text())
    r = asyncio.run(run_weekly(db_session, now=now, fetcher=lambda p, w, m: [dict(x) for x in raw], run_id=pre.id))
    assert r.id == pre.id and r.status == "awaiting_approval" and db_session.query(WeeklyRun).count() == 1


def test_start_run_refuses_while_one_is_running(db_session):
    from app.weekly.run import start_run
    now = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
    start_run(db_session, now=now)
    with pytest.raises(ValueError, match="already running"):
        start_run(db_session, now=now)


# --- Important 3: execute exactly the target the approver saw ------------------------------------------------

def test_doc_append_uses_the_doc_id_shown_not_current_setting(db_session, fake_mcp):
    _, _, doc, _ = _run_with_actions(db_session, doc_ref="DOC_SHOWN")
    approve(db_session, doc.id, "console")
    assert CALLS[0][1]["document_id"] == "DOC_SHOWN"


def test_doc_append_placeholder_target_fails(db_session, fake_mcp):
    _, _, doc, _ = _run_with_actions(db_session, doc_ref="PULSE_DOC_ID")
    a = approve(db_session, doc.id, "console")
    assert a.status == "failed" and "PULSE_DOC_ID" in a.error and CALLS == []


def test_email_fails_if_recipient_changed_since_shown(db_session, fake_mcp, monkeypatch):
    _, _, _, mail = _run_with_actions(db_session)
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "pulse_draft_recipient", "someone-else@example.com")
    a = approve(db_session, mail.id, "console")
    assert a.status == "failed" and "recipient" in a.error and CALLS == []


def test_email_label_shows_masked_recipient_without_pii(db_session, tmp_path, monkeypatch):
    from app.guard.pii import find_pii
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "pulse_draft_recipient", "team.lead@example.com")
    label = executors.recipient_label()
    assert "t***@example.com" in label and "team.lead" not in label and not find_pii(label)


# --- Important 4: failed actions can be retried -------------------------------------------------------------

def test_failed_action_can_be_retried_and_then_canonicalizes(db_session, fake_mcp, monkeypatch):
    _, ex, doc, _ = _run_with_actions(db_session)

    def boom(name, args):
        raise McpDeliveryError("token expired")
    monkeypatch.setattr(executors, "call_tool", boom)
    assert approve(db_session, doc.id, "console").status == "failed"
    monkeypatch.setattr(executors, "call_tool", lambda n, a: CALLS.append((n, a)) or {"ok": True})
    a = retry(db_session, doc.id, "console")
    db_session.expire_all()
    assert a.status == "executed" and a.error is None and len(CALLS) == 1
    assert db_session.get(Explainer, ex.id).status == "canonical"


def test_retry_only_from_failed(client, db_session, fake_mcp):
    _, _, doc, _ = _run_with_actions(db_session)
    with pytest.raises(ValueError):
        retry(db_session, doc.id, "console")
    assert client.post(f"/api/console/actions/{doc.id}/retry", headers=H).status_code == 409


def test_claim_is_committed_before_the_external_call(db_session, fake_mcp, monkeypatch):
    # Another session must already see 'approved' while the executor runs (no duplicate on crash, no long lock).
    _, _, doc, _ = _run_with_actions(db_session)
    from app import db as dbmod
    seen = []

    def peek(name, args):
        other = dbmod.SessionLocal()
        seen.append(other.get(Action, doc.id).status)
        other.close()
        return {"ok": True}
    monkeypatch.setattr(executors, "call_tool", peek)
    approve(db_session, doc.id, "console")
    assert seen == ["approved"]


# --- Minor items ------------------------------------------------------------------------------------------

def test_link2_does_not_treat_any_charge_as_brokerage():
    from app.weekly.fee_topics import topic_of
    assert topic_of("Is there a stamp duty charge on SIPs?", strict=True) is None
    assert topic_of("What is brokerage on HDFC mutual funds?", strict=True) == "brokerage"
    assert topic_of("so many hidden charges", strict=False) == "brokerage"     # review mining unchanged


def test_pii_still_redacts_numbers_with_non_breaking_spaces():
    from app.guard.pii import redact
    assert "[AADHAAR]" in redact("my aadhaar 1234 5678 9012").text
    assert "2026-11-17\n4" in redact("week ending 2026-11-17\n4 reviews").text


def test_verify_report_without_runs_says_so(db_session):
    from app.weekly.verify import build_report
    rep = build_report(db_session)
    assert "no weekly runs" in rep.markdown.lower()

