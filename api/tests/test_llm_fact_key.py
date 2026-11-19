"""Eval run 1 (u01, u02): when the AI classifies unclear wording, it also names the fact asked, and retrieval uses it."""

import asyncio
from pathlib import Path

import pytest

from app.config import get_settings
from app.intent import classifier

FIX = Path(__file__).parent / "fixtures"


def _fake_llm(monkeypatch, reply):
    async def fake(system, text, **kw):
        return reply
    monkeypatch.setattr(classifier, "complete_json", fake)


def test_llm_fact_key_is_used_when_no_keyword(monkeypatch):
    _fake_llm(monkeypatch, {"intent": "fee_question", "fact_key": "exit_load"})
    r = asyncio.run(classifier.classify_intent("how much does groww cut when i take my money out of the mid cap one early"))
    assert r.intent == "fee_question" and r.fact_key == "exit_load" and r.confidence == "llm"


def test_llm_fact_key_outside_the_known_facts_is_ignored(monkeypatch):
    _fake_llm(monkeypatch, {"intent": "fund_fact", "fact_key": "fund_manager"})
    r = asyncio.run(classifier.classify_intent("who runs the mid cap one"))
    assert r.fact_key is None


def test_run_facts_passes_the_fact_key_to_retrieval():
    from app.desk.facts import run_facts
    seen = {}

    class R:
        def retrieve(self, q, **kw):
            seen.update(kw)
            from types import SimpleNamespace as NS
            return NS(status="none", winner=None, hints=NS(fact_key=kw.get("fact_key"), scheme_ids=()), candidates=[])
    run_facts("q", R(), lambda u: None, None, fact_key="expense_ratio")
    assert seen.get("fact_key") == "expense_ratio"


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")


def test_retriever_uses_a_given_fact_key(corpus):
    from app.corpus.retriever import Retriever
    q = "how much does groww cut when i take my money out of HDFC Mid Cap Fund early"
    r = Retriever().retrieve(q, fact_key="exit_load")
    assert r.hints.fact_key == "exit_load"
    assert r.winner is not None and r.winner.fact_key == "exit_load"
