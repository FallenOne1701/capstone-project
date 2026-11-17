import pytest

from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.templates import ADVICE_REFUSAL, ACCOUNT_REPLY, PERFORMANCE_REFUSAL, covered_reply, not_covered_reply
from app.guard.scope import check_output


def test_covered_requires_citation():
    with pytest.raises(ValueError):
        FactsResult(status="covered", searched=[], fact="x")


def test_account_disposition_allowed():
    o = OrchestratorOutput(reply="x", last_checked=None, citation=None, disposition="account", disagreement=False,
                           routing_note=RoutingNote(team="t", priority="P2", why="w"))
    assert o.disposition == "account"


@pytest.mark.parametrize("text", [
    ADVICE_REFUSAL, PERFORMANCE_REFUSAL, ACCOUNT_REPLY,
    not_covered_reply(["hdfc-mid-cap-fund-direct-growth:exit_load"]),
    covered_reply("Exit load of 1% if redeemed within 1 year..", "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth", "2026-11-17"),
])
def test_templates_pass_scope_filter(text):
    assert check_output(text, kind="reply") == []
