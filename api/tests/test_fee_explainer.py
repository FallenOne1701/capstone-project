from pathlib import Path

import pytest

from app.guard.scope import bullet_count
from app.weekly.explainer import build_explainer, render_explainer, validate_explainer

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    return db_session


@pytest.mark.parametrize("topic", ["exit_load", "expense_ratio", "redemption_charges", "brokerage"])
def test_each_topic_builds_valid_explainer(corpus, topic):
    d = build_explainer(corpus, topic)
    assert validate_explainer(d) == [], validate_explainer(d)
    assert 1 <= len(d.bullets) <= 6 and len({b["url"] for b in d.bullets}) >= 2
    md = render_explainer(d)
    assert bullet_count(md) == len(d.bullets) and f"Last checked: {d.last_checked}" in md


def test_exit_load_uses_scheme_facts_with_their_urls(corpus):
    d = build_explainer(corpus, "exit_load", schemes=["hdfc-mid-cap-fund-direct-growth"])
    scheme = [b for b in d.bullets if "mid-cap" in b["url"]]
    assert scheme and "exit load" in scheme[0]["text"].lower()


def test_validate_catches_bad_drafts(corpus):
    d = build_explainer(corpus, "exit_load")
    d.bullets = d.bullets[:1]
    assert any("distinct" in p for p in validate_explainer(d))
    d.bullets = [{"text": "You should buy now.", "url": "https://groww.in/x"}] * 7
    probs = validate_explainer(d)
    assert any("bullets" in p for p in probs) and any("advice" in p for p in probs)
