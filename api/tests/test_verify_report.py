import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models import Review, Theme, Ticket, WeeklyRun
from app.weekly.verify import build_report

FIX = Path(__file__).parent / "fixtures"
RAW = json.loads((FIX / "reviews.json").read_text())


@pytest.fixture()
def run(db_session, tmp_path, monkeypatch):
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


def test_clean_run_has_no_flags_and_all_sections(db_session, run):
    rep = build_report(db_session, run.id)
    assert rep.flags == [], rep.flags
    for h in ("## Run summary", "## Themes", "## Quotes", "## Repeated questions", "## Fee confusion",
              "## Explainer", "## Caps & scope", "## Pending actions", "## PII sweep", "## Manual checklist"):
        assert h in rep.markdown
    assert "count OK" in rep.markdown and "verbatim OK" in rep.markdown and "source OK" in rep.markdown


def test_theme_count_mismatch_flagged(db_session, run):
    t = db_session.query(Theme).filter_by(run_id=run.id).first()
    t.count += 1
    db_session.commit()
    assert any("count MISMATCH" in f for f in build_report(db_session, run.id).flags)


def test_tampered_quote_flagged(db_session, run):
    r = db_session.get(WeeklyRun, run.id)
    rid = re.findall(r'\((rv_[a-z2-7]+)\)', r.pulse_text)[0]
    db_session.get(Review, rid).text_redacted = "completely different text"
    db_session.commit()
    assert any(f"quote {rid} NOT FOUND" in f for f in build_report(db_session, run.id).flags)


def test_pii_sweep_finds_db_and_log_hits(db_session, run, tmp_path):
    db_session.add(Ticket(code="GRW-PII001", question_redacted="leaked 9876543210"))
    db_session.commit()
    log = tmp_path / "server.log"
    log.write_text("ok line\nuser pan ABCDE1234F\n", encoding="utf-8")
    flags = build_report(db_session, run.id, log_paths=[log]).flags
    assert any(f.startswith("PII tickets.question_redacted") for f in flags)
    assert any(f.startswith(f"PII log {log.name}:2") for f in flags)
