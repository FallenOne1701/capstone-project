import asyncio
from datetime import date

from app.models import Review
from app.weekly.themes import assign_themes, build_themes
from app.weekly.vocab import THEME_VOCAB


def rid(i):
    return "rv_" + "".join("abcdefghij"[int(c)] for c in f"{i:010d}")   # letters only, like real ids


def _r(i, text, d=date(2026, 11, 15), rating=1):
    return Review(id=rid(i), rating=rating, date=d, text_redacted=text)


REVIEWS = [
    _r(1, "App crashes after update"), _r(2, "Not working, lag and blank screen"),
    _r(3, "Exit load deducted, confusing charge"), _r(4, "Brokerage fee too high"),
    _r(5, "Support no response to my ticket"), _r(6, "Unable to sell, order stuck", d=date(2026, 10, 1)),
    _r(7, "Chart shows wrong price"), _r(8, "nice", rating=5),
]


def test_default_actions_pass_scope_filter():
    from app.guard.scope import check_output
    from app.weekly.vocab import DEFAULT_ACTIONS
    for a in DEFAULT_ACTIONS.values():
        assert [v.check for v in check_output(a, kind="pulse")] == [], a


def test_assign_without_llm_covers_all_and_uses_vocab():
    assign, calls = asyncio.run(assign_themes(REVIEWS))
    assert calls == 0 and set(assign) == {r.id for r in REVIEWS} - {rid(8)}   # "nice" has no theme signal
    assert set(assign.values()) <= set(THEME_VOCAB)
    assert assign[rid(3)] == "fees_funding" and assign[rid(1)] == "app_reliability"


def test_build_themes_capped_ranked_traced():
    assign, _ = asyncio.run(assign_themes(REVIEWS))
    themes = build_themes(assign, REVIEWS, window_start=date(2026, 9, 22), window_end=date(2026, 11, 17),
                          today=date(2026, 11, 17))
    assert 1 <= len(themes) <= 5 and [t.rank for t in themes] == list(range(1, len(themes) + 1))
    assert all(t.count == len(t.review_ids) > 0 for t in themes)
    assert sum(t.count for t in themes) == len(REVIEWS) - 1
    assert all(t.window_start == date(2026, 9, 22) and t.window_end == date(2026, 11, 17) for t in themes)
    trading = next(t for t in themes if t.theme_id == "trading_orders")
    assert trading.recent_count == 0  # its only review is from Oct 1


def test_llm_labels_only_ambiguous_and_capped(monkeypatch):
    from app.weekly import themes as th
    seen = []

    async def fake_llm(system, user, *, fast=False):
        ids = [line.split("|")[0].strip() for line in user.splitlines() if line.startswith("rv_")]
        seen.append(len(ids))
        return {"labels": [{"id": i, "theme_id": "customer_support"} for i in ids]}
    monkeypatch.setattr(th, "complete_json", fake_llm)
    monkeypatch.setattr(th, "llm_enabled", lambda: True)
    many = [_r(100 + i, "meh okay") for i in range(60)]
    assign, calls = asyncio.run(assign_themes(many, max_llm=24))
    assert calls == 2 and sum(seen) == 24 and set(assign) == {r.id for r in many[:24]}   # rest: no signal, unthemed
