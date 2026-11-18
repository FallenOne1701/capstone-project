from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.formparsers import MultiPartException, MultiPartParser
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import deps
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import Ticket
from app.tickets import service as ts, worker
from app.voice import stt

router = APIRouter(prefix="/api")


class AskIn(BaseModel):
    text: str
    scheme_id: str | None = None
    channel: Literal["text", "voice"] = "text"


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
        t, intent = await ts.create_ticket(db, body.text, channel=body.channel, scheme_id=body.scheme_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if get_settings().ticket_worker_inline:
        await _process(t.id, db)
    else:
        worker.submit(t.id)   # the page shows "received" at once and polls for "in review"
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


STT_FAIL = "Couldn't hear that — try again or type"
VOICE_DOWN = "Voice is unavailable right now — please type your question."


class _InMemoryParser(MultiPartParser):
    spool_max_size = 1 << 30  # never roll an upload over to a temp file: audio stays in memory


@router.post("/voice/transcribe")
async def voice_transcribe(request: Request):
    s = get_settings()
    if int(request.headers.get("content-length") or 0) > s.voice_max_bytes + 65_536:
        raise HTTPException(413, "recording too large")
    audio = b""
    try:
        try:
            form = await _InMemoryParser(request.headers, request.stream()).parse()
        except MultiPartException:
            raise HTTPException(422, STT_FAIL)
        upload = form.get("audio")
        try:
            duration = int(form.get("duration_ms") or 0)
        except ValueError:
            duration = 0
        if upload is None or isinstance(upload, str):
            raise HTTPException(422, STT_FAIL)
        audio = await upload.read()
        await upload.close()
        if len(audio) > s.voice_max_bytes:
            raise HTTPException(413, "recording too large")
        if not audio or not (s.voice_min_ms <= duration <= s.voice_max_ms):
            raise HTTPException(422, STT_FAIL)
        try:
            transcript = await stt.transcribe(audio, upload.filename or "clip.webm")
        except stt.NoSpeech:
            raise HTTPException(422, STT_FAIL)
        except stt.VoiceUnavailable:
            raise HTTPException(503, VOICE_DOWN)
    finally:
        del audio
    try:
        return await ts.preview(transcript.text, language=stt.language_hint(transcript))
    except ValueError:
        raise HTTPException(422, STT_FAIL)
