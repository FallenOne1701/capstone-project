from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approvals import service as ap
from app.corpus.refresh import refresh_corpus
from app.db import get_db
from app.deps import require_console
from app.models import Action, Draft, Source, Ticket

router = APIRouter(prefix="/api/console", dependencies=[Depends(require_console)])


class EditIn(BaseModel):
    reply: str


def _draft_out(d: Draft | None):
    if d is None:
        return None
    return {"id": d.id, "reply": d.reply, "citation": d.citation, "last_checked": d.last_checked,
            "disposition": d.disposition, "routing": {"team": d.routing_team, "priority": d.routing_priority,
                                                      "why": d.routing_why},
            "review_status": d.review_status, "review_failures": d.review_failures, "searched": d.searched,
            "reused_explainer_id": d.reused_explainer_id, "edited": d.edited}


@router.get("/queue")
def queue(db: Session = Depends(get_db)):
    out = []
    for t in db.query(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(200):
        d = db.query(Draft).filter_by(ticket_id=t.id).order_by(Draft.id.desc()).first()
        a = db.query(Action).filter_by(draft_id=d.id).order_by(Action.id.desc()).first() if d else None
        out.append({"code": t.code, "status": t.status, "intent": t.intent, "language": t.language,
                    "question": t.question_redacted, "pii_types": t.pii_types, "created_at": t.created_at,
                    "draft": _draft_out(d),
                    "action": {"id": a.id, "status": a.status, "target": a.target_label} if a else None})
    return out


def _guard(fn, *args):
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/drafts/{draft_id}/edit")
def edit(draft_id: int, body: EditIn, db: Session = Depends(get_db)):
    return _draft_out(_guard(ap.edit_draft, db, draft_id, body.reply, "console"))


@router.post("/actions/{action_id}/approve")
def approve(action_id: int, db: Session = Depends(get_db)):
    a = _guard(ap.approve, db, action_id, "console")
    return {"id": a.id, "status": a.status}


@router.post("/actions/{action_id}/reject")
def reject(action_id: int, db: Session = Depends(get_db)):
    a = _guard(ap.reject, db, action_id, "console")
    return {"id": a.id, "status": a.status}


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    return [{"url": s.url, "title": s.title, "kind": s.kind, "status": s.status,
             "last_checked": s.fetched_at.date().isoformat() if s.fetched_at else None, "error": s.error}
            for s in db.query(Source).order_by(Source.kind, Source.title)]


@router.post("/sources/refresh")
def refresh(db: Session = Depends(get_db)):
    r = refresh_corpus(db)
    return {"ok": r.ok, "stale": r.stale, "error": r.error, "reindexed": r.reindexed}
