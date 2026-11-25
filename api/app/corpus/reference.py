"""Official fee-concept pages (Groww Help, AMFI): fetched, main text extracted, sentence-addressable."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import trafilatura
from sqlalchemy.orm import Session

from app.config import get_settings, is_allowed_source_url, load_schemes
from app.guard.pii import find_pii
from app.guard.scope import detect_advice, detect_performance

log = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z₹(\"'])")


@dataclass
class ReferenceDoc:
    topic: str
    url: str
    title: str
    text: str
    fetched_at: str


def _dir() -> Path:
    d = Path(get_settings().data_processed_dir).parent / "reference"
    d.mkdir(parents=True, exist_ok=True)
    return d


def references() -> list[dict]:
    return list(load_schemes().get("references") or [])


def howtos() -> list[dict]:
    """Official Groww Help how-to pages (sources.yaml `howtos:`); fetched with the references, kind "howto"."""
    return list(load_schemes().get("howtos") or [])


def _download(url: str) -> str:
    r = httpx.get(url, headers={"User-Agent": _UA}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _extract(html: str) -> str:
    return re.sub(r"\s+", " ", trafilatura.extract(html) or "").strip()


def refresh_references(db: Session, *, fetch: bool = True, fixture_dir: Path | None = None):
    from app.corpus.refresh import RefreshResult
    from app.models import Source
    res = RefreshResult()
    now = datetime.now(timezone.utc)
    for kind, item in [("reference", x) for x in references()] + [("howto", x) for x in howtos()]:
        if not is_allowed_source_url(item["url"]):
            raise ValueError(f"reference host not allowed: {item['url']}")
        offline = fixture_dir is not None and not fetch
        if offline and kind == "howto" and not (Path(fixture_dir) / f"{item['topic']}.html").exists():
            continue   # offline runs (tests, e2e) have fee-page fixtures only
        row = db.query(Source).filter_by(url=item["url"]).one_or_none()
        if row is None:
            row = Source(url=item["url"], title=item["title"], kind=kind, scheme_id=None, status="pending")
            db.add(row)
        try:
            if offline:
                html = (Path(fixture_dir) / f"{item['topic']}.html").read_text(encoding="utf-8", errors="ignore")
            else:
                html = _download(item["url"])
            text = _extract(html)
            if len(text) < 80:
                raise ValueError("extracted text too short")
            doc = ReferenceDoc(topic=item["topic"], url=item["url"], title=item["title"], text=text,
                               fetched_at=now.date().isoformat())
            (_dir() / f"{item['topic']}.json").write_text(json.dumps(asdict(doc), ensure_ascii=False), encoding="utf-8")
            row.status, row.fetched_at, row.error = "ok", now, None
            res.ok += 1
        except Exception as exc:  # noqa: BLE001
            row.error = type(exc).__name__
            row.status = "stale" if row.fetched_at else "error"
            res.stale += row.status == "stale"
            res.error += row.status == "error"
            log.warning("reference fetch failed for %s: %s", item["topic"], type(exc).__name__)
    db.commit()
    return res


def load_reference(topic: str) -> ReferenceDoc | None:
    p = _dir() / f"{topic}.json"
    if not p.exists():
        return None
    return ReferenceDoc(**json.loads(p.read_text(encoding="utf-8")))


def reference_sentences(topic: str, *, max_words: int = 45) -> list[str]:
    doc = load_reference(topic)
    if doc is None:
        return []
    out: list[str] = []
    for s in _SENT.split(doc.text):
        s = s.strip()
        # Questions are headings (and carry page chrome glued on by extraction), never facts.
        if len(s.split()) < 5 or s.endswith("?") or detect_advice(s) or detect_performance(s) or find_pii(s):
            continue
        words = s.split()
        out.append(s if len(words) <= max_words else " ".join(words[:max_words]) + "…")
    return out
