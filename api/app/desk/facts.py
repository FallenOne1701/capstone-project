from __future__ import annotations

from typing import Callable

from app.corpus.retriever import Retriever
from app.desk.contracts import FactsResult


def run_facts(redacted_text: str, retriever: Retriever, last_checked: Callable[[str], str | None],
              scheme_id: str | None = None, fact_key: str | None = None) -> FactsResult:
    r = retriever.retrieve(redacted_text, scheme_id=scheme_id, fact_key=fact_key)
    # Covered only when the asked fact was detected and is exactly the retrieved one; a scheme-only
    # question ("AUM of mid cap") would otherwise get whichever chunk is nearest.
    if r.status == "ok" and r.winner is not None and r.hints.fact_key and r.winner.fact_key == r.hints.fact_key:
        w = r.winner
        checked = last_checked(w.source_url) or (w.ingested_at or "")[:10] or None
        return FactsResult(status="covered", scheme_id=w.scheme_id, section_title=w.page_or_section,
                           fact=w.text, citation=w.source_url, last_checked=checked,
                           searched=[f"{w.scheme_id}:{w.fact_key}"])
    searched = [f"{c.scheme_id}:{c.fact_key}" for c in r.candidates]
    if not searched:
        searched = list(r.hints.scheme_ids) or ["all 15 HDFC scheme pages"]
    return FactsResult(status="not_covered", searched=searched)
