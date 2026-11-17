from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import deps
from app.db import SessionLocal, get_db
from app.models import Ticket
from app.tickets import service as ts

router = APIRouter(prefix="/api")


class AskIn(BaseModel):
    text: str


async def _process(ticket_id: int, db: Session | None = None):
    own = db is None
    db = db or SessionLocal()
    try:
        await ts.process_ticket(db, ticket_id, retriever=deps.get_retriever(), themes_provider=deps.get_themes_provider())
    finally:
        if own:
            db.close()


@router.post("/ask/preview")
async def ask_preview(body: AskIn):
    try:
        return await ts.preview(body.text)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/ask")
async def ask(body: AskIn, db: Session = Depends(get_db)):
    try:
        t, intent = await ts.create_ticket(db, body.text)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await _process(t.id, db)  # synchronous in Plan 1; Plan 3 moves this to a worker queue for latency
    notice = ts.SCOPE_NOTICE if intent.intent in ("advice_request", "performance_request") else None
    return {"code": t.code, "status": db.get(Ticket, t.id).status, "notice": notice}


@router.get("/tickets/{code}")
def ticket_status(code: str, db: Session = Depends(get_db)):
    t = db.query(Ticket).filter_by(code=code).one_or_none()
    if t is None:
        raise HTTPException(404, "ticket not found")
    return {"code": t.code, "status": t.status, "question": t.question_redacted,
            "answer": t.answer_text if t.status == "answered" else None, "answered_at": t.answered_at,
            "language": t.language}
