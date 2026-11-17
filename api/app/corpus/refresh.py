from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings, load_schemes
from app.corpus.chunker import chunk_scheme_pages
from app.corpus.fetcher import fetch_scheme_pages
from app.corpus.indexer import build_index, collection_count
from app.corpus.parser import parse_scheme_pages
from app.models import Source

log = logging.getLogger(__name__)


@dataclass
class RefreshResult:
    ok: int = 0
    stale: int = 0
    error: int = 0
    reindexed: bool = False


def _upsert(db: Session, scheme: dict) -> Source:
    row = db.query(Source).filter_by(url=scheme["url"]).one_or_none()
    if row is None:
        row = Source(url=scheme["url"], title=scheme["scheme_name"], kind=scheme.get("kind", "scheme"),
                     scheme_id=scheme["scheme_id"], status="pending")
        db.add(row)
    return row


def refresh_corpus(db: Session, *, fetch: bool = True, raw_dir: Path | None = None) -> RefreshResult:
    s = get_settings()
    schemes = list(load_schemes(s.schemes_path)["schemes"])
    work_raw = Path(s.data_raw_dir)
    work_raw.mkdir(parents=True, exist_ok=True)
    if raw_dir is not None and Path(raw_dir) != work_raw:
        for f in Path(raw_dir).iterdir():
            if not (work_raw / f.name).exists():
                shutil.copy2(f, work_raw / f.name)

    now = datetime.now(timezone.utc)
    res = RefreshResult()
    changed = False
    results = {}
    if fetch:
        report = fetch_scheme_pages(schemes=schemes, raw_dir=work_raw, write_report=False)
        results = {r.scheme_id: r for r in report.results}

    for sch in schemes:
        row = _upsert(db, sch)
        r = results.get(sch["scheme_id"])
        if not fetch or (r is not None and r.ok):
            new_hash = (r.content_hash if r else None) or row.content_hash or "fixture"
            changed |= new_hash != row.content_hash
            row.status, row.fetched_at, row.content_hash, row.error = "ok", now, new_hash, None
            res.ok += 1
        else:
            row.error = (r.error if r else None) or "fetch failed"
            row.status = "stale" if row.fetched_at else "error"
            res.stale += row.status == "stale"
            res.error += row.status == "error"
    db.commit()

    if changed or collection_count() == 0:
        parse_scheme_pages(schemes=schemes, raw_dir=work_raw, write_report=False)
        chunk_scheme_pages(schemes=schemes, write_report=False)
        build_index(schemes=schemes, write_report=False)
        res.reindexed = True
    log.info("corpus refresh ok=%s stale=%s error=%s reindexed=%s", res.ok, res.stale, res.error, res.reindexed)
    return res


def last_checked_for(db: Session, url: str) -> str | None:
    row = db.query(Source).filter_by(url=url).one_or_none()
    return row.fetched_at.date().isoformat() if row and row.fetched_at else None
