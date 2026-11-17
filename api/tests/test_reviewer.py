from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.reviewer import review_draft, rewrite_draft
from app.desk.templates import covered_reply

URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
FACTS = FactsResult(status="covered", scheme_id="hdfc-mid-cap-fund-direct-growth", section_title="Exit Load",
                    fact="Exit load of 1% if redeemed within 1 year.", citation=URL, last_checked="2026-11-17",
                    searched=["x"])


def draft(reply, disposition="reply", citation=URL, last_checked="2026-11-17", why="Facts covered."):
    return OrchestratorOutput(reply=reply, citation=citation, last_checked=last_checked, disposition=disposition,
                              disagreement=False, routing_note=RoutingNote(team="t", priority="P3", why=why))


def test_good_covered_draft_passes():
    r = review_draft(draft(covered_reply(FACTS.fact, URL, "2026-11-17")), facts=FACTS, round=1)
    assert r.status == "pass", r.failures


def test_advice_fails_then_rewrite_passes():
    bad = draft("Exit load is 1%. You should buy now. Source: " + URL + " Last checked: 2026-11-17.")
    r1 = review_draft(bad, facts=FACTS, round=1)
    assert r1.status == "fail" and {f.check for f in r1.failures} >= {"advice"}
    fixed = rewrite_draft(bad, facts=FACTS, failures=r1.failures)
    assert review_draft(fixed, facts=FACTS, round=2).status == "pass"


def test_four_sentences_fail_shape():
    r = review_draft(draft("A. B. C. D. Source: " + URL + " Last checked: 2026-11-17."), facts=FACTS, round=1)
    assert "shape" in {f.check for f in r.failures}


def test_wrong_citation_fails():
    r = review_draft(draft(covered_reply(FACTS.fact, "https://groww.in/x", "2026-11-17"), citation="https://groww.in/x"),
                     facts=FACTS, round=1)
    assert "citation" in {f.check for f in r.failures}


def test_handoff_with_link_fails_and_second_round_blocks():
    d = draft("Not covered. See " + URL, disposition="handoff", citation=None, last_checked=None)
    assert review_draft(d, facts=None, round=1).status == "fail"
    assert review_draft(d, facts=None, round=2).status == "blocked"


def test_pii_in_routing_note_fails():
    d = draft(covered_reply(FACTS.fact, URL, "2026-11-17"), why="user phone 9876543210")
    assert "pii" in {f.check for f in review_draft(d, facts=FACTS, round=1).failures}
