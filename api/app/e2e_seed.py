"""Offline seed for the Playwright stack (E2E_SEED=1 with USE_LLM=0 only): one weekly run and the source rows.

Never downloads anything and never rebuilds the corpus index: the e2e API shares the real corpus folders.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import API_ROOT, get_settings, load_schemes
from app.corpus.reference import load_reference, references
from app.models import Source, WeeklyRun

log = logging.getLogger(__name__)
REVIEWS = API_ROOT / "tests" / "fixtures" / "reviews.json"


def _fixture_fetcher(now: datetime):
    raws = json.loads(REVIEWS.read_text(encoding="utf-8"))
    newest = max(datetime.fromisoformat(r["at"]) for r in raws)
    shift = (now.replace(tzinfo=None) - timedelta(days=1)) - newest   # keep the reviews inside the 8-week window

    def fetch(package: str, weeks: int, max_reviews: int) -> list[dict]:
        return [{**r, "at": (datetime.fromisoformat(r["at"]) + shift).isoformat()} for r in raws]
    return fetch


def _seed_sources(db: Session, now: datetime) -> None:
    s = get_settings()
    rows = [(x["url"], x["scheme_name"], "scheme", x["scheme_id"],
             (Path(s.data_raw_dir) / f"{x['scheme_id']}.html").exists())
            for x in load_schemes(s.schemes_path)["schemes"]]
    rows += [(x["url"], x["title"], "reference", None, load_reference(x["topic"]) is not None) for x in references()]
    for url, title, kind, scheme_id, have in rows:
        if db.query(Source).filter_by(url=url).one_or_none() is None:
            db.add(Source(url=url, title=title, kind=kind, scheme_id=scheme_id, status="ok" if have else "error",
                          fetched_at=now if have else None, error=None if have else "not downloaded"))
    db.commit()


def seed(db: Session) -> None:
    from app.weekly.run import run_weekly
    import asyncio
    now = datetime.now(timezone.utc)
    _seed_sources(db, now)
    if db.query(WeeklyRun).first() is None:
        run = asyncio.run(run_weekly(db, now=now, fetcher=_fixture_fetcher(now)))
        log.info("e2e seed: weekly run %s -> %s", run.id, run.status)
