from datetime import date

import pytest

from app.approvals import executors
from app.approvals.service import approve, reject
from app.delivery.mcp_client import McpDeliveryError, call_tool
from app.models import Action, Explainer, WeeklyRun

CALLS = []


@pytest.fixture()
def fake_mcp(monkeypatch):
    CALLS.clear()

    def fake(name, args):
        CALLS.append((name, args))
        return {"document_id": args.get("document_id"), "draft_id": "r-1"}
    monkeypatch.setattr(executors, "call_tool", fake)
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "pulse_doc_id", "DOC123")
    monkeypatch.setattr(s, "pulse_draft_recipient", "team@example.com")
    return CALLS


@pytest.fixture()
def run(db_session):
    r = WeeklyRun(status="awaiting_approval", window_start=date(2026, 9, 22), window_end=date(2026, 11, 17))
    db_session.add(r); db_session.flush()
    ex = Explainer(run_id=r.id, topic="exit_load", title="t", bullets=[{"text": "a", "url": "https://groww.in/a"}],
                   last_checked="2026-11-17", status="draft", evidence={})
    doc = Action(type="doc_append", target_label="doc", target_ref="DOC123", content="PULSE BODY",
                 source_ref=f"weekly_run:{r.id}")
    mail = Action(type="email_draft", target_label="mail", target_ref=executors.recipient_ref("team@example.com"),
                  content="Subject: Groww weekly pulse\n\nPULSE BODY", source_ref=f"weekly_run:{r.id}")
    db_session.add_all([ex, doc, mail]); db_session.commit()
    return r, ex, doc, mail


def test_doc_approve_calls_docs_tool_only_and_canonicalizes(db_session, run, fake_mcp):
    r, ex, doc, mail = run
    approve(db_session, doc.id, "agent")
    db_session.expire_all()
    assert fake_mcp == [("google_docs_append_content", {"document_id": "DOC123", "content": "PULSE BODY",
                                                         "add_newline_before": True, "add_newline_after": True})]
    assert db_session.get(Action, doc.id).status == "executed"
    assert db_session.get(Action, mail.id).status == "pending"
    assert db_session.get(Explainer, ex.id).status == "canonical"


def test_email_approve_creates_gmail_draft_never_sends(db_session, run, fake_mcp):
    r, ex, doc, mail = run
    approve(db_session, mail.id, "agent")
    db_session.expire_all()
    assert fake_mcp == [("gmail_create_draft", {"to": ["team@example.com"], "subject": "Groww weekly pulse",
                                                 "body": "PULSE BODY", "is_html": False})]
    assert db_session.get(Explainer, ex.id).status == "draft"


def test_send_tool_is_denylisted():
    with pytest.raises(McpDeliveryError):
        call_tool("gmail_send_email", {"to": ["x@example.com"]})


def test_missing_doc_id_fails_action_cleanly(db_session, run, fake_mcp):
    r, ex, doc, mail = run
    doc.target_ref = executors.DOC_PLACEHOLDER   # PULSE_DOC_ID was unset when the run created the action
    db_session.commit()
    a = approve(db_session, doc.id, "agent")
    assert a.status == "failed" and "PULSE_DOC_ID" in a.error and fake_mcp == []
    db_session.expire_all()
    assert db_session.get(Explainer, ex.id).status == "draft"


def test_mcp_failure_redacted_and_not_canonical(db_session, run, monkeypatch):
    r, ex, doc, mail = run

    def boom(name, args):
        raise McpDeliveryError("google 401 for ABCDE1234F")
    monkeypatch.setattr(executors, "call_tool", boom)
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "pulse_doc_id", "DOC123")
    a = approve(db_session, doc.id, "agent")
    assert a.status == "failed" and "ABCDE1234F" not in a.error
    db_session.expire_all()
    assert db_session.get(Explainer, ex.id).status == "draft"


def test_reject_doc_rejects_explainer(db_session, run, fake_mcp):
    r, ex, doc, mail = run
    reject(db_session, doc.id, "agent")
    db_session.expire_all()
    assert db_session.get(Explainer, ex.id).status == "rejected" and db_session.get(Action, mail.id).status == "pending"
    assert fake_mcp == []


def test_second_approve_raises(db_session, run, fake_mcp):
    r, ex, doc, mail = run
    approve(db_session, doc.id, "agent")
    with pytest.raises(ValueError):
        approve(db_session, doc.id, "agent")
    assert len(fake_mcp) == 1


def test_new_canonical_supersedes_old(db_session, run, fake_mcp):
    r, ex, doc, mail = run
    old = Explainer(topic="exit_load", title="old", bullets=[], last_checked="2026-11-01", status="canonical", evidence={})
    db_session.add(old); db_session.commit()
    approve(db_session, doc.id, "agent")
    db_session.expire_all()
    assert db_session.get(Explainer, old.id).status == "superseded"


def test_call_tool_requires_built_server(monkeypatch, tmp_path):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "mcp_server_dir", tmp_path)
    with pytest.raises(McpDeliveryError, match="not built"):
        call_tool("google_docs_append_content", {})
