from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))  # scheme | reference
    scheme_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # ok | stale | error | pending
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    channel: Mapped[str] = mapped_column(String(10), default="text")  # text | voice
    language: Mapped[str] = mapped_column(String(10), default="en")  # en | hi | hinglish
    question_redacted: Mapped[str] = mapped_column(Text)
    pii_types: Mapped[list] = mapped_column(JSON, default=list)
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scheme_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fact_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    question_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="received")  # received | in_review | answered | failed
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reply: Mapped[str] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_checked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    disposition: Mapped[str] = mapped_column(String(20))
    routing_team: Mapped[str] = mapped_column(String(80))
    routing_priority: Mapped[str] = mapped_column(String(4))
    routing_why: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(10))  # pass | fail | blocked
    review_failures: Mapped[list] = mapped_column(JSON, default=list)
    searched: Mapped[list] = mapped_column(JSON, default=list)
    reused_explainer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)


class DraftTranslation(Base):
    """Hindi version of a draft, shown to the approver and published only with it (additive table)."""
    __tablename__ = "draft_translations"
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), unique=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="hi")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Action(Base):
    __tablename__ = "actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(20))  # reply_publish | doc_append | email_draft
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|approved|rejected|executed|failed
    target_label: Mapped[str] = mapped_column(String(300))
    target_ref: Mapped[str] = mapped_column(String(300))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # null for reply_publish (read from draft)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id"), nullable=True)
    source_ref: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(40))
    verb: Mapped[str] = mapped_column(String(20))  # create|edit|approve|reject|execute|fail
    entity: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(Text, default="")


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer)
    date: Mapped["date"] = mapped_column(Date, index=True)
    text_redacted: Mapped[str] = mapped_column(Text)
    app_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WeeklyRun(Base):
    __tablename__ = "weekly_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|awaiting_approval|failed|done
    window_start: Mapped["date"] = mapped_column(Date)
    window_end: Mapped["date"] = mapped_column(Date)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    pulse_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)


class Theme(Base):
    __tablename__ = "themes"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("weekly_runs.id"), index=True)
    theme_id: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(120))
    count: Mapped[int] = mapped_column(Integer)
    recent_count: Mapped[int] = mapped_column(Integer)
    review_ids: Mapped[list] = mapped_column(JSON, default=list)
    window_start: Mapped["date"] = mapped_column(Date)
    window_end: Mapped["date"] = mapped_column(Date)
    rank: Mapped[int] = mapped_column(Integer)


class Explainer(Base):
    __tablename__ = "explainers"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("weekly_runs.id"), nullable=True)
    topic: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    bullets: Mapped[list] = mapped_column(JSON, default=list)
    last_checked: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft|canonical|superseded|rejected
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    canonical_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
