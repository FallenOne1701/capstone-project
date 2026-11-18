"""Three specialists in parallel (LangGraph) → merge → reviewer (one rewrite)."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.corpus.retriever import Retriever
from app.desk.compliance import run_compliance
from app.desk.contracts import (ComplianceResult, FactsResult, OrchestratorOutput, PatternResult,
                                ReviewerResult, RoutingNote, ThemeStat)
from app.desk.facts import run_facts
from app.desk.pattern import run_pattern, team_for
from app.desk.reviewer import review_draft, rewrite_draft
from app.desk.templates import ACCOUNT_REPLY, ADVICE_REFUSAL, OUT_OF_SCOPE_REPLY, PERFORMANCE_REFUSAL, covered_reply, not_covered_reply
from app.intent.classifier import IntentResult

SURGE_RECENT = 40


class DeskResult(BaseModel):
    draft: OrchestratorOutput
    review: ReviewerResult
    facts: FactsResult
    pattern: PatternResult
    compliance: ComplianceResult


class _S(TypedDict, total=False):
    text: str
    pii: list[str]
    intent: IntentResult
    ctx: dict[str, Any]
    facts: FactsResult
    pattern: PatternResult
    compliance: ComplianceResult


async def _facts(s: _S):
    c = s["ctx"]
    ids = s["intent"].scheme_ids
    return {"facts": await asyncio.to_thread(run_facts, s["text"], c["retriever"], c["last_checked"],
                                             ids[0] if len(ids) == 1 else None)}


async def _pattern(s: _S):
    return {"pattern": run_pattern(s["text"], s["ctx"]["themes"], today=s["ctx"]["today"])}


async def _compliance(s: _S):
    return {"compliance": run_compliance(s["text"], s["pii"], s["intent"])}


async def _join(s: _S):
    return {}


def _build():
    g = StateGraph(_S)
    for name, fn in (("facts", _facts), ("pattern", _pattern), ("compliance", _compliance), ("join", _join)):
        g.add_node(name, fn)
    for n in ("facts", "pattern", "compliance"):
        g.add_edge(START, n)
        g.add_edge(n, "join")
    g.add_edge("join", END)
    return g.compile()


_GRAPH = _build()


def _disposition(intent: IntentResult, f: FactsResult, p: PatternResult, c: ComplianceResult) -> str:
    if c.advice_refusal or intent.intent == "out_of_scope":
        return "refuse"
    if intent.intent == "account_issue":
        return "account"
    if f.status == "not_covered":
        return "handoff"
    if p.signal == "rising" and p.recent_count >= SURGE_RECENT:
        return "disagree"
    if p.signal in ("recurring", "rising"):
        return "escalate"
    return "reply"


def _priority(signal: str, disposition: str) -> str:
    if signal == "rising":
        return "P1"
    if disposition in ("escalate", "disagree", "account") or signal == "recurring":
        return "P2"
    return "P3"


def _why(disp: str, f: FactsResult, p: PatternResult) -> str:
    if disp == "refuse":
        return f"Compliance refusal (theme {p.theme_id}, signal={p.signal}, count={p.count})."
    if disp == "account":
        return "Account-specific issue routed to customer support; no account data accessed."
    if disp == "handoff":
        return f"Facts not covered for theme {p.theme_id}. Searched: {', '.join(f.searched[:12]) or 'none'}."
    if disp == "disagree":
        return (f"Corpus answers {f.scheme_id} {f.section_title}, but {p.recent_count} recent reviews match "
                f"{p.theme_id}; ticket stays open.")
    if disp == "escalate":
        return (f"Facts covered for {f.scheme_id} {f.section_title}. Theme {p.theme_id} is {p.signal} across "
                f"{p.count} reviews from {p.window.start} to {p.window.end}.")
    return f"Facts covered for {f.scheme_id} {f.section_title}. Theme {p.theme_id} is {p.signal} (count={p.count})."


def merge_draft(intent: IntentResult, f: FactsResult, p: PatternResult, c: ComplianceResult,
                themes: list[ThemeStat]) -> OrchestratorOutput:
    disp = _disposition(intent, f, p, c)
    citation = last_checked = None
    if disp == "refuse":
        if intent.intent == "out_of_scope" and not c.advice_refusal:
            reply = OUT_OF_SCOPE_REPLY
        else:
            reply = PERFORMANCE_REFUSAL if "performance_claim" in c.flags else ADVICE_REFUSAL
    elif disp == "account":
        reply = ACCOUNT_REPLY
    elif disp == "handoff":
        reply = not_covered_reply(f.searched)
    else:
        reply = covered_reply(f.fact, f.citation, f.last_checked)
        citation, last_checked = f.citation, f.last_checked
    team = "Customer support" if disp == "account" else team_for(p.theme_id, themes)
    return OrchestratorOutput(reply=reply, citation=citation, last_checked=last_checked, disposition=disp,
                              disagreement=disp == "disagree",
                              routing_note=RoutingNote(team=team, priority=_priority(p.signal, disp), why=_why(disp, f, p)))


async def run_desk(redacted_text: str, pii_types: list[str], intent: IntentResult, *, retriever: Retriever,
                   themes: list[ThemeStat], last_checked: Callable[[str], str | None], today: date) -> DeskResult:
    ctx = {"retriever": retriever, "themes": themes, "last_checked": last_checked, "today": today}
    s = await _GRAPH.ainvoke({"text": redacted_text, "pii": list(pii_types), "intent": intent, "ctx": ctx})
    draft = merge_draft(intent, s["facts"], s["pattern"], s["compliance"], themes)
    review = review_draft(draft, facts=s["facts"], round=1)
    if review.status == "fail":
        draft = rewrite_draft(draft, facts=s["facts"], failures=review.failures)
        review = review_draft(draft, facts=s["facts"], round=2)
    return DeskResult(draft=draft, review=review, facts=s["facts"], pattern=s["pattern"], compliance=s["compliance"])
