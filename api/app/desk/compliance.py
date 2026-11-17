from __future__ import annotations

from app.desk.contracts import ComplianceResult
from app.guard.pii import find_pii
from app.intent.classifier import IntentResult


def run_compliance(redacted_text: str, pii_types: list[str], intent: IntentResult) -> ComplianceResult:
    flags: list[str] = []
    advice = intent.intent == "advice_request"
    perf = intent.intent == "performance_request"
    if advice:
        flags.append("advice")
    if perf:
        flags.append("performance_claim")
    merged = list(dict.fromkeys([*pii_types, *find_pii(redacted_text)]))
    if merged:
        flags.append("pii")
    return ComplianceResult(flags=flags, pii_types=merged, advice_refusal=advice or perf, redacted_text=redacted_text)
