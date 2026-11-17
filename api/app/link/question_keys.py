"""Link 1: normalized question keys; keys asked ≥ threshold times in the trailing window feed the pulse."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import load_schemes
from app.intent.classifier import IntentResult
from app.models import Ticket
from app.weekly.fee_topics import TOPIC_LABELS, topic_of

_INTENT_LABELS = {"fee_question": "Fee question", "fund_fact": "Fund fact", "how_to_process": "How-to",
                  "advice_request": "Advice request", "performance_request": "Returns request",
                  "account_issue": "Account issue", "out_of_scope": "Out of scope"}


@dataclass
class RepeatedQuestion:
    key: str
    label: str
    count: int
    window_start: date
    window_end: date
    ticket_codes: list[str] = field(default_factory=list)


def question_key(intent: IntentResult, text: str) -> str:
    topic = intent.fact_key or topic_of(text) or "general"
    key = f"{intent.intent}:{topic}"
    if len(intent.scheme_ids) == 1:
        key += f":{intent.scheme_ids[0]}"
    return key


def label_for(key: str) -> str:
    parts = key.split(":")
    names = {s["scheme_id"]: s["scheme_name"] for s in load_schemes()["schemes"]}
    out = [_INTENT_LABELS.get(parts[0], parts[0])]
    if len(parts) > 1 and parts[1] != "general":
        out.append(TOPIC_LABELS.get(parts[1], parts[1].replace("_", " ").capitalize()))
    if len(parts) > 2:
        out.append(names.get(parts[2], parts[2]))
    return " · ".join(out)


def _aware(dt: datetime, tz) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)   # SQLite returns naive datetimes


def repeated_questions(db: Session, *, now: datetime, threshold: int, days: int) -> list[RepeatedQuestion]:
    cutoff = now - timedelta(days=days)
    groups: dict[str, list[Ticket]] = {}
    for t in db.query(Ticket).filter(Ticket.question_key.isnot(None)):
        if cutoff <= _aware(t.created_at, cutoff.tzinfo) <= now:
            groups.setdefault(t.question_key, []).append(t)
    out = [RepeatedQuestion(key=k, label=label_for(k), count=len(ts), window_start=cutoff.date(),
                            window_end=now.date(), ticket_codes=sorted(t.code for t in ts))
           for k, ts in groups.items() if len(ts) >= threshold]
    return sorted(out, key=lambda r: (-r.count, r.key))
