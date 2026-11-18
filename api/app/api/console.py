from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approvals import service as ap
from app.corpus.refresh import refresh_corpus
from app.db import get_db
from app.deps import require_console
from app.models import Action, Draft, DraftTranslation, Source, Ticket
from app.tickets import worker

router = APIRouter(prefix="/api/console", dependencies=[Depends(require_console)])


class EditIn(BaseModel):
    reply: str


def _draft_out(d: Draft | None, db: Session | None = None):
    if d is None:
        return None
    tr = db.query(DraftTranslation).filter_by(draft_id=d.id).one_or_none() if db is not None else None
    return {"translation": {"language": tr.language, "text": tr.text} if tr else None,"id": d.id, "reply": d.reply, "citation": d.citation, "last_checked": d.last_checked,
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
                    "draft": _draft_out(d, db),
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
    return _draft_out(_guard(ap.edit_draft, db, draft_id, body.reply, "console"), db)


@router.post("/actions/{action_id}/approve")
def approve(action_id: int, db: Session = Depends(get_db)):
    a = _guard(ap.approve, db, action_id, "console")
    return {"id": a.id, "status": a.status}


@router.post("/actions/{action_id}/retry")
def retry(action_id: int, db: Session = Depends(get_db)):
    a = _guard(ap.retry, db, action_id, "console")
    return {"id": a.id, "status": a.status, "error": a.error}


@router.post("/actions/{action_id}/reject")
def reject(action_id: int, db: Session = Depends(get_db)):
    a = _guard(ap.reject, db, action_id, "console")
    return {"id": a.id, "status": a.status}


@router.post("/tickets/{code}/reprocess")
def reprocess(code: str, db: Session = Depends(get_db)):
    t = db.query(Ticket).filter_by(code=code).one_or_none()
    if t is None:
        raise HTTPException(404, "ticket not found")
    if t.status not in ("failed", "received"):
        raise HTTPException(409, f"ticket is {t.status}; only failed or received tickets can be re-run")
    t.status = "received"
    ap.audit(db, "console", "reprocess", "ticket", t.id)
    db.commit()
    worker.submit(t.id)
    return {"code": t.code, "status": "received"}


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    return [{"url": s.url, "title": s.title, "kind": s.kind, "status": s.status,
             "last_checked": s.fetched_at.date().isoformat() if s.fetched_at else None, "error": s.error}
            for s in db.query(Source).order_by(Source.kind, Source.title)]


@router.post("/sources/refresh")
def refresh(db: Session = Depends(get_db)):
    r = refresh_corpus(db)
    return {"ok": r.ok, "stale": r.stale, "error": r.error, "reindexed": r.reindexed}


# --- Weekly loop, explainers, actions (Plan 2) -------------------------------------------------
import asyncio  # noqa: E402
import threading  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from sqlalchemy import func  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.link.question_keys import repeated_questions  # noqa: E402
from app.models import Explainer, Theme, WeeklyRun  # noqa: E402


def _action_out(a: Action) -> dict:
    return {"id": a.id, "type": a.type, "status": a.status, "target_label": a.target_label,
            "content": a.content, "source_ref": a.source_ref, "error": a.error,
            "created_at": a.created_at, "decided_at": a.decided_at, "executed_at": a.executed_at}


def _explainer_out(db: Session, e: Explainer) -> dict:
    reuse = db.query(func.count(Draft.id)).filter(Draft.reused_explainer_id == e.id).scalar()
    return {"id": e.id, "topic": e.topic, "title": e.title, "bullets": e.bullets, "last_checked": e.last_checked,
            "status": e.status, "evidence": e.evidence, "run_id": e.run_id, "canonical_at": e.canonical_at,
            "reuse_count": reuse}


def _run_in_background(run_id: int) -> None:
    def go():
        from app import db as dbmod
        from app.weekly.run import run_weekly
        s = dbmod.SessionLocal()
        try:
            asyncio.run(run_weekly(s, now=datetime.now(timezone.utc), run_id=run_id))
        finally:
            s.close()
    threading.Thread(target=go, daemon=True).start()


@router.post("/weekly/run", status_code=202)
def weekly_run(db: Session = Depends(get_db)):
    from app.weekly.run import start_run
    try:
        run = start_run(db, now=datetime.now(timezone.utc))
    except ValueError as e:
        raise HTTPException(409, str(e))
    _run_in_background(run.id)
    return {"status": "started", "run_id": run.id}


@router.get("/weekly/latest")
def weekly_latest(db: Session = Depends(get_db)):
    run = db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
    if run is None:
        raise HTTPException(404, "no weekly runs yet")
    s = get_settings()
    themes = db.query(Theme).filter_by(run_id=run.id).order_by(Theme.rank).all()
    acts = db.query(Action).filter_by(source_ref=f"weekly_run:{run.id}").all()
    ex = db.query(Explainer).filter_by(run_id=run.id).first()
    rep = repeated_questions(db, now=datetime.now(timezone.utc), threshold=s.repeat_threshold, days=s.repeat_days)
    return {"run": {"id": run.id, "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at,
                    "window_start": run.window_start, "window_end": run.window_end, "review_count": run.review_count,
                    "pulse_text": run.pulse_text, "error": run.error, "llm_calls": run.llm_calls},
            "themes": [{"theme_id": t.theme_id, "label": t.label, "count": t.count, "recent_count": t.recent_count,
                        "review_ids": t.review_ids, "window_start": t.window_start, "window_end": t.window_end,
                        "rank": t.rank} for t in themes],
            "repeated": [r.__dict__ for r in rep],
            "actions": [_action_out(a) for a in acts],
            "explainer": _explainer_out(db, ex) if ex else None}


@router.get("/explainers")
def explainers(db: Session = Depends(get_db)):
    return [_explainer_out(db, e) for e in db.query(Explainer).order_by(Explainer.id.desc())]


@router.get("/actions")
def actions(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Action).order_by(Action.id.desc())
    if status:
        q = q.filter_by(status=status)
    return [_action_out(a) for a in q.limit(200)]
