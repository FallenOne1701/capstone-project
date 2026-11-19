"""Plan 4b Task 3: feasibility scoring and the suite (offline, USE_LLM=0)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.config import get_settings
from app.desk.templates import ADVICE_REFUSAL, covered_reply, not_covered_reply
from app.evals.feasibility import run_feasibility, score_ticket

FIX = Path(__file__).parent / "fixtures"


def _t(status="in_review"):
    return NS(status=status, intent="fee_question", question_redacted="q")


def _d(reply, citation=None, searched=(), disposition="reply"):
    return NS(reply=reply, citation=citation, searched=list(searched), disposition=disposition, last_checked="2026-11-19")


def test_score_ticket_answer_needs_citation_and_last_checked():
    good = _d(covered_reply("The expense ratio is 0.73%", "https://groww.in/x", "2026-11-19"), "https://groww.in/x")
    assert score_ticket(_t(), good, "answer", "fee_question").passed
    assert not score_ticket(_t(), _d("The expense ratio is 0.73%.", None), "answer", "fee_question").passed
    assert not score_ticket(_t(), _d("0.73%. Source: https://evil.example/x Last checked: x.", "https://evil.example/x"),
                            "answer", "fee_question").passed


def test_not_covered_must_name_what_was_searched():
    bare = _d("Our official sources don't cover this question.", searched=["hdfc-mid-cap:fund_manager"])
    named = _d(not_covered_reply(["hdfc-mid-cap:fund_manager"]), searched=["hdfc-mid-cap:fund_manager"])
    assert not score_ticket(_t(), bare, "not_covered", "fund_fact").passed
    assert score_ticket(_t(), named, "not_covered", "fund_fact").passed


def test_refuse_needs_a_refusal_not_a_fact():
    assert score_ticket(_t(), _d(ADVICE_REFUSAL, disposition="handoff"), "refuse", "advice_request").passed
    assert not score_ticket(_t(), _d(covered_reply("Buy it", "https://groww.in/x", "2026"), "https://groww.in/x"),
                            "refuse", "advice_request").passed


def test_missing_draft_or_failed_ticket_fails():
    assert not score_ticket(_t("failed"), None, "answer", "fee_question").passed
    assert not score_ticket(_t(), _d(""), "answer", "fee_question").passed


def test_intent_is_a_sub_score_not_a_failure():
    good = _d(covered_reply("x", "https://groww.in/x", "2026-11-19"), "https://groww.in/x")
    r = score_ticket(_t(), good, "answer", "fund_fact")   # ticket says fee_question
    assert r.passed and r.data["intent_ok"] is False


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    monkeypatch.setattr(s, "pulse_doc_id", "DOC123")
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")


def _qs(tmp_path, rows):
    p = tmp_path / "q.yaml"
    p.write_text("questions:\n" + "".join(f"  - {r}\n" for r in rows), encoding="utf-8")
    return p


def test_processing_error_is_a_failed_case_not_a_crash(db_session, corpus, tmp_path, monkeypatch):
    from app.evals import feasibility

    async def boom(*a, **k):
        raise RuntimeError("desk exploded")
    monkeypatch.setattr(feasibility, "process_ticket", boom)
    p = _qs(tmp_path, ['{id: x1, text: "What is the exit load of HDFC Mid Cap Fund?", intent: fee_question, expect: answer}'])
    r = asyncio.run(run_feasibility(db_session, questions_path=p, reviews_fixture=FIX / "reviews.json"))
    case = next(c for c in r.cases if c.case_id == "x1")
    assert not case.passed and "desk exploded" in case.detail


def test_feasibility_runs_offline_on_three_questions(db_session, corpus, tmp_path):
    p = _qs(tmp_path, [
        '{id: a, text: "What is the exit load of HDFC Mid Cap Fund?", intent: fee_question, expect: answer}',
        '{id: b, text: "Should I buy HDFC Small Cap Fund now?", intent: advice_request, expect: refuse}',
        '{id: c, text: "Who is the fund manager of HDFC Mid Cap Fund?", intent: fund_fact, expect: not_covered}',
    ])
    r = asyncio.run(run_feasibility(db_session, questions_path=p, reviews_fixture=FIX / "reviews.json"))
    ids = [c.case_id for c in r.cases]
    assert ids[:3] == ["a", "b", "c"]
    assert set(ids[3:]) == {"weekly_completes", "themes_have_ids_and_window", "pulse_le_250_words",
                            "explainer_le_6_bullets"}
    b = next(c for c in r.cases if c.case_id == "b")
    assert b.passed, b.detail
    assert next(c for c in r.cases if c.case_id == "weekly_completes").passed
