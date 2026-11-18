"""Weekly automation: the weekly loop (Mon 09:00 IST) and corpus refresh (Sun 21:00 IST)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.db import SessionLocal

log = logging.getLogger(__name__)


def _weekly_job() -> None:
    from app.weekly.run import start_run
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        try:
            pre = start_run(db, now=now)
        except ValueError:
            log.warning("scheduled weekly run skipped: a run is already running")
            return
        from app.approvals.auto import weekly_and_deliver
        run = weekly_and_deliver(db, now=now, run_id=pre.id)
        log.info("scheduled weekly run %s -> %s", run.id, run.status)
    finally:
        db.close()


def _refresh_job() -> None:
    from app.corpus.refresh import refresh_corpus
    db = SessionLocal()
    try:
        refresh_corpus(db)
    finally:
        db.close()


def _delivery_retry_job() -> None:
    from app.approvals.auto import retry_failed_deliveries
    db = SessionLocal()
    try:
        n = retry_failed_deliveries(db)
        if n:
            log.info("retried %d failed Google delivery action(s)", n)
    finally:
        db.close()


def start_scheduler():
    if not get_settings().scheduler_enabled:
        return None
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    sch = BackgroundScheduler(timezone="Asia/Kolkata")
    sch.add_job(_weekly_job, CronTrigger(day_of_week="mon", hour=9, minute=0), id="weekly_loop", replace_existing=True)
    sch.add_job(_refresh_job, CronTrigger(day_of_week="sun", hour=21, minute=0), id="corpus_refresh",
                replace_existing=True)
    sch.add_job(_delivery_retry_job, CronTrigger(minute=5), id="delivery_retry", replace_existing=True)
    sch.start()
    log.info("scheduler started: weekly loop Mon 09:00 IST, corpus refresh Sun 21:00 IST, delivery retry hourly")
    return sch
