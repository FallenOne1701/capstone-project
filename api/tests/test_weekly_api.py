import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app import deps
from app.models import WeeklyRun

H = {"X-Console-Key": "test-pass"}
FIX = Path(__file__).parent / "fixtures"
RAW = json.loads((FIX / "reviews.json").read_text())


@pytest.fixture()
def ran(client, db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    from app.weekly.run import run_weekly
    r = asyncio.run(run_weekly(db_session, now=datetime(2026, 11, 17, 9, tzinfo=timezone.utc),
                               fetcher=lambda p, w, m: [dict(x) for x in RAW]))
    assert r.status == "awaiting_approval", r.error
    return r


def test_latest_shows_traced_themes_and_pending_actions(client, ran):
    body = client.get("/api/console/weekly/latest", headers=H).json()
    assert body["run"]["status"] == "awaiting_approval"
    assert all(t["review_ids"] and t["window_start"] and t["window_end"] for t in body["themes"])
    assert {a["type"] for a in body["actions"]} == {"doc_append", "email_draft"}
    assert all(a["content"] and a["target_label"] for a in body["actions"])


def test_approve_doc_makes_explainer_canonical_and_listed(client, ran, monkeypatch):
    from app.approvals import executors
    from app.config import get_settings
    monkeypatch.setattr(executors, "call_tool", lambda name, args: {"ok": True})   # never touch real Google in tests
    monkeypatch.setattr(get_settings(), "pulse_doc_id", "DOC123")
    acts = client.get("/api/console/actions?status=pending", headers=H).json()
    doc = next(a for a in acts if a["type"] == "doc_append")
    assert client.post(f"/api/console/actions/{doc['id']}/approve", headers=H).status_code == 200
    exps = client.get("/api/console/explainers", headers=H).json()
    assert exps[0]["status"] == "canonical" and "reuse_count" in exps[0]


def test_theme_provider_feeds_pattern_agent(db_session, ran):
    stats = deps.latest_theme_stats(db_session)
    assert stats and all(s.cues and s.team for s in stats)
    assert stats[0].window.end == "2026-11-17"


def test_weekly_run_endpoint_conflict_when_running(client, db_session):
    db_session.add(WeeklyRun(status="running", window_start=date(2026, 9, 22), window_end=date(2026, 11, 17)))
    db_session.commit()
    assert client.post("/api/console/weekly/run", headers=H).status_code == 409


def test_latest_404_when_no_runs(client):
    assert client.get("/api/console/weekly/latest", headers=H).status_code == 404


def test_scheduler_disabled_by_default(monkeypatch):
    from app.config import Settings, get_settings
    assert Settings.model_fields["scheduler_enabled"].default is False
    monkeypatch.setattr(get_settings(), "scheduler_enabled", False)   # never depend on the developer's real .env
    from app.scheduler import start_scheduler
    assert start_scheduler() is None
