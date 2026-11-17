from __future__ import annotations

from typing import Callable

from app.corpus.retriever import Retriever
from app.desk.contracts import FactsResult


def run_facts(redacted_text: str, retriever: Retriever, last_checked: Callable[[str], str | None]) -> FactsResult:
    r = retriever.retrieve(redacted_text)
    if r.status == "ok" and r.winner is not None:
        w = r.winner
        checked = last_checked(w.source_url) or (w.ingested_at or "")[:10] or None
        return FactsResult(status="covered", scheme_id=w.scheme_id, section_title=w.page_or_section,
                           fact=w.text, citation=w.source_url, last_checked=checked,
                           searched=[f"{w.scheme_id}:{w.fact_key}"])
    searched = [f"{c.scheme_id}:{c.fact_key}" for c in r.candidates]
    if not searched:
        searched = list(r.hints.scheme_ids) or ["all 15 HDFC scheme pages"]
    return FactsResult(status="not_covered", searched=searched)
