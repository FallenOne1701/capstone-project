import asyncio

import pytest

from app.intent import cache as ic
from app.intent.classifier import IntentResult, classify_intent
from app.tickets.service import create_ticket, preview, process_ticket
from tests.conftest_corpus import build_fixture_retriever


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("ic"))


@pytest.fixture()
def calls(monkeypatch):
    """Counts real classifications (the cache's only way to the classifier)."""
    ic.intent_cache.clear()
    seen: list[str] = []

    async def counting(text):
        seen.append(text)
        return await classify_intent(text)

    monkeypatch.setattr(ic, "classify_intent", counting)
    yield seen
    ic.intent_cache.clear()


def run(coro):
    return asyncio.run(coro)


def test_preview_ask_and_worker_classify_once(db_session, calls, retriever):
    text = "What is the expense ratio of HDFC Mid Cap Fund?"
    run(preview(text))
    t, _ = run(create_ticket(db_session, text))
    run(process_ticket(db_session, t.id, retriever=retriever))
    assert len(calls) == 1


def test_different_text_classifies_again(db_session, calls):
    run(preview("What is the expense ratio of HDFC Mid Cap Fund?"))
    run(preview("What is the exit load of HDFC Small Cap Fund?"))
    assert len(calls) == 2


def _intent():
    return IntentResult(intent="fee_question", scheme_ids=[], fact_key=None, language="en", confidence="rule")


def test_entry_expires():
    now = [0.0]
    c = ic.IntentCache(ttl_s=10, clock=lambda: now[0])
    c.put("a", _intent())
    now[0] = 9
    assert c.get("a") is not None
    now[0] = 11
    assert c.get("a") is None


def test_bounded_size():
    c = ic.IntentCache(max_items=2)
    for k in ("a", "b", "c"):
        c.put(k, _intent())
    assert c.get("a") is None and c.get("b") is not None and c.get("c") is not None


def test_cached_result_is_a_copy():
    c = ic.IntentCache()
    c.put("a", _intent())
    got = c.get("a")
    got.scheme_ids.append("x")
    assert c.get("a").scheme_ids == []


def test_empty_cache_after_redeploy_gives_same_answer(db_session, calls, retriever):
    text = "What is the expense ratio of HDFC Mid Cap Fund?"
    t1, _ = run(create_ticket(db_session, text))
    d1 = run(process_ticket(db_session, t1.id, retriever=retriever))
    t2, _ = run(create_ticket(db_session, text))
    ic.intent_cache.clear()   # a redeploy between Send and the worker
    d2 = run(process_ticket(db_session, t2.id, retriever=retriever))
    assert (d2.reply, d2.citation) == (d1.reply, d1.citation)


def test_chosen_fund_wins_over_cached_intent(db_session, calls, retriever):
    text = "exit load of HDFC Mid Cap and HDFC Small Cap"
    run(preview(text))   # caches both funds
    t, _ = run(create_ticket(db_session, text, scheme_id="hdfc-small-cap-fund-direct-growth"))
    d = run(process_ticket(db_session, t.id, retriever=retriever))
    assert d.citation.endswith("hdfc-small-cap-fund-direct-growth")
