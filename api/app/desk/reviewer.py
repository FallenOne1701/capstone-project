"""Outgoing-draft reviewer: hard checks in code, one deterministic rewrite, then block."""

from __future__ import annotations

import re

from app.desk.contracts import FactsResult, OrchestratorOutput, ReviewerFailure, ReviewerResult, RoutingNote
from app.desk.templates import covered_reply
from app.guard.pii import redact
from app.guard.scope import check_output, strip_advice_and_performance, truncate_sentences

_URL = re.compile(r"https?://[^\s\]\)>]+")
COVERED = ("reply", "escalate", "disagree")


def _clean(u: str) -> str:
    return u.rstrip(".,);")


def _citation_failures(d: OrchestratorOutput, facts: FactsResult | None) -> list[ReviewerFailure]:
    out: list[ReviewerFailure] = []
    urls = [_clean(u) for u in _URL.findall(d.reply)]
    if len(urls) > 1:
        out.append(ReviewerFailure(check="citation", detail=f"multiple links: {len(urls)}"))
    if d.disposition in COVERED:
        if not d.citation:
            out.append(ReviewerFailure(check="citation", detail="covered draft missing citation"))
        elif d.citation not in urls:
            out.append(ReviewerFailure(check="citation", detail="covered reply text must contain its citation link"))
        if facts is not None and facts.status == "covered" and d.citation and d.citation != facts.citation:
            out.append(ReviewerFailure(check="citation", detail="citation does not match Facts source"))
        if urls and d.citation and any(u != d.citation for u in urls):
            out.append(ReviewerFailure(check="citation", detail="reply link differs from citation"))
    elif urls:
        out.append(ReviewerFailure(check="citation", detail=f"{d.disposition} draft must not include links"))
    return out


def _shape_failures(d: OrchestratorOutput) -> list[ReviewerFailure]:
    if d.disposition in COVERED and (not d.last_checked or d.last_checked not in d.reply):
        return [ReviewerFailure(check="shape", detail="covered reply must include last_checked date")]
    return []


def review_draft(draft: OrchestratorOutput, *, facts: FactsResult | None, round: int) -> ReviewerResult:
    failures = _citation_failures(draft, facts) + _shape_failures(draft)
    failures += [ReviewerFailure(check=v.check, detail=v.detail) for v in check_output(draft.reply, kind="reply")]
    failures += [ReviewerFailure(check=v.check, detail="routing note: " + v.detail)
                 for v in check_output(draft.routing_note.why, kind="pulse") if v.check != "shape"]
    seen: set[str] = set()
    unique = [f for f in failures if not (f.check in seen or seen.add(f.check))]
    status = "pass" if not unique else ("blocked" if round >= 2 else "fail")
    return ReviewerResult(status=status, round=round, failures=unique)


def rewrite_draft(draft: OrchestratorOutput, *, facts: FactsResult | None,
                  failures: list[ReviewerFailure]) -> OrchestratorOutput:
    checks = {f.check for f in failures}
    reply, why = draft.reply, draft.routing_note.why
    citation, last_checked = draft.citation, draft.last_checked
    covered = facts is not None and facts.status == "covered"
    if covered and draft.disposition in COVERED and checks & {"citation", "shape", "advice", "performance"}:
        citation, last_checked = facts.citation, facts.last_checked
        reply = covered_reply(facts.fact, facts.citation, facts.last_checked)
    else:
        if checks & {"advice", "performance"}:
            reply = strip_advice_and_performance(reply)
        if "citation" in checks and draft.disposition not in COVERED:
            reply = _URL.sub("", reply).strip()
    reply = redact(truncate_sentences(reply, 3)).text
    why = redact(strip_advice_and_performance(why) or why).text
    return OrchestratorOutput(reply=reply, citation=citation, last_checked=last_checked,
                              disposition=draft.disposition, disagreement=draft.disagreement,
                              routing_note=RoutingNote(team=draft.routing_note.team,
                                                       priority=draft.routing_note.priority, why=why))
