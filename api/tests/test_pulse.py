import asyncio
from datetime import date

from app.link.question_keys import RepeatedQuestion
from app.models import Review
from app.weekly.fee_topics import FeeConfusion
from app.weekly.pulse import action_ideas, compose_pulse, select_quotes, validate_pulse
from app.weekly.themes import ThemeOut

W0, W1 = date(2026, 9, 22), date(2026, 11, 17)


def rid(i):
    return "rv_" + "".join("abcdefghij"[int(c)] for c in f"{i:010d}")


def _rev(i, text, rating=1, d=date(2026, 11, 15)):
    return Review(id=rid(i), rating=rating, date=d, text_redacted=text)


REVS = {r.id: r for r in [
    _rev(1, "App crashes every time I open the portfolio screen after the latest update"),
    _rev(2, "You should sell this app, it gave 20% returns then crashed"),        # advice+perf → never quoted
    _rev(3, "Exit load deducted on redemption and nobody explained the exit load to me"),
    _rev(4, "Support never replied to my ticket for two weeks"),
]}


def _themes(n=3):
    base = [ThemeOut("app_reliability", "App reliability & updates", 2, 2, [rid(1), rid(2)], W0, W1, 1),
            ThemeOut("fees_funding", "Fees, charges & funding", 1, 1, [rid(3)], W0, W1, 2),
            ThemeOut("customer_support", "Customer support", 1, 1, [rid(4)], W0, W1, 3)]
    return base[:n]


def _pulse(themes, repeated=None, fee=None):
    quotes = select_quotes(themes, REVS)
    actions, _ = asyncio.run(action_ideas(themes, quotes))
    return compose_pulse(week_end=W1, window_start=W0, window_end=W1, review_count=4, themes=themes, quotes=quotes,
                         repeated=repeated or [], fee=fee or FeeConfusion("exit_load", [rid(3)], 2),
                         actions=actions)


def test_quotes_verbatim_and_safe():
    quotes = select_quotes(_themes(), REVS)
    assert [q.theme_id for q in quotes] == ["app_reliability", "fees_funding", "customer_support"]
    assert all(q.text.rstrip("…").strip() in REVS[q.review_id].text_redacted for q in quotes)
    assert all(q.review_id != rid(2) for q in quotes)


def test_actions_default_to_three_without_llm():
    actions, calls = asyncio.run(action_ideas(_themes(), select_quotes(_themes(), REVS)))
    assert len(actions) == 3 and calls == 0


def test_pulse_valid_and_capped():
    rq = [RepeatedQuestion("fee_question:exit_load", "Fee question · Exit load", 6, date(2026, 11, 10), W1, ["a"] * 6)]
    text = _pulse(_themes(), repeated=rq)
    assert validate_pulse(text) == [], validate_pulse(text)
    assert "Fee question · Exit load: 6 questions" in text and "2026-11-10" in text
    assert f"({rid(1)})" in text


def test_quiet_week_one_theme_no_repeats_still_valid():
    text = _pulse(_themes(1), fee=FeeConfusion("exit_load"))
    assert validate_pulse(text) == [] and "No question reached" in text and "0 reviews and 0 questions" in text


def test_long_inputs_are_trimmed_to_cap():
    long_rev = {rid(i): _rev(i, " ".join(["slowness"] * 80)) for i in range(10, 13)}
    themes = [ThemeOut("app_reliability", "App reliability & updates", 3, 3, list(long_rev), W0, W1, 1)]
    rq = [RepeatedQuestion(f"fee_question:k{i}", "Fee question · " + "x" * 40, 9, W0, W1, []) for i in range(8)]
    quotes = select_quotes(themes, long_rev)
    actions, _ = asyncio.run(action_ideas(themes, quotes))
    text = compose_pulse(week_end=W1, window_start=W0, window_end=W1, review_count=3, themes=themes, quotes=quotes,
                         repeated=rq, fee=FeeConfusion("exit_load"), actions=actions)
    assert validate_pulse(text) == []


def test_fee_counts_are_pluralised_correctly():
    # Live run 4 printed "67 reviews and 1 questions".
    one = FeeConfusion("brokerage", [rid(3)], 1)
    text = _pulse(_themes(), fee=one)
    assert "1 reviews" not in text and "1 questions" not in text
    assert "Brokerage & charges: 1 review and 1 question → explainer below." in text
