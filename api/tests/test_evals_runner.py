"""Plan 4b Task 1: eval runner, result files and the score card."""

import json
from datetime import date

from app.evals.result import CaseResult, SuiteResult, next_result_path, score_card, write_result


def test_next_result_path_increments(tmp_path):
    (tmp_path / "run-1-2026-11-19.json").write_text("{}")
    (tmp_path / "run-2-2026-11-20.json").write_text("{}")
    assert next_result_path(tmp_path, date(2026, 11, 20)).name == "run-3-2026-11-20.json"


def test_next_result_path_starts_at_one(tmp_path):
    assert next_result_path(tmp_path / "new", date(2026, 11, 19)).name == "run-1-2026-11-19.json"


def test_write_result_roundtrip(tmp_path):
    s = SuiteResult("feasibility", [CaseResult("feasibility", "q1", True, data={"reply": "x"})])
    p = write_result(tmp_path, [s], today=date(2026, 11, 19), meta={"use_llm": True})
    body = json.loads(p.read_text(encoding="utf-8"))
    assert body["meta"]["use_llm"] is True
    assert body["suites"][0]["passed"] == 1 and body["suites"][0]["total"] == 1
    assert body["suites"][0]["cases"][0]["data"] == {"reply": "x"}


def test_score_card_lists_failures():
    s = SuiteResult("feasibility", [CaseResult("feasibility", "q1", True),
                                    CaseResult("feasibility", "q2", False, "no citation")])
    card = score_card([s])
    assert "feasibility  1/2" in card
    assert "q2" in card and "no citation" in card
