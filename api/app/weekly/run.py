"""Weekly loop: reviews → themes → fee confusion → explainer + pulse → two pending approval actions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.approvals.service import audit
from app.config import get_settings
from app.guard.pii import redact
from app.link.question_keys import repeated_questions
from app.models import Action, Explainer, Review, Theme, Ticket, WeeklyRun
from app.weekly.explainer import build_explainer, render_explainer, validate_explainer
from app.weekly.fee_topics import detect_fee_confusion
from app.weekly.pulse import action_ideas, compose_pulse, select_quotes, validate_pulse
from app.weekly.reviews import ingest_reviews, play_store_fetcher
from app.weekly.themes import assign_themes, build_themes

log = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def run_weekly(db: Session, *, now: datetime, fetcher=play_store_fetcher) -> WeeklyRun:
    s = get_settings()
    today = now.date()
    run = WeeklyRun(status="running", window_start=today - timedelta(weeks=s.reviews_weeks), window_end=today)
    db.add(run)
    db.commit()
    run_id = run.id
    try:
        ing = ingest_reviews(db, today=today, fetcher=fetcher)
        run.window_start = ing.window_start   # the window actually covered, not the nominal 8 weeks
        reviews = db.query(Review).filter(Review.date >= ing.window_start, Review.date <= ing.window_end).all()
        run.review_count = len(reviews)
        assign, calls = await assign_themes(reviews)
        themes = build_themes(assign, reviews, window_start=ing.window_start, window_end=ing.window_end, today=today)
        for t in themes:
            db.add(Theme(run_id=run.id, theme_id=t.theme_id, label=t.label, count=t.count, recent_count=t.recent_count,
                         review_ids=t.review_ids, window_start=t.window_start, window_end=t.window_end, rank=t.rank))
        repeated = repeated_questions(db, now=now, threshold=s.repeat_threshold, days=s.repeat_days)
        cutoff = now - timedelta(days=s.repeat_days)
        keys = [t.question_key for t in db.query(Ticket).filter(Ticket.question_key.isnot(None))
                if _aware(t.created_at) >= cutoff]
        fee = detect_fee_confusion(reviews, keys)
        draft = build_explainer(db, fee.topic)
        quotes = select_quotes(themes, {r.id: r for r in reviews})
        actions, act_calls = await action_ideas(themes, quotes)
        pulse = compose_pulse(week_end=today, window_start=ing.window_start, window_end=ing.window_end,
                              review_count=len(reviews), themes=themes, quotes=quotes, repeated=repeated, fee=fee,
                              actions=actions)
        run.llm_calls = calls + act_calls
        problems = validate_pulse(pulse) + validate_explainer(draft)
        if problems:
            raise ValueError("; ".join(problems))
        db.add(Explainer(run_id=run.id, topic=draft.topic, title=draft.title, bullets=draft.bullets,
                         last_checked=draft.last_checked, status="draft", evidence=fee.evidence))
        body = pulse + "\n\n" + render_explainer(draft)
        doc = Action(type="doc_append", target_ref=s.pulse_doc_id or "PULSE_DOC_ID",
                     target_label=f"Append to the weekly pulse Google Doc ({s.pulse_doc_id or 'PULSE_DOC_ID not set'})",
                     content=body, source_ref=f"weekly_run:{run.id}")
        mail = Action(type="email_draft", target_ref="PULSE_DRAFT_RECIPIENT",
                      target_label="Gmail draft to the product team (PULSE_DRAFT_RECIPIENT)",
                      content=f"Subject: Groww weekly pulse — week ending {today.isoformat()}\n\n{body}",
                      source_ref=f"weekly_run:{run.id}")
        db.add_all([doc, mail])
        db.flush()
        run.pulse_text, run.status, run.finished_at = pulse, "awaiting_approval", datetime.now(timezone.utc)
        audit(db, "scheduler", "create", "weekly_run", run.id, f"themes={len(themes)} fee={fee.topic}")
        audit(db, "scheduler", "create", "action", doc.id, "doc_append")
        audit(db, "scheduler", "create", "action", mail.id, "email_draft")
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(WeeklyRun, run_id)
        run.status, run.finished_at = "failed", datetime.now(timezone.utc)
        run.error = redact(f"{type(exc).__name__}: {exc}").text[:1000]
        audit(db, "scheduler", "fail", "weekly_run", run.id, run.error)
        db.commit()
        log.warning("weekly run %s failed: %s", run.id, run.error)
    return run
