"""Read-only verification report: every weekly claim next to its evidence, for manual checking."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.config import get_settings, load_schemes
from app.corpus.reference import load_reference
from app.guard.pii import find_pii
from app.guard.scope import check_output, word_count
from app.link.question_keys import label_for
from app.models import Action, AuditLog, Draft, Explainer, Review, Theme, Ticket, WeeklyRun

CHECKLIST = """- [ ] Open 3 quotes' review ids and confirm the text matches.
- [ ] Spot-check 2 themes: count equals the number of listed ids; window is stated.
- [ ] Open each explainer URL in a browser; confirm the bullet's sentence is on the page and the date is today's check.
- [ ] Confirm a key with ≥5 questions in 7 days is in the pulse and a key with 4 is not.
- [ ] Confirm no names, phone numbers, PANs or emails appear anywhere in the report.
- [ ] Read the pending Doc/Gmail content — it is exactly what you'd approve."""
_QUOTE = re.compile(r'- "(.+?)" \((rv_[a-z2-7]+)\)')
_SWEEP = (Review, Ticket, Draft, Theme, Explainer, Action, AuditLog)


@dataclass
class Report:
    run_id: int
    markdown: str
    flags: list[str] = field(default_factory=list)


def _source_texts(url: str) -> list[str]:
    texts = [r.text for r in (load_reference(x["topic"]) for x in load_schemes().get("references") or [])
             if r is not None and r.url == url]
    for p in Path(get_settings().data_processed_dir).glob("*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("source_url") == url:
            texts += [s.get("text", "") for s in doc.get("sections", [])]
    return texts


def _text_of(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def build_report(db: Session, run_id: int | None = None, *, log_paths=()) -> Report:
    s = get_settings()
    run = db.get(WeeklyRun, run_id) if run_id else db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
    if run is None:
        return Report(run_id=None, markdown="# Verification report\n\nNo weekly runs found.", flags=[])
    flags: list[str] = []
    L = [f"# Verification report — weekly run {run.id}", f"Generated {datetime.now(timezone.utc).isoformat()}", "",
         "## Run summary",
         f"- status: {run.status} · window: {run.window_start} to {run.window_end} · reviews: {run.review_count} "
         f"· LLM calls: {run.llm_calls}" + (f" · error: {run.error}" if run.error else "")]

    L += ["", "## Themes"]
    for t in db.query(Theme).filter_by(run_id=run.id).order_by(Theme.rank):
        found = db.query(Review).filter(Review.id.in_(t.review_ids)).count()
        ok = found == t.count == len(t.review_ids)
        if not ok:
            flags.append(f"theme {t.theme_id} count MISMATCH ({t.count} stated, {found} found)")
        L.append(f"- {t.rank}. {t.label}: {t.count} reviews ({t.recent_count} in last 7 days), window "
                 f"{t.window_start} to {t.window_end} — {'count OK' if ok else 'count MISMATCH'}")
        L.append(f"  - ids: {', '.join(t.review_ids)}")

    L += ["", "## Quotes"]
    for text, rid in _QUOTE.findall(run.pulse_text or ""):
        rv = db.get(Review, rid)
        ok = rv is not None and text.rstrip("…").strip() in rv.text_redacted
        if not ok:
            flags.append(f"quote {rid} NOT FOUND")
        L += [f'- "{text}" ({rid}) — {"verbatim OK" if ok else "NOT FOUND"}',
              f"  - full review: {rv.text_redacted if rv else '(missing)'}"]

    L += ["", "## Repeated questions"]
    groups: dict[str, list[Ticket]] = {}
    for t in db.query(Ticket).filter(Ticket.question_key.isnot(None)):
        groups.setdefault(t.question_key, []).append(t)
    shown = False
    for key, ts in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(ts) >= s.repeat_threshold - 2:
            shown = True
            tag = f"≥{s.repeat_threshold}: check it is in the pulse" if len(ts) >= s.repeat_threshold else "near miss"
            L.append(f"- {label_for(key)} ({key}): {len(ts)} tickets [{tag}]")
            L += [f"  - {t.code} {t.created_at:%Y-%m-%d}: {t.question_redacted}" for t in ts]
    if not shown:
        L.append(f"- no question key has {s.repeat_threshold - 2}+ tickets")

    ex = db.query(Explainer).filter_by(run_id=run.id).first()
    L += ["", "## Fee confusion", f"- topic: {ex.topic} · evidence: {json.dumps(ex.evidence)}" if ex else "- none"]
    L += ["", "## Explainer"]
    if ex:
        for i, b in enumerate(ex.bullets, 1):
            ok = any(b["text"].rstrip("…").strip() in t for t in _source_texts(b["url"]))
            if not ok:
                flags.append(f"bullet {i} NOT IN SOURCE")
            L.append(f"- {i}. {b['text']} — {b['url']} (last checked {ex.last_checked}) — "
                     f"{'source OK' if ok else 'NOT IN SOURCE'}")
        L.append(f"- distinct official URLs: {len({b['url'] for b in ex.bullets})} · bullets: {len(ex.bullets)}")

    L += ["", "## Caps & scope", f"- pulse words: {word_count(run.pulse_text or '')} (cap 250)"]
    if ex:
        L.append(f"- explainer bullets: {len(ex.bullets)} (cap 6)")
    body = "\n".join(line for line in (run.pulse_text or "").splitlines() if not line.startswith('- "'))
    L.append(f"- pulse scope violations (outside quotes): {[v.check for v in check_output(body, kind='pulse')]}")

    L += ["", "## Pending actions"]
    for a in db.query(Action).filter_by(source_ref=f"weekly_run:{run.id}"):
        L += [f"### Action {a.id} · {a.type} · {a.status}", f"Target: {a.target_label}", "```", a.content or "", "```"]

    L += ["", "## PII sweep"]
    for model in _SWEEP:
        cols = [c.key for c in sa_inspect(model).columns
                if str(c.type).upper().startswith(("TEXT", "VARCHAR", "JSON"))]
        for row in db.query(model):
            for c in cols:
                hits = find_pii(_text_of(getattr(row, c)) or "")
                if hits:
                    flags.append(f"PII {model.__tablename__}.{c} id={row.id}: {','.join(hits)}")
    for p in log_paths:
        for n, line in enumerate(Path(p).read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if find_pii(line):
                flags.append(f"PII log {Path(p).name}:{n}")
    L += [f"- {f}" for f in flags if f.startswith("PII")] or ["- no PII found"]

    L += ["", "## Flags", *([f"- {f}" for f in flags] or ["- none"]), "", "## Manual checklist", CHECKLIST]
    return Report(run_id=run.id, markdown="\n".join(L), flags=flags)
