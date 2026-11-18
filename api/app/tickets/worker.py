"""Runs the desk off the request path: a small thread pool, one DB session and event loop per job."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.models import Ticket

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="desk")
_inflight: set[int] = set()
_lock = threading.Lock()


def _job(ticket_id: int) -> None:
    from app import db as dbmod, deps
    from app.tickets.service import process_ticket
    db = dbmod.SessionLocal()
    try:
        t = db.get(Ticket, ticket_id)
        if t is None or t.status != "received":   # already processed by an earlier submit
            return
        asyncio.run(process_ticket(db, ticket_id, retriever=deps.get_retriever(),
                                   themes_provider=deps.get_themes_provider()))
    except Exception:  # noqa: BLE001  (process_ticket marks the ticket failed itself; this is a last resort)
        log.exception("desk job crashed for ticket id %s", ticket_id)
    finally:
        db.close()
        with _lock:
            _inflight.discard(ticket_id)


def submit(ticket_id: int) -> None:
    with _lock:
        if ticket_id in _inflight:
            return
        _inflight.add(ticket_id)
    _pool.submit(_job, ticket_id)


def recover(db: Session) -> list[int]:
    """A ticket still 'received' at startup lost its job to a restart: run it again."""
    ids = [t.id for t in db.query(Ticket).filter_by(status="received").order_by(Ticket.id)]
    for i in ids:
        submit(i)
    return ids
