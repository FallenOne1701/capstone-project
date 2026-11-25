"""How-to questions → an official Groww Help page, answered in the page's own words (no AI writes the answer).

Pages are listed under `howtos:` in sources.yaml and fetched with the fee reference pages (`refresh_references`).
A question is matched to a page by fixed keyword rules — specific pages first — so an unrelated question never
borrows a page. No match → the desk's usual "not covered, here is what we searched".
"""

from __future__ import annotations

import re

from app.corpus.reference import load_reference
from app.guard.pii import find_pii
from app.guard.scope import detect_advice, detect_performance, truncate_sentences

_SIP = r"\bsips?\b|\binstal+ments?\b"
_REDEEM = r"\bredeem\w*|\bredemption\w*|\bwithdraw\w*"


def _all(*parts: str) -> re.Pattern[str]:
    return re.compile("".join(f"(?=.*(?:{p}))" for p in parts), re.IGNORECASE | re.DOTALL)


# Ordered: the first match wins, so the most specific rules come first.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("sip_cancel_charge", _all(_SIP, r"\bcancel\w*|\bstop\w*", r"\bcharg\w*|\bfees?\b|\bpenalt\w*|\bcost\w*")),
    ("sip_deducted_after_cancel", _all(_SIP, r"\bdeduct\w*|\bdebit\w*", r"\bcancel\w*|\bstop\w*")),
    ("sip_cancel_anytime", _all(_SIP, r"\bcancel\w*|\bstop\w*", r"\bany ?time\b|\bwhenever\b|\bas per my wish\b|\bat any point\b")),
    ("sip_cancel", _all(_SIP, r"\bcancel\w*|\bstop\w*|\bdiscontinu\w*")),
    ("sip_change", _all(_SIP, r"\bchang\w*|\bmodif\w*|\bupdat\w*|\bedit\w*", r"\bdates?\b|\bamounts?\b")),
    ("sip_start", _all(r"\bsips?\b", r"\bstart\w*|\bbegin\w*|\bset ?up\b|\bcreat\w*|\bopen\w*")),
    ("order_cancel", _all(r"\borders?\b", r"\bcancel\w*")),
    ("redeem_not_credited", _all(_REDEEM, r"\bnot (?:been )?(?:credited|received|reflect\w*)|\bhaven'?t (?:got|received)|\bdid ?n[o']?t (?:get|receive)")),
    ("redeem_time", _all(_REDEEM, r"\bhow long\b|\bhow many days\b|\bwhen will\b|\btime to\b|\bdays\b")),
    ("redeem_nav", _all(_REDEEM, r"\bnav\b|\bcut-? ?off\b")),
    ("redeem_limit", _all(_REDEEM, r"\blimit\w*|\bmaximum\b|\bmax\b")),
    ("redeem_anytime", _all(_REDEEM, r"\bany ?time\b|\bwhenever\b")),
    ("redeem_how", _all(_REDEEM, r"\bhow\b|\bsteps?\b|\bway\b|\bprocess\b")),
]

_CHROME_HEAD = re.compile(r"^Customer Support Help and Support En \S+ .*?\?\s*")
_CHROME_TAIL = re.compile(r"\s*Was the answer helpful\?.*$", re.DOTALL)
_LEADING_QUESTION = re.compile(r"^[^?]{10,200}\?\s+(?=[A-Z])")
_MAX_WORDS = 140


def howto_topic(text: str) -> str | None:
    """The help page a question asks about, or None."""
    return next((topic for topic, rule in _RULES if rule.search(text or "")), None)


def howto_fact(topic: str) -> tuple[str, str, str] | None:
    """(fact, url, title) — the page's opening lines, page chrome removed, at most 2 sentences; None if unusable."""
    doc = load_reference(topic)
    if doc is None:
        return None
    body = _CHROME_TAIL.sub("", _CHROME_HEAD.sub("", doc.text.strip())).strip()
    body = _LEADING_QUESTION.sub("", body, count=1).strip()   # a page that opens with its own title question
    fact = truncate_sentences(body, 2)
    words = fact.split()
    if len(words) > _MAX_WORDS:
        fact = truncate_sentences(fact, 1)
    if len(fact.split()) < 4 or detect_advice(fact) or detect_performance(fact) or find_pii(fact):
        return None
    return fact, doc.url, doc.title
