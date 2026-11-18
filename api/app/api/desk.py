"""The page's own approval endpoints (Plan 3c): no password — any person on the page can approve, edit or reject.

Every click is audited with actor `page`, and the POSTs are rate-limited because the page is public. The logic is
the same tested approval service the console uses; only the actor and the limits differ.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api import console as c
from app.approvals import service as ap
from app.db import get_db
from app.guard.ratelimit import limit_desk, limit_weekly_run
from app.models import Action, Ticket

ACTOR = "page"
QUEUE_SIZE = 30

router = APIRouter(prefix="/api/desk")
_run_in_background = c._run_in_background


@router.get("/queue")
def queue(db: Session = Depends(get_db)):
    """What needs a person first (pending replies, failed or stuck tickets), then the newest decided ones."""
    pending_codes = db.query(Action.target_ref).filter(Action.type == "reply_publish", Action.status == "pending")
    newest = (Ticket.created_at.desc(), Ticket.id.desc())
    waiting = (db.query(Ticket).filter(or_(Ticket.code.in_(pending_codes), Ticket.status.in_(("failed", "received"))))
               .order_by(*newest).limit(QUEUE_SIZE).all())
    seen = {t.id for t in waiting}
    rest = (db.query(Ticket).filter(Ticket.id.notin_(seen) if seen else True).order_by(*newest)
            .limit(QUEUE_SIZE - len(waiting)).all()) if len(waiting) < QUEUE_SIZE else []
    return [c.queue_item(db, t) for t in waiting + rest]


@router.post("/actions/{action_id}/approve", dependencies=[Depends(limit_desk)])
def approve(action_id: int, db: Session = Depends(get_db)):
    a = c._guard(ap.approve, db, action_id, ACTOR)
    return {"id": a.id, "status": a.status, "error": a.error}


@router.post("/actions/{action_id}/reject", dependencies=[Depends(limit_desk)])
def reject(action_id: int, db: Session = Depends(get_db)):
    a = c._guard(ap.reject, db, action_id, ACTOR)
    return {"id": a.id, "status": a.status}


@router.post("/actions/{action_id}/retry", dependencies=[Depends(limit_desk)])
def retry(action_id: int, db: Session = Depends(get_db)):
    a = c._guard(ap.retry, db, action_id, ACTOR)
    return {"id": a.id, "status": a.status, "error": a.error}


@router.post("/drafts/{draft_id}/edit", dependencies=[Depends(limit_desk)])
def edit(draft_id: int, body: c.EditIn, db: Session = Depends(get_db)):
    return c._draft_out(c._guard(ap.edit_draft, db, draft_id, body.reply, ACTOR), db)


@router.post("/tickets/{code}/reprocess", dependencies=[Depends(limit_desk)])
def reprocess(code: str, db: Session = Depends(get_db)):
    return c.reprocess_ticket(db, code, ACTOR)


@router.post("/weekly/run", status_code=202, dependencies=[Depends(limit_desk), Depends(limit_weekly_run)])
def weekly_run(db: Session = Depends(get_db)):
    from app.weekly.run import start_run
    try:
        run = start_run(db, now=datetime.now(timezone.utc))
    except ValueError as e:
        raise HTTPException(409, str(e))
    ap.audit(db, ACTOR, "start", "weekly_run", run.id)
    db.commit()
    _run_in_background(run.id)
    return {"status": "started", "run_id": run.id}


@router.get("/weekly/latest")
def weekly_latest(db: Session = Depends(get_db)):
    return c.weekly_latest(db)


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    return c.sources(db)


@router.get("/explainers")
def explainers(db: Session = Depends(get_db)):
    return c.explainers(db)
