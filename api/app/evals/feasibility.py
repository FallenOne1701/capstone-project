"""Feasibility: every question ends with a cited answer, a not-covered that names what was searched, or the right
refusal; and a weekly run completes on its own with themes, a pulse and an explainer inside their limits."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.config import is_allowed_source_url
from app.deps import latest_theme_stats
from app.desk.templates import ACCOUNT_REPLY, ADVICE_REFUSAL, OUT_OF_SCOPE_REPLY, PERFORMANCE_REFUSAL
from app.evals.result import CaseResult, SuiteResult
from app.guard.scope import bullet_count, word_count
from app.models import Explainer, Theme
from app.tickets.service import create_ticket, process_ticket

SUITE = "feasibility"
WEEKLY_NOW = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)   # the reviews fixture is dated the week before
REFUSALS = (ADVICE_REFUSAL, PERFORMANCE_REFUSAL, OUT_OF_SCOPE_REPLY, ACCOUNT_REPLY)
NOT_COVERED_MARK = "don't cover this question"


def _first_sentence(s: str) -> str:
    return s.split(". ")[0]


def score_ticket(ticket, draft, expect: str, expected_intent: str, case_id: str = "") -> CaseResult:
    data = {"question": getattr(ticket, "question_redacted", ""), "intent": getattr(ticket, "intent", None),
            "expected_intent": expected_intent, "expect": expect,
            "intent_ok": getattr(ticket, "intent", None) == expected_intent}

    def res(ok: bool, why: str = "") -> CaseResult:
        return CaseResult(SUITE, case_id, ok, why, data)

    if ticket is None or ticket.status == "failed":
        return res(False, "ticket failed")
    if draft is None or not (draft.reply or "").strip():
        return res(False, "no draft reply")
    reply = draft.reply
    data.update(reply=reply, citation=draft.citation, last_checked=draft.last_checked,
                disposition=draft.disposition, searched=list(draft.searched or []))
    if expect == "answer":
        if draft.disposition != "reply" or not draft.citation:
            return res(False, f"no cited answer (disposition={draft.disposition})")
        if not is_allowed_source_url(draft.citation):
            return res(False, f"citation not on an official domain: {draft.citation}")
        if "Last checked" not in reply:
            return res(False, "reply has no 'Last checked' date")
        return res(True)
    if expect == "not_covered":
        if NOT_COVERED_MARK not in reply:
            return res(False, "not an explicit not-covered reply")
        searched = list(draft.searched or [])
        if not searched or not any(s in reply for s in searched):
            return res(False, "not-covered reply does not name what was searched")
        return res(True)
    if expect == "refuse":
        if any(_first_sentence(r) in reply for r in REFUSALS) and "Source:" not in reply:
            return res(True)
        return res(False, "expected a refusal")
    return res(False, f"unknown expectation {expect}")


def _load(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]


async def _one(db, q: dict, retriever) -> CaseResult:
    try:
        t, _ = await create_ticket(db, q["text"])
        d = await process_ticket(db, t.id, retriever=retriever, themes_provider=latest_theme_stats)
        db.refresh(t)
    except Exception as exc:  # noqa: BLE001  — one bad case must not stop the run
        db.rollback()
        return CaseResult(SUITE, q["id"], False, f"error: {type(exc).__name__}: {exc}",
                          {"question": q["text"], "expect": q["expect"], "expected_intent": q["intent"]})
    r = score_ticket(t, d, q["expect"], q["intent"], q["id"])
    r.data["code"] = t.code
    return r


async def weekly_cases(db, reviews_fixture: Path, *, extra_reviews: list[dict] | None = None):
    """Run one weekly pulse on the fixture (+ injected reviews); returns (cases, run)."""
    from app.weekly.run import run_weekly
    raw = json.loads(Path(reviews_fixture).read_text(encoding="utf-8")) + list(extra_reviews or [])
    try:
        run = await run_weekly(db, now=WEEKLY_NOW, fetcher=lambda p, w, m: [dict(x) for x in raw])
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        msg = f"weekly run raised {type(exc).__name__}: {exc}"
        return [CaseResult(SUITE, n, False, msg) for n in
                ("weekly_completes", "themes_have_ids_and_window", "pulse_le_250_words", "explainer_le_6_bullets")], None
    ok = run.status == "awaiting_approval"
    cases = [CaseResult(SUITE, "weekly_completes", ok, "" if ok else f"run {run.status}: {run.error}",
                        {"run_id": run.id, "status": run.status, "llm_calls": run.llm_calls})]
    themes = db.query(Theme).filter_by(run_id=run.id).all()
    bad = [t.label for t in themes if not t.review_ids or not (t.window_start and t.window_end)]
    cases.append(CaseResult(SUITE, "themes_have_ids_and_window", bool(themes) and not bad,
                            "no themes" if not themes else (f"themes missing ids/window: {bad}" if bad else ""),
                            {"themes": [{"label": t.label, "count": t.count, "review_ids": t.review_ids[:5]}
                                        for t in themes]}))
    words = word_count(run.pulse_text or "")
    cases.append(CaseResult(SUITE, "pulse_le_250_words", bool(run.pulse_text) and words <= 250,
                            f"{words} words", {"pulse": run.pulse_text, "words": words}))
    ex = db.query(Explainer).filter_by(run_id=run.id).order_by(Explainer.id.desc()).first()
    n = len(ex.bullets) if ex else 0
    cases.append(CaseResult(SUITE, "explainer_le_6_bullets", ex is not None and 0 < n <= 6,
                            "no explainer" if ex is None else f"{n} bullets",
                            {"explainer": {"title": ex.title, "bullets": ex.bullets} if ex else None}))
    return cases, run


async def run_feasibility(db, *, questions_path: Path, reviews_fixture: Path, retriever=None) -> SuiteResult:
    if retriever is None:
        from app.corpus.retriever import Retriever
        retriever = Retriever()
    cases = [await _one(db, q, retriever) for q in _load(questions_path)]
    weekly, _ = await weekly_cases(db, reviews_fixture)
    return SuiteResult(SUITE, cases + weekly)


def intent_accuracy(suite: SuiteResult) -> tuple[int, int]:
    rows = [c for c in suite.cases if "expected_intent" in c.data and "intent" in c.data]
    return sum(bool(c.data.get("intent_ok")) for c in rows), len(rows)


__all__ = ["run_feasibility", "score_ticket", "weekly_cases", "intent_accuracy", "bullet_count"]
