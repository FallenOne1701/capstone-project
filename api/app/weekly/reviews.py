"""Public Play Store reviews → scrubbed Review rows (identity fields never leave this module)."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.guard.pii import redact
from app.models import Review

RawFetcher = Callable[[str, int, int], list[dict]]


@dataclass
class IngestResult:
    fetched: int
    stored: int
    window_start: date
    window_end: date


def play_store_fetcher(package: str, weeks: int, max_reviews: int) -> list[dict]:
    from google_play_scraper import Sort, reviews
    cutoff = datetime.now() - timedelta(weeks=weeks)
    out: list[dict] = []
    token = None
    while len(out) < max_reviews:
        batch, token = reviews(package, lang="en", country="in", sort=Sort.NEWEST,
                               count=min(200, max_reviews - len(out)), continuation_token=token)
        if not batch:
            break
        out.extend(batch)
        if batch[-1]["at"] < cutoff or token is None:
            break
    return out


def review_id(raw_id: str) -> str:
    # base32 (a-z, 2-7): never a long digit run, so ids can't trip the PII redactor's account-number rule
    return "rv_" + base64.b32encode(hashlib.sha1(raw_id.encode()).digest()).decode().lower()[:10]


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.fromisoformat(str(v)).date()


def scrub(raw: dict) -> dict | None:
    text = redact((raw.get("content") or "").strip()).text
    if not text:
        return None
    return {"id": review_id(str(raw["reviewId"])), "rating": int(raw.get("score") or 0),
            "date": _as_date(raw["at"]), "text_redacted": text,
            "app_version": (raw.get("appVersion") or raw.get("reviewCreatedVersion") or None)}


def ingest_reviews(db: Session, *, today: date, fetcher: RawFetcher = play_store_fetcher) -> IngestResult:
    s = get_settings()
    start = today - timedelta(weeks=s.reviews_weeks)
    raws = fetcher(s.play_package, s.reviews_weeks, s.reviews_max)
    if not raws:
        raise RuntimeError("Play Store returned 0 reviews")
    dates: list[date] = []
    for raw in raws:
        row = scrub(raw)
        if row is None or not (start <= row["date"] <= today):
            continue
        db.merge(Review(**row))
        dates.append(row["date"])
    db.commit()
    # State the window actually covered: when the review cap is hit, that's much shorter than reviews_weeks.
    covered = max(start, min(dates)) if dates else start
    return IngestResult(fetched=len(raws), stored=len(dates), window_start=covered, window_end=today)
