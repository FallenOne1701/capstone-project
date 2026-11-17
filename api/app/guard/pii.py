"""Deterministic PII redaction. Runs on every input before storage, logging or agents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_S = r"[ 	\-]?"  # optional single space/tab/hyphen between characters (voice transcripts); never a newline


@dataclass(frozen=True)
class Redaction:
    text: str
    pii_types: list[str] = field(default_factory=list)


_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    ("UPI", re.compile(r"\b[A-Za-z0-9._-]{2,}@[A-Za-z]{2,}\b"), "[UPI]"),
    # Letters: compact ("ABCDE"), fully spaced ("A B C D E") or 4+1 ("abcd e"); digits compact or fully
    # spaced; optional separator between groups. Arbitrary per-letter spacing is NOT allowed — it would
    # match ordinary text such as "SIP is 1000 a month" ("sip is" = 5 letters).
    ("PAN", re.compile(
        r"(?i)\b(?:[a-z]{5}|(?:[a-z][ 	-]){4}[a-z]|[a-z]{4}[ 	-][a-z])[ 	-]?(?:\d{4}|(?:\d[ 	-]){3}\d)[ 	-]?[a-z]\b"
    ), "[PAN]"),
    ("IFSC", re.compile(r"(?i)\b[a-z]{4}0[a-z0-9]{6}\b"), "[IFSC]"),
    ("OTP", re.compile(r"(?i)\b(?:otp|one[ 	-]?time[ 	-]?password)\s*(?:is|:|-)?\s*(?:\d" + _S + r"){3,7}\d\b"), "[OTP]"),
    ("CARD", re.compile(r"\b(?:\d" + _S + r"){15}\d\b"), "[CARD]"),
    ("ACCOUNT", re.compile(
        r"(?i)\b(?:account|acct|acc|a/c)\s*(?:no\.?|number|num|#)?\s*(?:is|:|-)?\s*(?:\d" + _S + r"){8,17}\d\b"
    ), "[ACCOUNT]"),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91" + _S + r")?[6-9](?:" + _S + r"\d){9}(?!\d)"), "[PHONE]"),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[ 	-]?\d{4}[ 	-]?\d{4}(?!\d)"), "[AADHAAR]"),
    ("ACCOUNT", re.compile(r"(?<![\d,.])(?:\d[ 	-]?){8,17}\d(?![\d,.])"), "[ACCOUNT]"),
]


def redact(text: str) -> Redaction:
    out = text or ""
    found: list[str] = []
    for ptype, pattern, token in _RULES:
        out, n = pattern.subn(token, out)
        if n and ptype not in found:
            found.append(ptype)
    return Redaction(text=out, pii_types=found)


def find_pii(text: str) -> list[str]:
    return redact(text).pii_types
