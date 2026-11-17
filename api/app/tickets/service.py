from __future__ import annotations

import logging
import secrets
from datetime import date
from typing import Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approvals.service import audit
from app.config import get_settings, load_schemes
from app.corpus.refresh import last_checked_for
from app.desk.orchestrator import run_desk
from app.guard.pii import redact
from app.intent.classifier import IntentResult, classify_intent
from app.models import Action, Draft, Ticket

log = logging.getLogger(__name__)
SCOPE_NOTICE = "We share facts only and can't advise on buying, selling or returns."
_ALPH = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PreviewOut(BaseModel):
    redacted_text: str
    pii_types: list[str]
    intent: str
    scheme_ids: list[str]
    language: str
    needs_clarification: bool
    options: list[str]


def _validate(text: str) -> str:
    t = (text or "").strip()
    if not t:
        raise ValueError("empty question")
    if len(t) > get_settings().max_message_chars:
        raise ValueError("question too long")
    return t


def _scheme_names() -> dict[str, str]:
    return {s["scheme_id"]: s["scheme_name"] for s in load_schemes()["schemes"]}


async def preview(text: str) -> PreviewOut:
    red = redact(_validate(text))
    intent = await classify_intent(red.text)
    names = _scheme_names()
    multi = len(intent.scheme_ids) > 1
    return PreviewOut(redacted_text=red.text, pii_types=red.pii_types, intent=intent.intent,
                      scheme_ids=intent.scheme_ids, language=intent.language, needs_clarification=multi,
                      options=[names.get(s, s) for s in intent.scheme_ids] if multi else [])


async def create_ticket(db: Session, text: str, *, channel: str = "text") -> tuple[Ticket, IntentResult]:
    red = redact(_validate(text))
    intent = await classify_intent(red.text)
    t = Ticket(code="GRW-" + "".join(secrets.choice(_ALPH) for _ in range(6)), channel=channel,
               language=intent.language, question_redacted=red.text, pii_types=red.pii_types,
               intent=intent.intent, scheme_id=intent.scheme_ids[0] if len(intent.scheme_ids) == 1 else None,
               fact_key=intent.fact_key, status="received")
    db.add(t)
    db.flush()
    audit(db, "public", "create", "ticket", t.id, f"intent={intent.intent}")
    db.commit()
    return t, intent


async def process_ticket(db: Session, ticket_id: int, *, retriever, themes_provider: Callable = lambda db: []) -> Draft | None:
    t = db.get(Ticket, ticket_id)
    try:
        intent = await classify_intent(t.question_redacted)
        res = await run_desk(t.question_redacted, list(t.pii_types), intent, retriever=retriever,
                             themes=themes_provider(db), last_checked=lambda u: last_checked_for(db, u),
                             today=date.today())
        d = Draft(ticket_id=t.id, reply=res.draft.reply, citation=res.draft.citation,
                  last_checked=res.draft.last_checked, disposition=res.draft.disposition,
                  routing_team=res.draft.routing_note.team, routing_priority=res.draft.routing_note.priority,
                  routing_why=res.draft.routing_note.why, review_status=res.review.status,
                  review_failures=[f.model_dump() for f in res.review.failures], searched=res.facts.searched)
        db.add(d)
        db.flush()
        a = Action(type="reply_publish", target_label=f"Reply to ticket {t.code}", target_ref=t.code, draft_id=d.id,
                   source_ref=f"ticket:{t.id}")
        db.add(a)
        db.flush()
        t.status = "in_review"
        audit(db, "desk", "create", "draft", d.id, f"disposition={d.disposition} review={d.review_status}")
        audit(db, "desk", "create", "action", a.id, "reply_publish")
        db.commit()
        return d
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("desk failed for ticket %s", t.code)
        t.status = "failed"
        audit(db, "desk", "fail", "ticket", t.id, type(exc).__name__)
        db.commit()
        return None
