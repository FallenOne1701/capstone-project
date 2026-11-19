"""Edit isolation: snapshot every table, do ONE operation, snapshot again, and require exactly the expected change.

Google is never called: the Doc/Gmail executors are swapped for a stub only while this suite runs.
"""

from __future__ import annotations

from datetime import date

from app.approvals import executors
from app.approvals.service import approve, edit_draft, reject
from app.evals.result import CaseResult, SuiteResult
from app.evals.snapshot import diff, snapshot
from app.models import Action, Draft, Explainer, Ticket, WeeklyRun

SUITE = "isolation"
OTHER_CODE = "EVAL-ISO-T3"   # a bystander ticket nothing should touch
ACTOR = "eval"


def _ticket(db, code: str) -> tuple[Ticket, Draft, Action]:
    t = Ticket(code=code, question_redacted="What is the exit load of HDFC Mid Cap Fund?", status="in_review",
               intent="fee_question")
    db.add(t)
    db.flush()
    d = Draft(ticket_id=t.id, reply="The exit load is 1% if redeemed within 1 year. Source: https://groww.in/x "
              "Last checked: 2026-11-19.", citation="https://groww.in/x", last_checked="2026-11-19",
              disposition="reply", routing_team="desk", routing_priority="P3", routing_why="fee fact",
              review_status="pass")
    db.add(d)
    db.flush()
    a = Action(type="reply_publish", target_label=f"Reply to ticket {code}", target_ref=code, draft_id=d.id)
    db.add(a)
    return t, d, a


def _seed(db) -> dict:
    t1, d1, a1 = _ticket(db, "EVAL-ISO-T1")
    t2, _, a2 = _ticket(db, "EVAL-ISO-T2")
    _ticket(db, OTHER_CODE)
    run = WeeklyRun(status="awaiting_approval", window_start=date(2026, 11, 9), window_end=date(2026, 11, 16),
                    pulse_text="Weekly pulse")
    db.add(run)
    db.flush()
    ex = Explainer(run_id=run.id, topic="exit_load", title="Exit load", bullets=["One fact."],
                   last_checked="2026-11-19", status="draft")
    doc = Action(type="doc_append", target_label="Append to the weekly pulse Google Doc", target_ref="DOC-EVAL",
                 content="pulse", source_ref=f"weekly_run:{run.id}")
    mail = Action(type="email_draft", target_label="Gmail draft to the product team, not sent",
                  target_ref="team", content="pulse", source_ref=f"weekly_run:{run.id}")
    db.add_all([ex, doc, mail])
    db.commit()
    return {"t1": t1.id, "t2": t2.id, "d1": d1.id, "a1": a1.id, "a2": a2.id, "doc": doc.id, "mail": mail.id,
            "ex": ex.id}


def _check(db, case_id: str, op, expect: dict[str, list | int]) -> CaseResult:
    """expect: table -> exact list of changed keys, or an int = number of NEW rows (audit_log)."""
    before = snapshot(db)
    try:
        op()
    except Exception as exc:  # noqa: BLE001
        return CaseResult(SUITE, case_id, False, f"operation raised {type(exc).__name__}: {exc}")
    got = diff(before, snapshot(db))
    problems = []
    for table in sorted(set(got) | set(expect)):
        want, have = expect.get(table), got.get(table, [])
        if isinstance(want, int):
            new = [k for k in have if k not in before.get(table, {})]
            if len(new) != want or len(new) != len(have):
                problems.append(f"{table}: expected {want} new row(s), got changes {have}")
        elif sorted(have, key=str) != sorted(want or [], key=str):
            problems.append(f"{table}: expected {want or []}, got {have}")
    return CaseResult(SUITE, case_id, not problems, "; ".join(problems), {"diff": {k: [str(x) for x in v]
                                                                                   for k, v in got.items()}})


def run_isolation(db) -> SuiteResult:
    ids = _seed(db)
    stub_calls: list[int] = []
    saved = {k: executors.EXECUTORS[k] for k in ("doc_append", "email_draft")}
    for k in saved:
        executors.EXECUTORS[k] = lambda _db, a: stub_calls.append(a.id) or f"stub:{a.id}"
    try:
        cases = [
            _check(db, "edit_draft",
                   lambda: edit_draft(db, ids["d1"], "The exit load is 1% if redeemed within 1 year. Source: "
                                      "https://groww.in/x Last checked: 2026-11-19.", ACTOR),
                   {"drafts": [ids["d1"]], "audit_log": 1}),
            _check(db, "approve_reply", lambda: approve(db, ids["a1"], ACTOR),
                   {"actions": [ids["a1"]], "tickets": [ids["t1"]], "audit_log": 2}),
            _check(db, "reject_reply", lambda: reject(db, ids["a2"], ACTOR),
                   {"actions": [ids["a2"]], "tickets": [ids["t2"]], "audit_log": 1}),
            _check(db, "approve_doc_append", lambda: approve(db, ids["doc"], ACTOR),
                   {"actions": [ids["doc"]], "explainers": [ids["ex"]], "audit_log": 3}),
            _check(db, "reject_email_draft", lambda: reject(db, ids["mail"], ACTOR),
                   {"actions": [ids["mail"]], "audit_log": 1}),
        ]
    finally:
        executors.EXECUTORS.update(saved)
    if stub_calls != [ids["doc"]]:
        cases[3] = CaseResult(SUITE, "approve_doc_append", False,
                              f"executor calls {stub_calls}: approving the Doc must run only the Doc write")
    return SuiteResult(SUITE, cases)
