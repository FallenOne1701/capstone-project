from pathlib import Path

import pytest

from app.corpus import reference as ref
from app.guard.scope import detect_advice, detect_performance
from app.models import Source

FIX = Path(__file__).parent / "fixtures" / "reference"


@pytest.fixture()
def refs(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "data_processed_dir", tmp_path / "processed")
    return ref.refresh_references(db_session, fetch=False, fixture_dir=FIX)


def test_refresh_creates_reference_sources(db_session, refs):
    rows = db_session.query(Source).filter_by(kind="reference").all()
    assert refs.ok == 4 and len(rows) == 4 and all(r.fetched_at and r.status == "ok" for r in rows)


def test_exit_load_sentence_is_verbatim(refs):
    sents = ref.reference_sentences("exit_load")
    assert sents[0].startswith("Exit load is a fee payable to a mutual fund house")
    doc = ref.load_reference("exit_load")
    assert doc.url.startswith("https://groww.in/help/") and sents[0].rstrip("…") in doc.text


def test_sentences_are_in_scope(refs):
    for topic in ("exit_load", "redemption_charges", "expense_ratio", "brokerage"):
        for s in ref.reference_sentences(topic):
            assert not detect_advice(s) and not detect_performance(s), s
            assert len(s.split()) <= 46


def test_unknown_topic_is_none(refs):
    assert ref.load_reference("nope") is None and ref.reference_sentences("nope") == []


def test_fetch_failure_marks_stale_keeps_text(db_session, refs, monkeypatch):
    def boom(url):
        raise RuntimeError("timeout")
    monkeypatch.setattr(ref, "_download", boom)
    res = ref.refresh_references(db_session, fetch=True)
    assert res.stale == 4
    assert ref.reference_sentences("exit_load")


def test_questions_and_page_chrome_are_not_fact_sentences(db_session, tmp_path, monkeypatch):
    # Live brokerage page: trafilatura glues the help header onto the page's title question.
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "data_processed_dir", tmp_path / "processed")
    doc = ref.ReferenceDoc(topic="brokerage", url="https://groww.in/help/x", title="t", fetched_at="2026-11-17",
                           text="Customer Support Help and Support En हि What fees does Groww charge? "
                                "Groww charges a brokerage fee for executing your trades. Is it free for you? "
                                "The minimum charge is ₹5 per order.")
    import json
    from dataclasses import asdict
    (ref._dir() / "brokerage.json").write_text(json.dumps(asdict(doc), ensure_ascii=False), encoding="utf-8")
    assert ref.reference_sentences("brokerage") == [
        "Groww charges a brokerage fee for executing your trades.", "The minimum charge is ₹5 per order."]
