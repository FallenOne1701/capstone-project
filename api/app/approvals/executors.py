"""Per-action-type executors. Only these functions write outside the database."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.delivery.mcp_client import McpDeliveryError, call_tool
from app.models import Action, Draft, Ticket

Executor = Callable[[Session, Action], str]
EXECUTORS: dict[str, Executor] = {}


def register(action_type: str, fn: Executor) -> None:
    EXECUTORS[action_type] = fn


def _reply_publish(db: Session, a: Action) -> str:
    d = db.get(Draft, a.draft_id)
    t = db.get(Ticket, d.ticket_id)
    t.status, t.answer_text, t.answered_at = "answered", d.reply, datetime.now(timezone.utc)
    return f"ticket:{t.code}"


DOC_PLACEHOLDER = "PULSE_DOC_ID"


def recipient_ref(email: str) -> str:
    """Stored instead of the address: lets execution prove the recipient is still the one that was shown."""
    return "recipient:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def _mask(email: str) -> str:
    local, _, domain = email.strip().partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def recipient_label() -> str:
    to = get_settings().pulse_draft_recipient
    return f"Gmail draft to the product team ({_mask(to) if to else 'PULSE_DRAFT_RECIPIENT not set'})"


def _doc_append(db: Session, a: Action) -> str:
    doc_id = a.target_ref   # exactly the Doc the approver was shown, not whatever is configured now
    if not doc_id or doc_id == DOC_PLACEHOLDER:
        raise McpDeliveryError("PULSE_DOC_ID was not set when this run was created; start a new weekly run")
    call_tool("google_docs_append_content", {"document_id": doc_id, "content": a.content,
                                             "add_newline_before": True, "add_newline_after": True})
    return f"gdoc:{doc_id}"


def _email_draft(db: Session, a: Action) -> str:
    to = get_settings().pulse_draft_recipient
    if not to:
        raise McpDeliveryError("PULSE_DRAFT_RECIPIENT not set")
    if a.target_ref != recipient_ref(to):
        raise McpDeliveryError("draft recipient changed since this action was shown; start a new weekly run")
    first, _, rest = (a.content or "").partition("\n\n")
    if first.startswith("Subject:"):
        subject, body = first.removeprefix("Subject:").strip(), rest
    else:
        subject, body = "Groww weekly pulse", a.content or ""
    res = call_tool("gmail_create_draft", {"to": [to], "subject": subject, "body": body, "is_html": False})
    return f"gmail_draft:{res.get('draft_id') or res.get('id') or 'created'}"


register("reply_publish", _reply_publish)
register("doc_append", _doc_append)
register("email_draft", _email_draft)
