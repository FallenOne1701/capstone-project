"""Fee/charge confusion topics shared by question keys, review mining and explainers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FEE_TOPICS: dict[str, tuple[str, ...]] = {
    "exit_load": (r"exit[\s-]?load",),
    "expense_ratio": (r"expense[\s-]?ratio", r"\bter\b", r"total expense"),
    "redemption_charges": (r"(?:redeem\w*|redemption|withdraw\w*).{0,40}(?:charge\w*|fee\w*|deduct\w*|cut)",
                           r"(?:charge\w*|fee\w*|deduct\w*).{0,40}(?:redeem\w*|redemption|withdraw\w*)"),
    "brokerage": (r"brokerage", r"\bdp charge", r"hidden charge", r"\bcharges?\b", r"\bfees?\b"),
}
TOPIC_LABELS = {"exit_load": "Exit load", "expense_ratio": "Expense ratio",
                "redemption_charges": "Redemption charges", "brokerage": "Brokerage & charges"}
_GENERIC = {r"\bcharges?\b", r"\bfees?\b"}   # fine for mining reviews, too loose to pick an answer
_COMPILED = {t: [(re.compile("(?i)" + p), p in _GENERIC) for p in ps] for t, ps in FEE_TOPICS.items()}


def topic_of(text: str, *, strict: bool = False) -> str | None:
    """strict=True (Link 2 answering) ignores the bare 'charge'/'fee' catch-alls."""
    for topic, pats in _COMPILED.items():
        if any(p.search(text) for p, generic in pats if not (strict and generic)):
            return topic
    return None


@dataclass
class FeeConfusion:
    topic: str
    review_ids: list[str] = field(default_factory=list)
    ticket_count: int = 0

    @property
    def evidence(self) -> dict:
        return {"reviews": len(self.review_ids), "tickets": self.ticket_count, "review_ids": self.review_ids[:20]}


def detect_fee_confusion(reviews, ticket_keys: list[str]) -> FeeConfusion:
    """Most-mentioned fee topic across reviews + fee_question tickets; ties → FEE_TOPICS order; none → exit_load."""
    per: dict[str, FeeConfusion] = {t: FeeConfusion(t) for t in FEE_TOPICS}
    for r in reviews:
        t = topic_of(r.text_redacted)
        if t:
            per[t].review_ids.append(r.id)
    for k in ticket_keys:
        parts = k.split(":")
        if parts[0] == "fee_question" and len(parts) > 1 and parts[1] in per:
            per[parts[1]].ticket_count += 1
    order = list(FEE_TOPICS)
    best = max(per.values(), key=lambda f: (len(f.review_ids) + f.ticket_count, -order.index(f.topic)))
    return best if (len(best.review_ids) + best.ticket_count) > 0 else FeeConfusion("exit_load")
