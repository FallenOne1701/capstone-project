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
from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.orchestrator import run_desk
from app.desk.reviewer import review_draft
from app.desk.translate import translate_reply, validate_translation
from app.link.canonical import find_canonical, reuse_reply
from app.guard.pii import redact
from app.intent.cache import classify_cached
from app.intent.classifier import IntentResult
from app.link.question_keys import question_key
from app.models import Action, Draft, DraftTranslation, Ticket

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
    scheme_names: list[str] = []


def _validate(text: str) -> str:
    t = (text or "").strip()
    if not t:
        raise ValueError("empty question")
    if len(t) > get_settings().max_message_chars:
        raise ValueError("question too long")
    return t


def _scheme_names() -> dict[str, str]:
    return {s["scheme_id"]: s["scheme_name"] for s in load_schemes()["schemes"]}


def short_name(name: str) -> str:
    """"HDFC Mid Cap Fund Direct Growth" → "HDFC Mid Cap" (the name people say)."""
    i = name.find(" Fund")
    return name[:i] if i > 0 else name


async def preview(text: str, *, language: str | None = None) -> PreviewOut:
    red = redact(_validate(text))
    intent = await classify_cached(red.text)
    names = _scheme_names()
    multi = len(intent.scheme_ids) > 1
    return PreviewOut(redacted_text=red.text, pii_types=red.pii_types, intent=intent.intent,
                      scheme_ids=intent.scheme_ids, language=language or intent.language, needs_clarification=multi,
                      options=[names.get(s, s) for s in intent.scheme_ids] if multi else [],
                      scheme_names=[short_name(names.get(s, s)) for s in intent.scheme_ids])


async def create_ticket(db: Session, text: str, *, channel: str = "text",
                        scheme_id: str | None = None) -> tuple[Ticket, IntentResult]:
    red = redact(_validate(text))
    intent = await classify_cached(red.text)
    if scheme_id and scheme_id in intent.scheme_ids:  # the answer to "Mid Cap or Small Cap?"; anything else is ignored
        intent = intent.model_copy(update={"scheme_ids": [scheme_id]})
    t = Ticket(code="GRW-" + "".join(secrets.choice(_ALPH) for _ in range(6)), channel=channel,
               language=intent.language, question_redacted=red.text, pii_types=red.pii_types,
               intent=intent.intent, scheme_id=intent.scheme_ids[0] if len(intent.scheme_ids) == 1 else None,
               fact_key=intent.fact_key, question_key=question_key(intent, red.text), status="received")
    db.add(t)
    db.flush()
    audit(db, "public", "create", "ticket", t.id, f"intent={intent.intent}")
    db.commit()
    return t, intent


async def _add_translation(db: Session, d: Draft) -> None:
    out = await translate_reply(d.reply)
    probs = validate_translation(d.reply, out) if out else ["no translation"]
    if not probs:
        db.add(DraftTranslation(draft_id=d.id, language="hi", text=out))
    audit(db, "desk", "translate", "draft", d.id, "ok" if not probs else f"discarded:{probs[0]}")


async def process_ticket(db: Session, ticket_id: int, *, retriever, themes_provider: Callable = lambda db: []) -> Draft | None:
    t = db.get(Ticket, ticket_id)
    try:
        intent = await classify_cached(t.question_redacted)
        if t.scheme_id and t.scheme_id in intent.scheme_ids:
            intent = intent.model_copy(update={"scheme_ids": [t.scheme_id]})
        ex = find_canonical(db, intent, t.question_redacted)
        reuse = reuse_reply(ex, intent, t.question_redacted) if ex is not None else None
        if reuse is not None:
            reply, bullet = reuse
            draft_out = OrchestratorOutput(
                reply=reply, citation=bullet["url"], last_checked=ex.last_checked, disposition="reply",
                disagreement=False, routing_note=RoutingNote(team="Fees and mutual fund ops", priority="P3",
                                                             why=f"Reused canonical explainer #{ex.id} ({ex.topic})."))
            facts = FactsResult(status="covered",
                                scheme_id=intent.scheme_ids[0] if len(intent.scheme_ids) == 1 else "reference",
                                fact=bullet["text"], citation=bullet["url"], last_checked=ex.last_checked,
                                searched=[f"explainer:{ex.id}"])
            review = review_draft(draft_out, facts=facts, round=1)
            searched, reused_id = facts.searched, ex.id
        else:
            res = await run_desk(t.question_redacted, list(t.pii_types), intent, retriever=retriever,
                                 themes=themes_provider(db), last_checked=lambda u: last_checked_for(db, u),
                                 today=date.today())
            draft_out, review, searched, reused_id = res.draft, res.review, res.facts.searched, None
        d = Draft(ticket_id=t.id, reply=draft_out.reply, citation=draft_out.citation,
                  last_checked=draft_out.last_checked, disposition=draft_out.disposition,
                  routing_team=draft_out.routing_note.team, routing_priority=draft_out.routing_note.priority,
                  routing_why=draft_out.routing_note.why, review_status=review.status,
                  review_failures=[f.model_dump() for f in review.failures], searched=searched,
                  reused_explainer_id=reused_id)
        db.add(d)
        db.flush()
        if t.language in ("hi", "hinglish") and d.review_status == "pass":
            await _add_translation(db, d)
        a = Action(type="reply_publish", target_label=f"Reply to ticket {t.code}", target_ref=t.code, draft_id=d.id,
                   source_ref=f"ticket:{t.id}")
        db.add(a)
        db.flush()
        t.status = "in_review"
        audit(db, "desk", "create", "draft", d.id, f"disposition={d.disposition} review={d.review_status}")
        audit(db, "desk", "create", "action", a.id, "reply_publish")
        db.commit()
        if get_settings().auto_approve:
            from app.approvals.auto import auto_decide
            auto_decide(db, t.id)
        return d
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("desk failed for ticket %s", t.code)
        t.status = "failed"
        audit(db, "desk", "fail", "ticket", t.id, type(exc).__name__)
        db.commit()
        return None
