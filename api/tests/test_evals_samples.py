"""Plan 4b Task 7: README samples — reviews CSV and sample Q&As from an eval run."""

import csv
import io

from app.evals.samples import pick_qas, reviews_csv


def test_reviews_csv_redacts_and_has_header():
    rows = [{"id": "rv_abc", "date": "2026-11-15", "rating": 1, "app_version": "26.11.0",
             "text_redacted": "call me on 9876543210, app crashes"}]
    out = list(csv.reader(io.StringIO(reviews_csv(rows))))
    assert out[0] == ["review_id", "date", "rating", "text_redacted", "app_version"]
    assert "9876543210" not in out[1][3] and "[PHONE]" in out[1][3]


def _case(cid, intent, passed=True, expect="answer"):
    return {"case_id": cid, "passed": passed,
            "data": {"question": f"q {cid}", "reply": f"r {cid}", "citation": "https://groww.in/x",
                     "last_checked": "2026-11-19", "intent": intent, "expect": expect}}


def test_pick_qas_distinct_intents():
    result = {"suites": [{"name": "feasibility", "cases": [
        _case("a", "fee_question"), _case("b", "fee_question"), _case("c", "fund_fact"),
        _case("d", "fund_fact", passed=False), _case("e", "out_of_scope", expect="refuse"),
        _case("f", "fund_fact", expect="not_covered")]}]}
    qas = pick_qas(result, n=3)
    assert [q["question"] for q in qas] == ["q a", "q c", "q e"]
    assert qas[0] == {"question": "q a", "answer": "r a", "source": "https://groww.in/x", "last_checked": "2026-11-19",
                      "kind": "answer"}
