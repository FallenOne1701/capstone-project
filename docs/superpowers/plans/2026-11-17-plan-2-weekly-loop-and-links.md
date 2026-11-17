# Plan 2 — Weekly Loop + Loop Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The weekly loop runs end to end on live Play Store reviews: it builds ≤5 traced themes, a ≤250-word pulse and a ≤6-bullet fee explainer, and queues them as approval-gated actions. Approving the explainer's doc append makes it a canonical answer the response loop reuses. Questions asked ≥5 times in 7 days surface in the pulse.

**Architecture:** A new `app/weekly/` package (reviews → themes → fee topic → explainer + pulse → run orchestration) and `app/link/` package (question keys, canonical reuse). These plug into Plan 1's tickets, approvals and desk through three seams:
- `process_ticket` checks canonical explainers first.
- `approve` dispatches to a per-type executor registry. `doc_append`/`email_draft` write to a local outbox in this plan; Plan 3 swaps in MCP.
- `deps.get_themes_provider` feeds the latest themes to the Pattern agent.

Official fee-concept pages join the corpus as `kind: reference`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2, google-play-scraper, APScheduler 3, trafilatura, Groq (`gpt-oss-20b` for ambiguous labels, `gpt-oss-120b` for action ideas). Everything is deterministic when `USE_LLM=0`.

**Spec:** `docs/superpowers/specs/2026-11-17-support-desk-design.md` (§4 fee pages, §6 weekly loop and both links, §7 approvals for doc/email actions, §9 feasibility hooks).

**Builds on:** Plan 1 (merged to `main`). Interfaces used from it:
- `redact(text) -> Redaction(text, pii_types)`
- `check_output(text, kind)`, `detect_advice`, `detect_performance`, `word_count`, `bullet_count`
- `classify_intent(text) -> IntentResult(intent, scheme_ids, fact_key, language, confidence)`
- `complete_json(system, user, *, fast)`
- `load_schemes()`, `refresh_corpus(db, fetch, raw_dir)`, `last_checked_for(db, url)`
- `ThemeStat(theme_id, name, team, cues, count, recent_count, window, recent_window)`, `DateWindow(start, end)`
- `FactsResult`, `OrchestratorOutput`, `RoutingNote`, `review_draft(draft, facts=, round=)`, `covered_reply(fact, citation, last_checked)`
- `approve/reject/edit_draft/audit` in `app.approvals.service`, `_claim(db, action_id, status)`
- ORM `Source, Ticket, Draft, Action, AuditLog`; `Ticket.question_key` column already exists
- Test helpers `tests/conftest.py` (`db_session`, `client`) and `tests/conftest_corpus.py` (`build_fixture_retriever`, `FIXTURES`)

## Global Constraints

- Themes: **at most 5**, each with `review_ids`, `count`, and the `window_start`/`window_end` it covers; top 3 by count.
- Pulse ≤ **250 words**, with supporting quotes and exactly **3** action ideas.
- Explainer ≤ **6 bullets**. It is facts-only, every bullet carries one source URL, it uses **≥2 distinct official URLs** overall, and it shows "Last checked: <date>".
- Link 1: a question key with **≥5 tickets in the trailing 7 days** appears in the pulse with count, window and ticket codes.
- Link 2: approving (and successfully executing) a run's `doc_append` marks its explainer **canonical** for its topic, superseding the previous one. Reuse is still reviewed and still needs approval.
- Nothing is written without a human approving **that specific action**. Approving `doc_append` never executes `email_draft` and vice versa.
- No PII: review author names/avatars/reply text are dropped at fetch, and review text is passed through `redact()` before storage. Quotes must pass `find_pii`, `detect_advice` and `detect_performance`.
- Reviews: public Play Store listing `com.nextbillion.groww`, `lang="en"`, `country="in"`, last **8 weeks**, capped at **3000** reviews.
- LLM budget per weekly run: ≤ **4** fast-model calls (ambiguous labels, 12 reviews per call) + **1** main-model call (action ideas). The rules-only path must be complete when `USE_LLM=0`.
- Allowed citation hosts become `groww.in`, `amfiindia.com`, `sebi.gov.in`.
- `doc_append`/`email_draft` executors in this plan write to `api/data/outbox/` (**interim**; Plan 3 replaces them with MCP). The recipient email is never stored in the DB; `target_ref` holds the setting name `PULSE_DRAFT_RECIPIENT`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Quiet or failed Play Store fetch** (0 reviews, network error): the run is marked `failed` with a reason, no actions are created, and the previous run and its themes stay visible. → test in Task 8.
2. **Week with fewer than 3 themes, or no fee-related mentions:** the pulse still validates and states what is missing. The explainer falls back to the most-asked fee topic, else `exit_load`, with evidence count 0 stated. → tests in Tasks 6 and 7.
3. **Canonical reuse for a scheme the explainer doesn't cover** ("exit load of HDFC Gilt"): fall back to the desk's scheme-specific answer, never another scheme's bullet. → test in Task 10.
4. **Approving doc vs email out of order, rejecting the doc, or approving twice:** each action is independent; only an executed `doc_append` canonicalizes; a reject canonicalizes nothing; a second approve raises. → tests in Task 9.
5. **Repeated-question window edges** (exactly 7 days ago, 4 vs 5 tickets, mixed schemes): boundary-correct counts, and every count states its window. → tests in Task 5.

---

## File Structure

```
api/app/
  models.py                 + Review, WeeklyRun, Theme, Explainer
  config.py                 + outbox dir, scheduler flag, review limits, pulse settings; amfi/sebi hosts already allowed
  corpus/
    sources.yaml            + references: [...] (4 official fee pages, with topic)
    reference.py            NEW fetch/extract/store reference pages; load_reference(); reference_sentences()
    refresh.py              + refresh references alongside schemes
  weekly/
    __init__.py
    vocab.py                M2 THEME_VOCAB / keyword patterns / DEFAULT_ACTIONS (ported) + TEAMS + cues
    reviews.py              fetch_reviews() (google-play-scraper) → scrub → upsert Review rows
    themes.py               assign_themes(), build_themes()
    fee_topics.py           FEE_TOPICS, topic_of(text), detect_fee_confusion()
    explainer.py            build_explainer(), validate_explainer(), render_explainer()
    pulse.py                select_quotes(), action_ideas(), compose_pulse(), validate_pulse()
    run.py                  run_weekly()
  link/
    __init__.py
    question_keys.py        question_key(), repeated_questions()
    canonical.py            find_canonical(), reuse_reply()
  approvals/
    executors.py            NEW registry; outbox executors; reply_publish executor
    service.py              approve() dispatches executors; on doc_append executed → mark canonical
  tickets/service.py        create_ticket sets question_key; process_ticket tries canonical first
  deps.py                   get_themes_provider() → latest run's ThemeStats
  scheduler.py              NEW APScheduler weekly jobs
  api/console.py            + /weekly/run, /weekly/latest, /explainers, /actions
api/tests/
  fixtures/reference/*.html  4 saved reference pages
  fixtures/reviews.json      40 synthetic Play Store review dicts (incl. PII + author fields)
  test_models_p2.py test_reference.py test_reviews.py test_themes.py test_question_keys.py
  test_fee_explainer.py test_pulse.py test_weekly_run.py test_executors_link2.py
  test_canonical.py test_weekly_api.py
```

---

### Task 1: Data model and dependencies

**Files:**
- Modify: `api/pyproject.toml` (deps), `api/app/models.py`, `api/app/config.py`
- Test: `api/tests/test_models_p2.py`

**Interfaces:**
- Produces ORM:
  - `Review(id: str pk "rv_<10 base32 chars>", rating: int, date: date, text_redacted: str, app_version: str|None, fetched_at: datetime)`
  - `WeeklyRun(id, started_at, finished_at, status: "running"|"awaiting_approval"|"failed"|"done", window_start: date, window_end: date, review_count: int, pulse_text: str|None, error: str|None, llm_calls: int)`
  - `Theme(id, run_id fk, theme_id: str, label: str, count: int, recent_count: int, review_ids: JSON list[str], window_start: date, window_end: date, rank: int)`
  - `Explainer(id, run_id fk|None, topic: str, title: str, bullets: JSON list[{"text","url"}], last_checked: str, status: "draft"|"canonical"|"superseded"|"rejected", evidence: JSON dict, created_at, canonical_at: datetime|None)`
- Settings added: `data_outbox_dir: Path = API_ROOT/"data"/"outbox"`, `scheduler_enabled: bool = False`, `reviews_weeks: int = 8`, `reviews_max: int = 3000`, `play_package: str = "com.nextbillion.groww"`, `repeat_threshold: int = 5`, `repeat_days: int = 7`, `pulse_doc_id: str = ""`.

- [ ] **Step 1: Add dependencies and install**

In `api/pyproject.toml` dependencies append `"google-play-scraper>=1.2", "apscheduler>=3.10,<4"`. Run:
`cd api && .venv/Scripts/python -m pip install -q -e ".[dev]"`

- [ ] **Step 2: Write the failing test**

`api/tests/test_models_p2.py`:
```python
from datetime import date

from app.models import Explainer, Review, Theme, WeeklyRun


def test_weekly_tables_roundtrip(db_session):
    run = WeeklyRun(status="running", window_start=date(2026, 9, 22), window_end=date(2026, 11, 16), review_count=0)
    db_session.add(run); db_session.flush()
    db_session.add(Review(id="rv_abcdefghij", rating=1, date=date(2026, 11, 16), text_redacted="app crash"))
    db_session.add(Theme(run_id=run.id, theme_id="app_reliability", label="App reliability & updates", count=1,
                         recent_count=1, review_ids=["rv_abcdefghij"], window_start=run.window_start,
                         window_end=run.window_end, rank=1))
    db_session.add(Explainer(run_id=run.id, topic="exit_load", title="Exit load explained",
                             bullets=[{"text": "x", "url": "https://groww.in/a"}], last_checked="2026-11-17",
                             status="draft", evidence={"reviews": 0, "tickets": 0}))
    db_session.commit()
    t = db_session.query(Theme).one()
    assert t.review_ids == ["rv_abcdefghij"] and db_session.query(Explainer).one().status == "draft"


def test_settings_have_weekly_fields():
    from app.config import get_settings
    s = get_settings()
    assert s.reviews_weeks == 8 and s.reviews_max == 3000 and s.repeat_threshold == 5 and s.repeat_days == 7
    assert s.play_package == "com.nextbillion.groww"
```

- [ ] **Step 3: Run to verify failure** — `.venv/Scripts/python -m pytest tests/test_models_p2.py -q` → FAIL (`ImportError: cannot import name 'Explainer'`).

- [ ] **Step 4: Implement**

Append to `api/app/models.py` (add `Date` to the sqlalchemy import list and `date` to the datetime import):
```python
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
    status: Mapped[str] = mapped_column(String(20), default="running")
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
    status: Mapped[str] = mapped_column(String(12), default="draft")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    canonical_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```
The annotation `Mapped["date"]` avoids shadowing by the column attribute named `date`; at the top of models.py use `from datetime import date, datetime, timezone`.

Append to `Settings` in `api/app/config.py`:
```python
    # Weekly loop (Plan 2)
    data_outbox_dir: Path = API_ROOT / "data" / "outbox"
    scheduler_enabled: bool = False
    reviews_weeks: int = 8
    reviews_max: int = 3000
    play_package: str = "com.nextbillion.groww"
    repeat_threshold: int = 5
    repeat_days: int = 7
    pulse_doc_id: str = ""
```

- [ ] **Step 5: Run** → `pytest tests/test_models_p2.py -q` → PASS; then full suite `pytest -q` → all PASS.

- [ ] **Step 6: Commit** — `feat(weekly): data model for reviews, runs, themes, explainers` (+ Co-Authored-By).

---

### Task 2: Official fee reference pages in the corpus

**Files:**
- Modify: `api/app/corpus/sources.yaml`, `api/app/corpus/refresh.py`
- Create: `api/app/corpus/reference.py`, `api/tests/fixtures/reference/{exit_load,redemption_charges,expense_ratio,brokerage}.html`
- Test: `api/tests/test_reference.py`

**Interfaces:**
- Consumes: `Source`, `get_settings()`, `load_schemes()`, `redact`, `detect_advice`, `detect_performance`
- Produces:
  - `REFERENCE_DIR = settings.data_processed_dir.parent / "reference"`
  - `refresh_references(db, *, fetch=True, fixture_dir: Path | None = None) -> RefreshResult` (reuses `RefreshResult` from refresh.py)
  - `load_reference(topic: str) -> ReferenceDoc | None`, where `ReferenceDoc` is a dataclass `(topic, url, title, text, fetched_at: str)`
  - `reference_sentences(topic: str, *, max_words: int = 45) -> list[str]`: verbatim sentences from the page that pass `detect_advice`/`detect_performance`/PII checks, in page order; a sentence longer than `max_words` is cut to a verbatim prefix + "…"
  - `refresh_corpus(...)` now also calls `refresh_references(db, fetch=fetch, fixture_dir=...)`, and adds `references_ok`/`references_stale` to its log line.

- [ ] **Step 1: Save the four reference pages as fixtures**

```bash
cd api && mkdir -p tests/fixtures/reference
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
curl -sL -A "$UA" -o tests/fixtures/reference/exit_load.html "https://groww.in/help/mutual-funds/order/what-is-exit-load--71"
curl -sL -A "$UA" -o tests/fixtures/reference/redemption_charges.html "https://groww.in/help/mutual-funds/order/what-are-the-charges-applicable-for-redeeming--53"
curl -sL -A "$UA" -o tests/fixtures/reference/expense_ratio.html "https://www.amfiindia.com/investor/knowledge-center-info?zoneName=expenseRatio"
curl -sL -A "$UA" -o tests/fixtures/reference/brokerage.html "https://groww.in/help/payments-&-withdrawals/payments-charges/what-fees-does-groww-charge--58"
ls -la tests/fixtures/reference
```
Expected: four files, each > 50 KB.

Append to `api/app/corpus/sources.yaml` (replace the `references: []` line):
```yaml
references:
  - topic: exit_load
    title: What is exit load? — Groww Help
    url: https://groww.in/help/mutual-funds/order/what-is-exit-load--71
  - topic: redemption_charges
    title: What are the charges applicable for redeeming? — Groww Help
    url: https://groww.in/help/mutual-funds/order/what-are-the-charges-applicable-for-redeeming--53
  - topic: expense_ratio
    title: Expense Ratio — AMFI Investor Corner
    url: https://www.amfiindia.com/investor/knowledge-center-info?zoneName=expenseRatio
  - topic: brokerage
    title: What fees does Groww charge? — Groww Help
    url: https://groww.in/help/payments-&-withdrawals/payments-charges/what-fees-does-groww-charge--58
```

- [ ] **Step 2: Write the failing test**

`api/tests/test_reference.py`:
```python
from pathlib import Path

import pytest

from app.corpus import reference as ref
from app.guard.scope import detect_advice, detect_performance
from app.models import Source

FIX = Path(__file__).parent / "fixtures" / "reference"


@pytest.fixture()
def refs(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "data_processed_dir", tmp_path / "processed")
    res = ref.refresh_references(db_session, fetch=False, fixture_dir=FIX)
    return res


def test_refresh_creates_reference_sources(db_session, refs):
    rows = db_session.query(Source).filter_by(kind="reference").all()
    assert refs.ok == 4 and len(rows) == 4 and all(r.fetched_at and r.status == "ok" for r in rows)


def test_exit_load_sentence_is_verbatim(refs):
    sents = ref.reference_sentences("exit_load")
    assert sents[0].startswith("Exit load is a fee payable to a mutual fund house")
    doc = ref.load_reference("exit_load")
    assert doc.url.startswith("https://groww.in/help/") and sents[0].rstrip("…") in doc.text


def test_sentences_are_in_scope(refs):
    for topic in ("exit_load", "redemption_charges", "expense_ratio", "brokerage"):
        for s in ref.reference_sentences(topic):
            assert not detect_advice(s) and not detect_performance(s), s
            assert len(s.split()) <= 46


def test_unknown_topic_is_none(refs):
    assert ref.load_reference("nope") is None and ref.reference_sentences("nope") == []


def test_fetch_failure_marks_stale_keeps_text(db_session, refs, monkeypatch):
    def boom(url):
        raise RuntimeError("timeout")
    monkeypatch.setattr(ref, "_download", boom)
    res = ref.refresh_references(db_session, fetch=True)
    assert res.stale == 4
    assert ref.reference_sentences("exit_load")  # previous text still served
```

- [ ] **Step 3: Run to verify failure** → FAIL (`ModuleNotFoundError: app.corpus.reference`).

- [ ] **Step 4: Implement**

`api/app/corpus/reference.py`:
```python
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


def _download(url: str) -> str:
    r = httpx.get(url, headers={"User-Agent": _UA}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _extract(html: str) -> str:
    text = trafilatura.extract(html) or ""
    return re.sub(r"\s+", " ", text).strip()


def refresh_references(db: Session, *, fetch: bool = True, fixture_dir: Path | None = None):
    from app.corpus.refresh import RefreshResult
    from app.models import Source
    res = RefreshResult()
    now = datetime.now(timezone.utc)
    for item in references():
        if not is_allowed_source_url(item["url"]):
            raise ValueError(f"reference host not allowed: {item['url']}")
        row = db.query(Source).filter_by(url=item["url"]).one_or_none()
        if row is None:
            row = Source(url=item["url"], title=item["title"], kind="reference", scheme_id=None, status="pending")
            db.add(row)
        try:
            html = (Path(fixture_dir) / f"{item['topic']}.html").read_text(encoding="utf-8", errors="ignore") \
                if fixture_dir is not None and not fetch else _download(item["url"])
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
        if len(s.split()) < 5 or detect_advice(s) or detect_performance(s) or find_pii(s):
            continue
        words = s.split()
        out.append(s if len(words) <= max_words else " ".join(words[:max_words]) + "…")
    return out
```

In `api/app/corpus/refresh.py`, at the end of `refresh_corpus` before `log.info(...)`, add:
```python
    from app.corpus.reference import refresh_references
    rr = refresh_references(db, fetch=fetch, fixture_dir=None if fetch else (raw_dir.parent / "reference" if raw_dir else None))
```
and include `rr.ok`/`rr.stale` in the log line. Plan 1's `test_refresh.py` passes `raw_dir=FIXTURES` (`tests/fixtures/raw`), so `raw_dir.parent / "reference"` resolves to the new fixture folder.

- [ ] **Step 5: Run** → `pytest tests/test_reference.py tests/test_refresh.py -q` → PASS. If an AMFI sentence > 45 words fails `len(s.split()) <= 46`, check the "…" suffix logic; do not loosen the assertion.

- [ ] **Step 6: Commit** — `feat(corpus): official fee reference pages (Groww Help, AMFI) with verbatim sentences` (+ Co-Authored-By).

---

### Task 3: Play Store review ingest with PII scrub

**Files:**
- Create: `api/app/weekly/__init__.py` (empty), `api/app/weekly/reviews.py`, `api/tests/fixtures/reviews.json`
- Test: `api/tests/test_reviews.py`

**Interfaces:**
- Consumes: `redact`, `Review` model, settings `play_package`, `reviews_weeks`, `reviews_max`
- Produces:
  - `RawFetcher = Callable[[str, int, int], list[dict]]`, with signature `(package, weeks, max_reviews) -> raw google-play-scraper dicts`
  - `play_store_fetcher(package, weeks, max_reviews) -> list[dict]`: the default; pages with `Sort.NEWEST` until older than the cutoff or the cap is reached
  - `review_id(raw_id: str) -> str`: `"rv_"` + 10 base32 chars (a–z, 2–7) of sha1(raw_id). Digits can never form the 9+ digit runs the PII redactor treats as account numbers
  - `scrub(raw: dict) -> dict | None`: keeps only `{id, rating, date, text_redacted, app_version}`; returns None if the text is empty after redaction
  - `ingest_reviews(db, *, today: date, fetcher: RawFetcher = play_store_fetcher) -> IngestResult`, where `IngestResult` is a dataclass `(fetched: int, stored: int, window_start: date, window_end: date)`. It upserts rows, ignores reviews outside the window, and raises `RuntimeError` if the fetcher returns 0 reviews.

- [ ] **Step 1: Create the synthetic fixture**

Generate `api/tests/fixtures/reviews.json` with this script (it is deterministic and contains PII and author fields to prove scrubbing):
```bash
cd api && .venv/Scripts/python - <<'PY'
import json, random
from datetime import datetime, timedelta
random.seed(7)
base = datetime(2026, 11, 16, 12, 0, 0)
texts = [
  "App crashes every time I open portfolio after the update",
  "Not working since update, blank screen and lag",
  "Customer support never replies, raised ticket 3 times no response",
  "Why was exit load deducted when I redeemed my mutual fund? nobody explains exit load",
  "Exit load charged on SIP units, confusing, which exit load applies",
  "Hidden charges on brokerage, DP charge not shown before selling",
  "Brokerage fee too high for small orders",
  "Unable to sell stocks, order stuck pending",
  "Stop loss order not executed, lost money",
  "Chart shows wrong price and holdings value stale",
  "Great app, easy to invest in mutual funds",
  "Expense ratio shown differently on two screens, what is expense ratio",
]
rows = []
for i in range(40):
    t = texts[i % len(texts)]
    if i == 3: t += " call me 9876543210 or mail ravi.k@example.com"
    if i == 7: t += " my PAN ABCDE1234F"
    rows.append({"reviewId": f"gp:raw-{i:03d}", "userName": f"Real Person {i}", "userImage": "https://x/y.png",
                 "content": t, "score": 1 if i % 4 else 4, "thumbsUpCount": i,
                 "at": (base - timedelta(days=(i * 37) % 70)).isoformat(),
                 "replyContent": "Hi Real Person, sorry", "repliedAt": None, "appVersion": "26.11.0"})
json.dump(rows, open("tests/fixtures/reviews.json", "w"), indent=1)
print(len(rows))
PY
```
Expected: `40`.

- [ ] **Step 2: Write the failing test**

`api/tests/test_reviews.py`:
```python
import json
from datetime import date
from pathlib import Path

import pytest

from app.models import Review
from app.weekly.reviews import ingest_reviews, review_id, scrub

RAW = json.loads((Path(__file__).parent / "fixtures" / "reviews.json").read_text())


def fake_fetcher(package, weeks, max_reviews):
    return [dict(r) for r in RAW][:max_reviews]


def test_scrub_drops_identity_and_redacts_text():
    out = scrub(RAW[3])
    assert set(out) == {"id", "rating", "date", "text_redacted", "app_version"}
    assert "9876543210" not in out["text_redacted"] and "ravi" not in out["text_redacted"]
    assert out["id"] == review_id("gp:raw-003") and out["id"].startswith("rv_")


def test_ingest_window_and_no_pii(db_session):
    res = ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=fake_fetcher)
    assert res.window_start == date(2026, 9, 22) and res.window_end == date(2026, 11, 17)
    rows = db_session.query(Review).all()
    assert 0 < len(rows) == res.stored <= 40
    assert all(res.window_start <= r.date <= res.window_end for r in rows)
    blob = " ".join(f"{r.id} {r.text_redacted} {r.app_version}" for r in rows)
    for raw in ("Real Person", "9876543210", "ABCDE1234F", "ravi.k@example.com", "gp:raw"):
        assert raw not in blob


def test_ingest_is_idempotent(db_session):
    ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=fake_fetcher)
    n = db_session.query(Review).count()
    ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=fake_fetcher)
    assert db_session.query(Review).count() == n


def test_zero_reviews_raises(db_session):
    with pytest.raises(RuntimeError):
        ingest_reviews(db_session, today=date(2026, 11, 17), fetcher=lambda p, w, m: [])
```

- [ ] **Step 3: Run to verify failure** → FAIL (module missing).

- [ ] **Step 4: Implement**

`api/app/weekly/reviews.py`:
```python
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
    stored = 0
    for raw in raws:
        row = scrub(raw)
        if row is None or not (start <= row["date"] <= today):
            continue
        db.merge(Review(**row))
        stored += 1
    db.commit()
    return IngestResult(fetched=len(raws), stored=stored, window_start=start, window_end=today)
```

- [ ] **Step 5: Run** → `pytest tests/test_reviews.py -q` → PASS.

- [ ] **Step 6: Commit** — `feat(weekly): Play Store ingest with identity drop and PII redaction` (+ Co-Authored-By).

---

### Task 4: Theme vocabulary and theme building (≤5, traced, top 3)

**Files:**
- Create: `api/app/weekly/vocab.py`, `api/app/weekly/themes.py`
- Test: `api/tests/test_themes.py`

**Interfaces:**
- Consumes: `Review` rows, `complete_json(system, user, fast=True)`
- Produces:
  - `vocab.THEME_VOCAB: dict[str, str]`: the 5 M2 ids → labels, with `fees_funding` relabelled "Fees, charges & funding"
  - `vocab.TEAMS: dict[str, str]`
  - `vocab.CUES: dict[str, list[str]]`: plain lowercase cue words for the Pattern agent
  - `vocab.DEFAULT_ACTIONS`
  - `vocab.keyword_scores(text) -> dict[str, int]`, `vocab.confident_theme_id(text) -> str | None`, `vocab.heuristic_theme_id(text) -> str`
  - `async themes.assign_themes(reviews: list[Review], *, max_llm: int = 48) -> tuple[dict[str, str], int]`: returns review_id → theme_id and the number of LLM calls. Confident keyword hits skip the LLM; ambiguous reviews go to the LLM in batches of 12 up to `max_llm`; the rest use the heuristic.
  - `themes.build_themes(assign: dict[str,str], reviews: list[Review], *, window_start, window_end, today) -> list[ThemeOut]`, where `ThemeOut` is a dataclass `(theme_id, label, count, recent_count, review_ids, window_start, window_end, rank)`. It returns at most 5, sorted by count desc then theme order, with rank 1..n; only themes with count > 0 are included; `recent_count` counts reviews dated within the last 7 days ending `today`.

- [ ] **Step 1: Port vocab**

```bash
cp C:/Users/dhruv/Groww-and-MCP/src/agent/vocab.py api/app/weekly/vocab.py
```
Edit `api/app/weekly/vocab.py`: change the `"fees_funding"` label to `"Fees, charges & funding"`, delete `keyword_hint`, and replace two `DEFAULT_ACTIONS` values whose verbs ("sell", "buy") the output advice filter would reject:
```python
    "trading_orders": (
        "Trace failed exit, stop-loss and square-off order executions end-to-end and ship "
        "regression tests for the top order-lifecycle breakages."
    ),
    "charts_market_data": (
        "Audit chart OHLC, average cost price, and holdings display accuracy "
        "against exchange feeds after recent UI updates."
    ),
```
Then append:
```python
TEAMS: Final[dict[str, str]] = {
    "trading_orders": "Trading platform",
    "charts_market_data": "Market data",
    "customer_support": "Customer support",
    "app_reliability": "App stability",
    "fees_funding": "Fees and mutual fund ops",
}

CUES: Final[dict[str, list[str]]] = {
    "trading_orders": ["order", "sell", "buy", "stop loss", "stop-loss", "ipo", "trade"],
    "charts_market_data": ["chart", "price", "holdings", "portfolio value"],
    "customer_support": ["support", "ticket", "no response", "kyc", "customer care"],
    "app_reliability": ["crash", "not working", "lag", "slow", "update", "error", "bug"],
    "fees_funding": ["exit load", "expense ratio", "brokerage", "charge", "fee", "deducted", "withdraw", "redeem"],
}
```

- [ ] **Step 2: Write the failing test**

`api/tests/test_themes.py`:
```python
import asyncio
from datetime import date

from app.models import Review
from app.weekly.themes import assign_themes, build_themes
from app.weekly.vocab import THEME_VOCAB


def rid(i):
    return "rv_" + "".join("abcdefghij"[int(c)] for c in f"{i:010d}")   # letters only, like real ids


def _r(i, text, d=date(2026, 11, 15), rating=1):
    return Review(id=rid(i), rating=rating, date=d, text_redacted=text)


REVIEWS = [
    _r(1, "App crashes after update"), _r(2, "Not working, lag and blank screen"),
    _r(3, "Exit load deducted, confusing charge"), _r(4, "Brokerage fee too high"),
    _r(5, "Support no response to my ticket"), _r(6, "Unable to sell, order stuck", d=date(2026, 10, 1)),
    _r(7, "Chart shows wrong price"), _r(8, "nice", rating=5),
]


def test_default_actions_pass_scope_filter():
    from app.guard.scope import check_output
    from app.weekly.vocab import DEFAULT_ACTIONS
    for a in DEFAULT_ACTIONS.values():
        assert [v.check for v in check_output(a, kind="pulse")] == [], a


def test_assign_without_llm_covers_all_and_uses_vocab():
    assign, calls = asyncio.run(assign_themes(REVIEWS))
    assert calls == 0 and set(assign) == {r.id for r in REVIEWS}
    assert set(assign.values()) <= set(THEME_VOCAB)
    assert assign[rid(3)] == "fees_funding" and assign[rid(1)] == "app_reliability"


def test_build_themes_capped_ranked_traced():
    assign, _ = asyncio.run(assign_themes(REVIEWS))
    themes = build_themes(assign, REVIEWS, window_start=date(2026, 9, 22), window_end=date(2026, 11, 17),
                          today=date(2026, 11, 17))
    assert 1 <= len(themes) <= 5 and [t.rank for t in themes] == list(range(1, len(themes) + 1))
    assert all(t.count == len(t.review_ids) > 0 for t in themes)
    assert sum(t.count for t in themes) == len(REVIEWS)
    assert all(t.window_start == date(2026, 9, 22) and t.window_end == date(2026, 11, 17) for t in themes)
    trading = next(t for t in themes if t.theme_id == "trading_orders")
    assert trading.recent_count == 0  # its only review is from Oct 1


def test_llm_labels_only_ambiguous_and_capped(monkeypatch):
    from app.weekly import themes as th
    seen = []

    async def fake_llm(system, user, *, fast=False):
        import json
        ids = [line.split("|")[0].strip() for line in user.splitlines() if line.startswith("rv_")]
        seen.append(len(ids))
        return {"labels": [{"id": i, "theme_id": "customer_support"} for i in ids]}
    monkeypatch.setattr(th, "complete_json", fake_llm)
    monkeypatch.setattr(th, "llm_enabled", lambda: True)
    many = [_r(100 + i, "meh okay") for i in range(60)]
    assign, calls = asyncio.run(assign_themes(many, max_llm=24))
    assert calls == 2 and sum(seen) == 24 and set(assign) == {r.id for r in many}
```

- [ ] **Step 3: Run to verify failure** → FAIL (module missing).

- [ ] **Step 4: Implement**

`api/app/weekly/themes.py`:
```python
"""Reviews → ≤5 fixed-vocabulary themes. Keyword rules first; fast LLM only for ambiguous, capped."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.llm.client import complete_json, llm_enabled
from app.models import Review
from app.weekly.vocab import THEME_VOCAB, confident_theme_id, heuristic_theme_id

_ORDER = list(THEME_VOCAB)
_SYSTEM = (
    "Label each Groww Play Store review with exactly one theme_id from: "
    + ", ".join(f"{k} ({v})" for k, v in THEME_VOCAB.items())
    + ". Mutual fund / SIP / exit load / charges → fees_funding. Generic complaint → app_reliability. "
    "Return JSON {\"labels\": [{\"id\": ..., \"theme_id\": ...}]} covering every id. Never invent ids."
)


@dataclass
class ThemeOut:
    theme_id: str
    label: str
    count: int
    recent_count: int
    review_ids: list[str] = field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None
    rank: int = 0


async def assign_themes(reviews: list[Review], *, max_llm: int = 48) -> tuple[dict[str, str], int]:
    out: dict[str, str] = {}
    ambiguous: list[Review] = []
    for r in reviews:
        tid = confident_theme_id(r.text_redacted)
        if tid:
            out[r.id] = tid
        else:
            ambiguous.append(r)
    calls = 0
    if llm_enabled():
        budget = ambiguous[:max_llm]
        for i in range(0, len(budget), 12):
            batch = budget[i:i + 12]
            user = "\n".join(f"{r.id} | {r.rating}★ | {r.text_redacted[:300]}" for r in batch)
            data = await complete_json(_SYSTEM, user, fast=True)
            calls += 1
            for item in (data or {}).get("labels", []):
                if item.get("id") in {r.id for r in batch} and item.get("theme_id") in THEME_VOCAB:
                    out[item["id"]] = item["theme_id"]
    for r in ambiguous:
        out.setdefault(r.id, heuristic_theme_id(r.text_redacted))
    return out, calls


def build_themes(assign: dict[str, str], reviews: list[Review], *, window_start: date, window_end: date,
                 today: date) -> list[ThemeOut]:
    by_id = {r.id: r for r in reviews}
    recent_start = today - timedelta(days=6)
    groups: dict[str, list[str]] = {}
    for rid, tid in assign.items():
        if rid in by_id:
            groups.setdefault(tid, []).append(rid)
    themes = [ThemeOut(theme_id=tid, label=THEME_VOCAB[tid], count=len(ids),
                       recent_count=sum(1 for i in ids if by_id[i].date >= recent_start),
                       review_ids=sorted(ids), window_start=window_start, window_end=window_end)
              for tid, ids in groups.items() if ids]
    themes.sort(key=lambda t: (-t.count, _ORDER.index(t.theme_id)))
    themes = themes[:5]
    for i, t in enumerate(themes, 1):
        t.rank = i
    return themes
```

- [ ] **Step 5: Run** → `pytest tests/test_themes.py -q` → PASS. If `confident_theme_id("nice")` returns a theme, that's fine; the assertion is only that every review gets a vocab theme.

- [ ] **Step 6: Commit** — `feat(weekly): fixed-vocabulary themes with capped LLM labelling` (+ Co-Authored-By).

---

### Task 5: Question keys and repeated questions (Link 1)

**Files:**
- Create: `api/app/link/__init__.py` (empty), `api/app/link/question_keys.py`, `api/app/weekly/fee_topics.py`
- Modify: `api/app/tickets/service.py` (`create_ticket` sets `question_key`)
- Test: `api/tests/test_question_keys.py`

**Interfaces:**
- Consumes: `IntentResult`, `Ticket`
- Produces:
  - `fee_topics.FEE_TOPICS: dict[str, tuple[str, ...]]` mapping topic → regex fragments, with topics `exit_load`, `expense_ratio`, `redemption_charges`, `brokerage`
  - `fee_topics.TOPIC_LABELS: dict[str, str]`
  - `fee_topics.topic_of(text) -> str | None`: the first topic whose pattern matches, in the order above
  - `question_key(intent: IntentResult, text: str) -> str`: `f"{intent}:{topic}"` + `f":{scheme}"` when exactly one scheme. `topic = intent.fact_key or topic_of(text) or "general"`.
  - `repeated_questions(db, *, now: datetime, threshold: int, days: int) -> list[RepeatedQuestion]`, where `RepeatedQuestion` is a dataclass `(key, label, count, window_start: date, window_end: date, ticket_codes: list[str])`. The window is the trailing `days` days ending `now` and inclusive of tickets created at or after `now - timedelta(days=days)`. Results are sorted by count desc.
  - `label_for(key) -> str`, e.g. `"fee_question:exit_load:hdfc-mid-cap-fund-direct-growth"` → `"Fee question · Exit load · HDFC Mid Cap Fund Direct Growth"`

- [ ] **Step 1: Write the failing test**

`api/tests/test_question_keys.py`:
```python
import asyncio
from datetime import datetime, timedelta, timezone

from app.intent.classifier import classify_intent
from app.link.question_keys import label_for, question_key, repeated_questions
from app.models import Ticket
from app.weekly.fee_topics import topic_of

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def qk(text):
    return question_key(asyncio.run(classify_intent(text)), text)


def test_keys():
    assert qk("What is the exit load of HDFC Mid Cap?") == "fee_question:exit_load:hdfc-mid-cap-fund-direct-growth"
    assert qk("why was exit load deducted?") == "fee_question:exit_load"
    assert qk("brokerage charges on groww") == "fee_question:brokerage"
    assert qk("weather today") == "out_of_scope:general"


def test_topic_of():
    assert topic_of("expense ratio confusion") == "expense_ratio"
    assert topic_of("charged when I redeemed my fund") == "redemption_charges"
    assert topic_of("hello") is None


def _ticket(db, i, key, age):
    db.add(Ticket(code=f"GRW-T{i:05d}", question_redacted="q", question_key=key, created_at=NOW - age))


def test_repeated_threshold_and_window(db_session):
    k1, k2 = "fee_question:exit_load", "fee_question:brokerage"
    for i in range(5):
        _ticket(db_session, i, k1, timedelta(days=i))                 # 5 within window
    _ticket(db_session, 10, k1, timedelta(days=7, seconds=1))         # just outside
    for i in range(4):
        _ticket(db_session, 20 + i, k2, timedelta(hours=i))           # only 4
    db_session.commit()
    rep = repeated_questions(db_session, now=NOW, threshold=5, days=7)
    assert [r.key for r in rep] == [k1] and rep[0].count == 5
    assert rep[0].window_start.isoformat() == "2026-11-10" and rep[0].window_end.isoformat() == "2026-11-17"
    assert len(rep[0].ticket_codes) == 5


def test_boundary_exactly_seven_days_is_inside(db_session):
    for i in range(4):
        _ticket(db_session, i, "k", timedelta(days=1))
    _ticket(db_session, 9, "k", timedelta(days=7))
    db_session.commit()
    assert repeated_questions(db_session, now=NOW, threshold=5, days=7)[0].count == 5


def test_create_ticket_sets_key(db_session):
    from app.tickets.service import create_ticket
    t, _ = asyncio.run(create_ticket(db_session, "What is the exit load of HDFC Mid Cap?"))
    assert t.question_key == "fee_question:exit_load:hdfc-mid-cap-fund-direct-growth"


def test_label():
    assert label_for("fee_question:exit_load:hdfc-mid-cap-fund-direct-growth") == \
        "Fee question · Exit load · HDFC Mid Cap Fund Direct Growth"
```

SQLite stores naive datetimes: in `repeated_questions` compare against `cutoff.replace(tzinfo=None)` when the column values are naive (see implementation).

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

`api/app/weekly/fee_topics.py`:
```python
"""Fee/charge confusion topics shared by question keys, review mining and explainers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FEE_TOPICS: dict[str, tuple[str, ...]] = {
    "exit_load": (r"exit[\s-]?load",),
    "expense_ratio": (r"expense[\s-]?ratio", r"\bter\b", r"total expense"),
    "redemption_charges": (r"(?:redeem\w*|redemption|withdraw\w*).{0,40}(?:charge\w*|fee\w*|deduct\w*|cut)",
                           r"(?:charge\w*|fee\w*|deduct\w*).{0,40}(?:redeem\w*|redemption|withdraw\w*)"),
    "brokerage": (r"brokerage", r"\bdp charge", r"hidden charge", r"\bcharges?\b", r"\bfees?\b"),
}
TOPIC_LABELS = {"exit_load": "Exit load", "expense_ratio": "Expense ratio",
                "redemption_charges": "Redemption charges", "brokerage": "Brokerage & charges"}
_COMPILED = {t: [re.compile("(?i)" + p) for p in ps] for t, ps in FEE_TOPICS.items()}


def topic_of(text: str) -> str | None:
    for topic, pats in _COMPILED.items():
        if any(p.search(text) for p in pats):
            return topic
    return None


@dataclass
class FeeConfusion:
    topic: str
    review_ids: list[str] = field(default_factory=list)
    ticket_count: int = 0

    @property
    def evidence(self) -> dict:
        return {"reviews": len(self.review_ids), "tickets": self.ticket_count, "review_ids": self.review_ids[:20]}


def detect_fee_confusion(reviews, ticket_keys: list[str]) -> FeeConfusion:
    """Most-mentioned fee topic across reviews + fee_question tickets; ties → FEE_TOPICS order; none → exit_load."""
    per: dict[str, FeeConfusion] = {t: FeeConfusion(t) for t in FEE_TOPICS}
    for r in reviews:
        t = topic_of(r.text_redacted)
        if t:
            per[t].review_ids.append(r.id)
    for k in ticket_keys:
        parts = k.split(":")
        if parts[0] == "fee_question" and len(parts) > 1 and parts[1] in per:
            per[parts[1]].ticket_count += 1
    order = list(FEE_TOPICS)
    best = max(per.values(), key=lambda f: (len(f.review_ids) + f.ticket_count, -order.index(f.topic)))
    return best if (len(best.review_ids) + best.ticket_count) > 0 else FeeConfusion("exit_load")
```

`api/app/link/question_keys.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import load_schemes
from app.intent.classifier import IntentResult
from app.models import Ticket
from app.weekly.fee_topics import TOPIC_LABELS, topic_of

_INTENT_LABELS = {"fee_question": "Fee question", "fund_fact": "Fund fact", "how_to_process": "How-to",
                  "advice_request": "Advice request", "performance_request": "Returns request",
                  "account_issue": "Account issue", "out_of_scope": "Out of scope"}


@dataclass
class RepeatedQuestion:
    key: str
    label: str
    count: int
    window_start: date
    window_end: date
    ticket_codes: list[str] = field(default_factory=list)


def question_key(intent: IntentResult, text: str) -> str:
    topic = intent.fact_key or topic_of(text) or "general"
    key = f"{intent.intent}:{topic}"
    if len(intent.scheme_ids) == 1:
        key += f":{intent.scheme_ids[0]}"
    return key


def label_for(key: str) -> str:
    parts = key.split(":")
    names = {s["scheme_id"]: s["scheme_name"] for s in load_schemes()["schemes"]}
    out = [_INTENT_LABELS.get(parts[0], parts[0])]
    if len(parts) > 1 and parts[1] != "general":
        out.append(TOPIC_LABELS.get(parts[1], parts[1].replace("_", " ").capitalize()))
    if len(parts) > 2:
        out.append(names.get(parts[2], parts[2]))
    return " · ".join(out)


def repeated_questions(db: Session, *, now: datetime, threshold: int, days: int) -> list[RepeatedQuestion]:
    cutoff = now - timedelta(days=days)
    rows = db.query(Ticket).filter(Ticket.question_key.isnot(None)).all()
    groups: dict[str, list[Ticket]] = {}
    for t in rows:
        created = t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=cutoff.tzinfo)
        if cutoff <= created <= now:
            groups.setdefault(t.question_key, []).append(t)
    out = [RepeatedQuestion(key=k, label=label_for(k), count=len(ts), window_start=cutoff.date(),
                            window_end=now.date(), ticket_codes=sorted(t.code for t in ts))
           for k, ts in groups.items() if len(ts) >= threshold]
    return sorted(out, key=lambda r: (-r.count, r.key))
```

In `api/app/tickets/service.py` `create_ticket`, add `question_key=question_key(intent, red.text),` to the `Ticket(...)` constructor and `from app.link.question_keys import question_key` at the top.

- [ ] **Step 4: Run** → `pytest tests/test_question_keys.py tests/test_tickets_api.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat(link): question keys and repeated-question detection (link 1)` (+ Co-Authored-By).

---

### Task 6: Fee explainer builder

**Files:**
- Create: `api/app/weekly/explainer.py`
- Test: `api/tests/test_fee_explainer.py`

**Interfaces:**
- Consumes: `reference_sentences(topic)`, `load_reference(topic)`, scheme facts in `settings.data_processed_dir/<scheme_id>.json` (M1 parsed docs: `sections[{fact_key, text}]`, `source_url`, `scheme_name`), `last_checked_for(db, url)`, `check_output`, `TOPIC_LABELS`
- Produces:
  - `RECIPES: dict[str, list[tuple]]`
  - `ExplainerDraft` dataclass `(topic, title, bullets: list[dict{text,url}], last_checked: str)`
  - `build_explainer(db, topic: str, *, schemes: list[str] | None = None) -> ExplainerDraft`. `schemes` is the scheme ids to illustrate (default: the 3 most-asked schemes in fee_question tickets, else mid cap, small cap, large cap).
  - `validate_explainer(d) -> list[str]`: problems; empty means valid. Checks: 1–6 bullets, each bullet has a url on an allowed host, ≥2 distinct urls, and each bullet passes `check_output(kind="reply")` advice/performance/pii.
  - `render_explainer(d) -> str`: markdown with title, bullets each ending `— Source: <url>`, and a final `Last checked: <date>` line.

Recipes (bullet sources in order; total capped at 6):
- `exit_load`: ref exit_load[0], ref redemption_charges[0], scheme exit_load × 3, ref exit_load[1]
- `expense_ratio`: ref expense_ratio[0], ref expense_ratio[1], scheme expense_ratio × 3
- `redemption_charges`: ref redemption_charges[0], ref redemption_charges[1], ref exit_load[0], scheme exit_load × 2
- `brokerage`: ref brokerage[0], ref brokerage[1], ref brokerage[2], ref redemption_charges[0]

- [ ] **Step 1: Write the failing test**

`api/tests/test_fee_explainer.py`:
```python
from pathlib import Path

import pytest

from app.weekly.explainer import build_explainer, render_explainer, validate_explainer
from app.guard.scope import bullet_count

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    return db_session


@pytest.mark.parametrize("topic", ["exit_load", "expense_ratio", "redemption_charges", "brokerage"])
def test_each_topic_builds_valid_explainer(corpus, topic):
    d = build_explainer(corpus, topic)
    assert validate_explainer(d) == [], validate_explainer(d)
    assert 1 <= len(d.bullets) <= 6 and len({b["url"] for b in d.bullets}) >= 2
    md = render_explainer(d)
    assert bullet_count(md) == len(d.bullets) and f"Last checked: {d.last_checked}" in md


def test_exit_load_uses_scheme_facts_with_their_urls(corpus):
    d = build_explainer(corpus, "exit_load", schemes=["hdfc-mid-cap-fund-direct-growth"])
    scheme = [b for b in d.bullets if "mid-cap" in b["url"]]
    assert scheme and "exit load" in scheme[0]["text"].lower()


def test_validate_catches_bad_drafts(corpus):
    d = build_explainer(corpus, "exit_load")
    d.bullets = d.bullets[:1]
    assert any("distinct" in p for p in validate_explainer(d))
    d.bullets = [{"text": "You should buy now.", "url": "https://groww.in/x"}] * 7
    probs = validate_explainer(d)
    assert any("bullets" in p for p in probs) and any("advice" in p for p in probs)
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

`api/app/weekly/explainer.py`:
```python
"""Fee explainer: extractive, facts-only bullets from official reference pages + scheme fact sections."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings, is_allowed_source_url
from app.corpus.reference import load_reference, reference_sentences
from app.corpus.refresh import last_checked_for
from app.guard.scope import check_output
from app.models import Ticket
from app.weekly.fee_topics import TOPIC_LABELS

DEFAULT_SCHEMES = ["hdfc-mid-cap-fund-direct-growth", "hdfc-small-cap-fund-direct-growth",
                   "hdfc-large-cap-fund-direct-growth"]
RECIPES: dict[str, list[tuple]] = {
    "exit_load": [("ref", "exit_load", 0), ("ref", "redemption_charges", 0), ("scheme", "exit_load", 3),
                  ("ref", "exit_load", 1)],
    "expense_ratio": [("ref", "expense_ratio", 0), ("ref", "expense_ratio", 1), ("scheme", "expense_ratio", 3)],
    "redemption_charges": [("ref", "redemption_charges", 0), ("ref", "redemption_charges", 1),
                           ("ref", "exit_load", 0), ("scheme", "exit_load", 2)],
    "brokerage": [("ref", "brokerage", 0), ("ref", "brokerage", 1), ("ref", "brokerage", 2),
                  ("ref", "redemption_charges", 0)],
}


@dataclass
class ExplainerDraft:
    topic: str
    title: str
    bullets: list[dict] = field(default_factory=list)
    last_checked: str = ""


def _scheme_fact(scheme_id: str, fact_key: str) -> dict | None:
    p = Path(get_settings().data_processed_dir) / f"{scheme_id}.json"
    if not p.exists():
        return None
    doc = json.loads(p.read_text(encoding="utf-8"))
    for s in doc.get("sections", []):
        if s.get("fact_key") == fact_key:
            return {"text": s["text"].strip().rstrip(".") + ".", "url": doc["source_url"]}
    return None


def _top_schemes(db: Session, n: int) -> list[str]:
    rows = (db.query(Ticket.scheme_id, func.count()).filter(Ticket.intent == "fee_question",
            Ticket.scheme_id.isnot(None)).group_by(Ticket.scheme_id).order_by(func.count().desc()).limit(n).all())
    picked = [r[0] for r in rows]
    return (picked + [s for s in DEFAULT_SCHEMES if s not in picked])[:n]


def build_explainer(db: Session, topic: str, *, schemes: list[str] | None = None) -> ExplainerDraft:
    bullets: list[dict] = []
    for step in RECIPES[topic]:
        if step[0] == "ref":
            sents, doc = reference_sentences(step[1]), load_reference(step[1])
            if doc and len(sents) > step[2]:
                bullets.append({"text": sents[step[2]], "url": doc.url})
        else:
            for sid in (schemes or _top_schemes(db, step[2]))[:step[2]]:
                f = _scheme_fact(sid, step[1])
                if f:
                    bullets.append(f)
    seen, unique = set(), []
    for b in bullets:
        if b["text"] not in seen:
            seen.add(b["text"]); unique.append(b)
    unique = unique[:6]
    dates = [d for d in (last_checked_for(db, b["url"]) for b in unique) if d]
    return ExplainerDraft(topic=topic, title=f"{TOPIC_LABELS[topic]} — what the official sources say",
                          bullets=unique, last_checked=min(dates) if dates else "")


def validate_explainer(d: ExplainerDraft) -> list[str]:
    probs: list[str] = []
    if not 1 <= len(d.bullets) <= 6:
        probs.append(f"explainer has {len(d.bullets)} bullets (must be 1-6)")
    if len({b.get("url") for b in d.bullets}) < 2:
        probs.append("explainer needs at least 2 distinct official source links")
    if not d.last_checked:
        probs.append("missing last-checked date")
    for i, b in enumerate(d.bullets, 1):
        if not b.get("url") or not is_allowed_source_url(b["url"]):
            probs.append(f"bullet {i} has no allowed source url")
        for v in check_output(b.get("text", ""), kind="reply"):
            if v.check != "shape":
                probs.append(f"bullet {i}: {v.check}")
    return probs


def render_explainer(d: ExplainerDraft) -> str:
    lines = [f"## {d.title}", ""]
    lines += [f"- {b['text']} — Source: {b['url']}" for b in d.bullets]
    lines += ["", f"Last checked: {d.last_checked}"]
    return "\n".join(lines)
```

- [ ] **Step 4: Run** → `pytest tests/test_fee_explainer.py -q` → PASS. If the brokerage reference yields fewer than 3 sentences, the recipe simply yields fewer bullets; the test only requires validity.

- [ ] **Step 5: Commit** — `feat(weekly): extractive fee explainer with ≥2 official links` (+ Co-Authored-By).

---

### Task 7: Pulse composer (quotes, repeated questions, fee confusion, 3 actions)

**Files:**
- Create: `api/app/weekly/pulse.py`
- Test: `api/tests/test_pulse.py`

**Interfaces:**
- Consumes: `ThemeOut`, `RepeatedQuestion`, `FeeConfusion`, `Review`, `complete_json`, vocab `DEFAULT_ACTIONS`, `TOPIC_LABELS`, `check_output`, `word_count`
- Produces:
  - `select_quotes(themes: list[ThemeOut], reviews_by_id: dict[str, Review], *, max_words: int = 24) -> list[Quote]`, where `Quote` is a dataclass `(review_id, theme_id, text)`. It takes one quote per top-3 theme. Candidates have rating ≤ 2 (else any rating) and pass advice/performance/PII checks; it picks the most recent. Text is a verbatim prefix ≤ `max_words` words + "…" when cut.
  - `async action_ideas(themes, quotes) -> tuple[list[str], int]`: exactly 3 action strings and the LLM call count (0 or 1). The LLM is used only if enabled and its output passes `check_output(kind="pulse")` advice/performance/PII; otherwise `DEFAULT_ACTIONS` for the top-3 themes, padded with remaining defaults.
  - `compose_pulse(*, week_end: date, window_start: date, window_end: date, review_count: int, themes, quotes, repeated, fee: FeeConfusion, actions: list[str]) -> str`: deterministic markdown. If > 250 words it retries with quote `max_words=14`, then repeated list cut to 3.
  - `validate_pulse(text) -> list[str]`: word cap, "Action ideas" section with exactly 3 numbered items, advice/performance/PII outside quoted lines.

Pulse template:
```
# Groww Weekly Review Pulse — week ending {week_end}
{review_count} Play Store reviews, {window_start} to {window_end}.

## Top themes
1. {label} — {count} reviews ({recent} in last 7 days)
...
## What users said
- "{quote}" ({review_id})
...
## Asked repeatedly ({window_start}–{window_end})
- {label}: {count} questions
(or) - No question reached {threshold} asks in this window.
## Fee confusion
- {topic label}: {n_reviews} reviews and {n_tickets} questions → explainer below.
## Action ideas
1. ...
2. ...
3. ...
```

- [ ] **Step 1: Write the failing test**

`api/tests/test_pulse.py`:
```python
import asyncio
from datetime import date

from app.link.question_keys import RepeatedQuestion
from app.models import Review
from app.weekly.fee_topics import FeeConfusion
from app.weekly.pulse import action_ideas, compose_pulse, select_quotes, validate_pulse
from app.weekly.themes import ThemeOut

W0, W1 = date(2026, 9, 22), date(2026, 11, 17)


def rid(i):
    return "rv_" + "".join("abcdefghij"[int(c)] for c in f"{i:010d}")


def _rev(i, text, rating=1, d=date(2026, 11, 15)):
    return Review(id=rid(i), rating=rating, date=d, text_redacted=text)


REVS = {r.id: r for r in [
    _rev(1, "App crashes every time I open the portfolio screen after the latest update"),
    _rev(2, "You should sell this app, it gave 20% returns then crashed"),        # advice+perf → never quoted
    _rev(3, "Exit load deducted on redemption and nobody explained the exit load to me"),
    _rev(4, "Support never replied to my ticket for two weeks"),
]}


def _themes(n=3):
    base = [ThemeOut("app_reliability", "App reliability & updates", 2, 2, [rid(1), rid(2)], W0, W1, 1),
            ThemeOut("fees_funding", "Fees, charges & funding", 1, 1, [rid(3)], W0, W1, 2),
            ThemeOut("customer_support", "Customer support", 1, 1, [rid(4)], W0, W1, 3)]
    return base[:n]


def _pulse(themes, repeated=None, fee=None):
    quotes = select_quotes(themes, REVS)
    actions, _ = asyncio.run(action_ideas(themes, quotes))
    return compose_pulse(week_end=W1, window_start=W0, window_end=W1, review_count=4, themes=themes, quotes=quotes,
                         repeated=repeated or [], fee=fee or FeeConfusion("exit_load", [rid(3)], 2),
                         actions=actions)


def test_quotes_verbatim_and_safe():
    quotes = select_quotes(_themes(), REVS)
    assert [q.theme_id for q in quotes] == ["app_reliability", "fees_funding", "customer_support"]
    assert all(q.text.rstrip("…").strip() in REVS[q.review_id].text_redacted for q in quotes)
    assert all(q.review_id != rid(2) for q in quotes)


def test_actions_default_to_three_without_llm():
    actions, calls = asyncio.run(action_ideas(_themes(), select_quotes(_themes(), REVS)))
    assert len(actions) == 3 and calls == 0


def test_pulse_valid_and_capped():
    rq = [RepeatedQuestion("fee_question:exit_load", "Fee question · Exit load", 6, date(2026, 11, 10), W1, ["a"] * 6)]
    text = _pulse(_themes(), repeated=rq)
    assert validate_pulse(text) == [], validate_pulse(text)
    assert "Fee question · Exit load: 6 questions" in text and "2026-11-10" in text
    assert f"({rid(1)})" in text


def test_quiet_week_one_theme_no_repeats_still_valid():
    text = _pulse(_themes(1), fee=FeeConfusion("exit_load"))
    assert validate_pulse(text) == [] and "No question reached" in text and "0 reviews and 0 questions" in text


def test_long_inputs_are_trimmed_to_cap():
    long_rev = {rid(i): _rev(i, " ".join(["slowness"] * 80)) for i in range(10, 13)}
    themes = [ThemeOut("app_reliability", "App reliability & updates", 3, 3, list(long_rev), W0, W1, 1)]
    rq = [RepeatedQuestion(f"fee_question:k{i}", "Fee question · " + "x" * 40, 9, W0, W1, []) for i in range(8)]
    quotes = select_quotes(themes, long_rev)
    actions, _ = asyncio.run(action_ideas(themes, quotes))
    text = compose_pulse(week_end=W1, window_start=W0, window_end=W1, review_count=3, themes=themes, quotes=quotes,
                         repeated=rq, fee=FeeConfusion("exit_load"), actions=actions)
    assert validate_pulse(text) == []
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

`api/app/weekly/pulse.py`:
```python
"""Weekly pulse: deterministic template over themes, verbatim quotes, repeated questions, fee confusion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.config import get_settings
from app.guard.pii import find_pii
from app.guard.scope import check_output, detect_advice, detect_performance, word_count
from app.llm.client import complete_json, llm_enabled
from app.weekly.fee_topics import TOPIC_LABELS, FeeConfusion
from app.weekly.vocab import DEFAULT_ACTIONS


@dataclass
class Quote:
    review_id: str
    theme_id: str
    text: str


def _safe(t: str) -> bool:
    return not (detect_advice(t) or detect_performance(t) or find_pii(t))


def _cut(t: str, n: int) -> str:
    w = t.split()
    return t if len(w) <= n else " ".join(w[:n]) + "…"


def select_quotes(themes, reviews_by_id, *, max_words: int = 24) -> list[Quote]:
    out: list[Quote] = []
    for t in themes[:3]:
        cands = [reviews_by_id[i] for i in t.review_ids if i in reviews_by_id and _safe(reviews_by_id[i].text_redacted)]
        low = [r for r in cands if r.rating <= 2] or cands
        if low:
            r = max(low, key=lambda r: (r.date, r.id))
            out.append(Quote(r.id, t.theme_id, _cut(r.text_redacted, max_words)))
    return out


_ACT_SYSTEM = (
    "You are writing exactly 3 internal action ideas for Groww's product and support teams, grounded only in the "
    "themes and quotes given. Each is one sentence starting with a verb (Audit, Trace, Clarify, Reduce...). No "
    "investment advice, no return figures, no PII. Return JSON {\"actions\": [\"...\", \"...\", \"...\"]}."
)


async def action_ideas(themes, quotes) -> tuple[list[str], int]:
    defaults = [DEFAULT_ACTIONS[t.theme_id] for t in themes[:3]]
    defaults += [a for k, a in DEFAULT_ACTIONS.items() if a not in defaults]
    defaults = defaults[:3]
    if not llm_enabled():
        return defaults, 0
    user = "\n".join([f"Theme {t.rank}: {t.label} ({t.count} reviews)" for t in themes[:3]] +
                     [f'Quote: "{q.text}"' for q in quotes])
    data = await complete_json(_ACT_SYSTEM, user)
    acts = [a.strip() for a in (data or {}).get("actions", []) if isinstance(a, str) and a.strip()]
    ok = len(acts) == 3 and all(not [v for v in check_output(a, kind="pulse") if v.check != "shape"] for a in acts)
    return (acts if ok else defaults), 1


def _render(*, week_end, window_start, window_end, review_count, themes, quotes, repeated, fee, actions,
            threshold) -> str:
    L = [f"# Groww Weekly Review Pulse — week ending {week_end.isoformat()}",
         f"{review_count} Play Store reviews, {window_start.isoformat()} to {window_end.isoformat()}.", "",
         "## Top themes"]
    L += [f"{t.rank}. {t.label} — {t.count} reviews ({t.recent_count} in last 7 days)" for t in themes[:3]]
    if len(themes) < 3:
        L.append(f"(Only {len(themes)} theme(s) had reviews in this window.)")
    L += ["", "## What users said"] + [f'- "{q.text}" ({q.review_id})' for q in quotes]
    rq_start = repeated[0].window_start.isoformat() if repeated else ""
    L += ["", f"## Asked repeatedly{f' ({rq_start} to {repeated[0].window_end.isoformat()})' if repeated else ''}"]
    L += [f"- {r.label}: {r.count} questions" for r in repeated] or \
         [f"- No question reached {threshold} asks in the last 7 days."]
    ev = fee.evidence
    L += ["", "## Fee confusion",
          f"- {TOPIC_LABELS[fee.topic]}: {ev['reviews']} reviews and {ev['tickets']} questions → explainer below.",
          "", "## Action ideas"] + [f"{i}. {a}" for i, a in enumerate(actions[:3], 1)]
    return "\n".join(L)


def compose_pulse(*, week_end: date, window_start: date, window_end: date, review_count: int, themes, quotes,
                  repeated, fee: FeeConfusion, actions: list[str]) -> str:
    th = get_settings().repeat_threshold
    args = dict(week_end=week_end, window_start=window_start, window_end=window_end, review_count=review_count,
                themes=themes, fee=fee, actions=actions, threshold=th)
    text = _render(quotes=quotes, repeated=repeated, **args)
    if word_count(text) > 250:
        short = [Quote(q.review_id, q.theme_id, _cut(q.text.rstrip("…"), 14)) for q in quotes]
        text = _render(quotes=short, repeated=repeated, **args)
    if word_count(text) > 250:
        text = _render(quotes=[Quote(q.review_id, q.theme_id, _cut(q.text.rstrip("…"), 14)) for q in quotes],
                       repeated=repeated[:3], **args)
    return text


def validate_pulse(text: str) -> list[str]:
    probs: list[str] = []
    n = word_count(text)
    if n > 250:
        probs.append(f"pulse has {n} words (cap 250)")
    m = re.search(r"## Action ideas\n((?:\d+\..*\n?)+)", text)
    if not m or len(re.findall(r"(?m)^\d+\.", m.group(1))) != 3:
        probs.append("pulse must have exactly 3 action ideas")
    body = "\n".join(l for l in text.splitlines() if not l.startswith('- "'))
    for v in check_output(body, kind="pulse"):
        if v.check != "shape":
            probs.append(f"pulse {v.check}: {v.detail}")
    if find_pii(text):
        probs.append("pulse contains PII")
    return probs
```

- [ ] **Step 4: Run** → `pytest tests/test_pulse.py -q` → PASS. If `validate_pulse` flags a DEFAULT_ACTIONS string, reword that default in `vocab.py` rather than weakening the filter, and record a ruling.

- [ ] **Step 5: Commit** — `feat(weekly): pulse composer with verbatim safe quotes, link-1 section, 3 actions` (+ Co-Authored-By).

---

### Task 8: Weekly run orchestration and pending actions

**Files:**
- Create: `api/app/weekly/run.py`
- Test: `api/tests/test_weekly_run.py`

**Interfaces:**
- Consumes: Tasks 3–7, `audit`, `Action`, `WeeklyRun`, `Theme`, `Explainer`, `Review`, `Ticket`, settings
- Produces: `async run_weekly(db, *, now: datetime, fetcher=play_store_fetcher) -> WeeklyRun`. Steps: create run (`running`) → `ingest_reviews` → load window reviews → `assign_themes` → `build_themes` → persist `Theme` rows → `repeated_questions` → `detect_fee_confusion(reviews, recent ticket keys)` → `build_explainer` → `select_quotes`/`action_ideas`/`compose_pulse` → validate both. On any problem: run `failed` with `error` (problems joined), no actions, explainer not saved. On success: persist `Explainer(status="draft", run_id, evidence)`, `run.pulse_text`, `run.llm_calls`, and two pending actions, then run `awaiting_approval`, `finished_at` set, audit rows.
  - `Action(type="doc_append", target_label=f"Append to Google Doc '{doc_title}' ({pulse_doc_id or 'PULSE_DOC_ID not set'})", target_ref=pulse_doc_id or "PULSE_DOC_ID", content=pulse + "\n\n" + render_explainer(explainer), source_ref=f"weekly_run:{run.id}")`
  - `Action(type="email_draft", target_label="Gmail draft to the product team (PULSE_DRAFT_RECIPIENT)", target_ref="PULSE_DRAFT_RECIPIENT", content=f"Subject: Groww weekly pulse — week ending {date}\n\n" + same body, source_ref=...)`
  - `doc_title = "Groww Weekly Pulse"`.
  - Exceptions inside the run (fetch failure etc.) → `failed` with `type(exc).__name__: message-redacted`; never raises out.

- [ ] **Step 1: Write the failing test**

`api/tests/test_weekly_run.py`:
```python
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.guard.scope import word_count
from app.models import Action, Explainer, Theme, WeeklyRun
from app.weekly.run import run_weekly

FIX = Path(__file__).parent / "fixtures"
RAW = json.loads((FIX / "reviews.json").read_text())
NOW = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def corpus(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    return db_session


def run(db, fetcher=lambda p, w, m: [dict(r) for r in RAW]):
    return asyncio.run(run_weekly(db, now=NOW, fetcher=fetcher))


def test_full_run_without_manual_steps(corpus):
    r = run(corpus)
    assert r.status == "awaiting_approval", r.error
    themes = corpus.query(Theme).filter_by(run_id=r.id).order_by(Theme.rank).all()
    assert 1 <= len(themes) <= 5 and all(t.review_ids and t.window_start and t.window_end for t in themes)
    assert word_count(r.pulse_text) <= 250
    ex = corpus.query(Explainer).filter_by(run_id=r.id).one()
    assert ex.status == "draft" and 1 <= len(ex.bullets) <= 6
    acts = corpus.query(Action).filter_by(source_ref=f"weekly_run:{r.id}").all()
    assert sorted(a.type for a in acts) == ["doc_append", "email_draft"] and all(a.status == "pending" for a in acts)
    assert all("Last checked:" in a.content for a in acts)


def test_fetch_failure_marks_failed_and_keeps_previous(corpus):
    first = run(corpus)
    def boom(p, w, m):
        raise RuntimeError("network down")
    second = run(corpus, fetcher=boom)
    assert second.status == "failed" and "network down" in second.error
    assert corpus.query(Action).filter_by(source_ref=f"weekly_run:{second.id}").count() == 0
    assert corpus.query(Theme).filter_by(run_id=first.id).count() >= 1


def test_zero_reviews_fails_cleanly(corpus):
    r = run(corpus, fetcher=lambda p, w, m: [])
    assert r.status == "failed" and "0 reviews" in r.error


def test_no_pii_in_run_outputs(corpus):
    r = run(corpus)
    blob = r.pulse_text + " ".join(a.content for a in corpus.query(Action))
    for raw in ("Real Person", "9876543210", "ABCDE1234F", "ravi.k@example.com"):
        assert raw not in blob
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

`api/app/weekly/run.py`:
```python
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
DOC_TITLE = "Groww Weekly Pulse"


async def run_weekly(db: Session, *, now: datetime, fetcher=play_store_fetcher) -> WeeklyRun:
    s = get_settings()
    today = now.date()
    run = WeeklyRun(status="running", window_start=today - timedelta(weeks=s.reviews_weeks), window_end=today)
    db.add(run); db.commit()
    try:
        ing = ingest_reviews(db, today=today, fetcher=fetcher)
        reviews = db.query(Review).filter(Review.date >= ing.window_start, Review.date <= ing.window_end).all()
        run.review_count = len(reviews)
        assign, calls = await assign_themes(reviews)
        themes = build_themes(assign, reviews, window_start=ing.window_start, window_end=ing.window_end, today=today)
        for t in themes:
            db.add(Theme(run_id=run.id, theme_id=t.theme_id, label=t.label, count=t.count, recent_count=t.recent_count,
                         review_ids=t.review_ids, window_start=t.window_start, window_end=t.window_end, rank=t.rank))
        repeated = repeated_questions(db, now=now, threshold=s.repeat_threshold, days=s.repeat_days)
        cutoff = now - timedelta(days=s.repeat_days)
        keys = [t.question_key for t in db.query(Ticket).filter(Ticket.question_key.isnot(None)).all()
                if (t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)) >= cutoff]
        fee = detect_fee_confusion(reviews, keys)
        draft = build_explainer(db, fee.topic)
        by_id = {r.id: r for r in reviews}
        quotes = select_quotes(themes, by_id)
        actions, act_calls = await action_ideas(themes, quotes)
        pulse = compose_pulse(week_end=today, window_start=ing.window_start, window_end=ing.window_end,
                              review_count=len(reviews), themes=themes, quotes=quotes, repeated=repeated, fee=fee,
                              actions=actions)
        problems = validate_pulse(pulse) + validate_explainer(draft)
        run.llm_calls = calls + act_calls
        if problems:
            raise ValueError("; ".join(problems))
        ex = Explainer(run_id=run.id, topic=draft.topic, title=draft.title, bullets=draft.bullets,
                       last_checked=draft.last_checked, status="draft", evidence=fee.evidence)
        db.add(ex)
        body = pulse + "\n\n" + render_explainer(draft)
        doc = Action(type="doc_append", target_ref=s.pulse_doc_id or "PULSE_DOC_ID",
                     target_label=f"Append to Google Doc '{DOC_TITLE}' ({s.pulse_doc_id or 'PULSE_DOC_ID not set'})",
                     content=body, source_ref=f"weekly_run:{run.id}")
        mail = Action(type="email_draft", target_ref="PULSE_DRAFT_RECIPIENT",
                      target_label="Gmail draft to the product team (PULSE_DRAFT_RECIPIENT)",
                      content=f"Subject: Groww weekly pulse — week ending {today.isoformat()}\n\n{body}",
                      source_ref=f"weekly_run:{run.id}")
        db.add_all([doc, mail]); db.flush()
        run.pulse_text, run.status, run.finished_at = pulse, "awaiting_approval", datetime.now(timezone.utc)
        audit(db, "scheduler", "create", "weekly_run", run.id, f"themes={len(themes)} fee={fee.topic}")
        audit(db, "scheduler", "create", "action", doc.id, "doc_append")
        audit(db, "scheduler", "create", "action", mail.id, "email_draft")
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(WeeklyRun, run.id)
        run.status, run.finished_at = "failed", datetime.now(timezone.utc)
        run.error = redact(f"{type(exc).__name__}: {exc}").text[:1000]
        audit(db, "scheduler", "fail", "weekly_run", run.id, run.error)
        db.commit()
        log.warning("weekly run %s failed: %s", run.id, run.error)
    return run
```
On failure the `db.rollback()` discards that run's Theme rows; the run row itself was committed first, so it survives.

- [ ] **Step 4: Run** → `pytest tests/test_weekly_run.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat(weekly): run orchestration with validation and pending doc/email actions` (+ Co-Authored-By).

---

### Task 9: Action executors and Link 2 canonicalization

**Files:**
- Create: `api/app/approvals/executors.py`
- Modify: `api/app/approvals/service.py` (`approve` dispatches; doc_append success → canonical)
- Test: `api/tests/test_executors_link2.py`

**Interfaces:**
- Consumes: `_claim`, `audit`, `Explainer`, `WeeklyRun`, `Action`, settings `data_outbox_dir`
- Produces:
  - `executors.EXECUTORS: dict[str, Callable[[Session, Action], str]]`: returns a result reference string; raises on failure
  - `executors.register(type, fn)`
  - Default executors: `reply_publish` (moved from approve), `doc_append` and `email_draft`, which write `outbox/<action_id>-<type>.md` and return the path (interim until Plan 3)
  - `service.mark_canonical(db, explainer_id) -> Explainer`: sets `canonical`/`canonical_at`; any other `canonical` explainer with the same topic → `superseded`
  - `approve()` behaviour: claim (`approved`) → executor. On success: `executed` + `executed_at`, audit approve+execute, and if `doc_append` → `mark_canonical` for the run's explainer. On exception: `failed` + `error` (redacted), audit approve+fail, no canonicalization; it returns the action without raising.
  - `reject()` on a `doc_append`: the action `rejected`, and the run's draft explainer → `rejected`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_executors_link2.py`:
```python
from datetime import date

import pytest

from app.approvals import executors
from app.approvals.service import approve, reject
from app.models import Action, Explainer, WeeklyRun


@pytest.fixture()
def run(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "data_outbox_dir", tmp_path / "outbox")
    r = WeeklyRun(status="awaiting_approval", window_start=date(2026, 9, 22), window_end=date(2026, 11, 17))
    db_session.add(r); db_session.flush()
    ex = Explainer(run_id=r.id, topic="exit_load", title="t", bullets=[{"text": "a", "url": "https://groww.in/a"}],
                   last_checked="2026-11-17", status="draft", evidence={})
    doc = Action(type="doc_append", target_label="doc", target_ref="D", content="PULSE", source_ref=f"weekly_run:{r.id}")
    mail = Action(type="email_draft", target_label="mail", target_ref="M", content="PULSE", source_ref=f"weekly_run:{r.id}")
    db_session.add_all([ex, doc, mail]); db_session.commit()
    return r, ex, doc, mail


def test_doc_approve_executes_only_doc_and_canonicalizes(db_session, run, tmp_path):
    r, ex, doc, mail = run
    approve(db_session, doc.id, "agent")
    db_session.expire_all()
    assert db_session.get(Action, doc.id).status == "executed"
    assert db_session.get(Action, mail.id).status == "pending"
    assert db_session.get(Explainer, ex.id).status == "canonical"
    assert len(list((tmp_path / "outbox").iterdir())) == 1


def test_email_first_does_not_canonicalize(db_session, run):
    r, ex, doc, mail = run
    approve(db_session, mail.id, "agent")
    db_session.expire_all()
    assert db_session.get(Explainer, ex.id).status == "draft"


def test_reject_doc_rejects_explainer(db_session, run):
    r, ex, doc, mail = run
    reject(db_session, doc.id, "agent")
    db_session.expire_all()
    assert db_session.get(Explainer, ex.id).status == "rejected" and db_session.get(Action, mail.id).status == "pending"


def test_second_approve_raises(db_session, run):
    r, ex, doc, mail = run
    approve(db_session, doc.id, "agent")
    with pytest.raises(ValueError):
        approve(db_session, doc.id, "agent")


def test_executor_failure_marks_failed_no_canonical(db_session, run, monkeypatch):
    r, ex, doc, mail = run
    def boom(db, a):
        raise RuntimeError("mcp down for ABCDE1234F")
    monkeypatch.setitem(executors.EXECUTORS, "doc_append", boom)
    a = approve(db_session, doc.id, "agent")
    db_session.expire_all()
    a = db_session.get(Action, doc.id)
    assert a.status == "failed" and "ABCDE1234F" not in a.error
    assert db_session.get(Explainer, ex.id).status == "draft"


def test_new_canonical_supersedes_old(db_session, run):
    r, ex, doc, mail = run
    old = Explainer(topic="exit_load", title="old", bullets=[], last_checked="2026-11-01", status="canonical", evidence={})
    db_session.add(old); db_session.commit()
    approve(db_session, doc.id, "agent")
    db_session.expire_all()
    assert db_session.get(Explainer, old.id).status == "superseded"
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError: app.approvals.executors`).

- [ ] **Step 3: Implement**

`api/app/approvals/executors.py`:
```python
"""Per-action-type executors. Plan 3 registers MCP-backed doc_append / email_draft over these outbox ones."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
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


def _outbox(db: Session, a: Action) -> str:
    out = Path(get_settings().data_outbox_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{a.id}-{a.type}.md"
    p.write_text(f"<!-- target: {a.target_label} -->\n{a.content}", encoding="utf-8")
    return str(p)


register("reply_publish", _reply_publish)
register("doc_append", _outbox)
register("email_draft", _outbox)
```

Rewrite `approve` and `reject` in `api/app/approvals/service.py` (keep `_claim`, `_get`, `audit`, `edit_draft` as they are):
```python
def mark_canonical(db: Session, explainer_id: int) -> Explainer:
    ex = db.get(Explainer, explainer_id)
    for other in db.query(Explainer).filter(Explainer.topic == ex.topic, Explainer.status == "canonical",
                                            Explainer.id != ex.id):
        other.status = "superseded"
    ex.status, ex.canonical_at = "canonical", _now()
    return ex


def _run_explainer(db: Session, a: Action) -> Explainer | None:
    if not a.source_ref.startswith("weekly_run:"):
        return None
    run_id = int(a.source_ref.split(":", 1)[1])
    return db.query(Explainer).filter_by(run_id=run_id).order_by(Explainer.id.desc()).first()


def approve(db: Session, action_id: int, actor: str) -> Action:
    from app.approvals.executors import EXECUTORS
    a = _get(db, action_id)
    if a.type not in EXECUTORS:
        raise ValueError(f"no executor for {a.type}")
    if a.type == "reply_publish" and db.get(Draft, a.draft_id).review_status == "blocked":
        raise ValueError("blocked draft cannot be approved; edit it first")
    _claim(db, action_id, "approved")
    db.refresh(a)
    audit(db, actor, "approve", "action", a.id)
    try:
        ref = EXECUTORS[a.type](db, a)
    except Exception as exc:  # noqa: BLE001
        a.status, a.error = "failed", redact(f"{type(exc).__name__}: {exc}").text[:500]
        audit(db, actor, "fail", "action", a.id, a.error)
        db.commit()
        return a
    a.status, a.executed_at = "executed", _now()
    audit(db, actor, "execute", "action", a.id, ref)
    if a.type == "doc_append":
        ex = _run_explainer(db, a)
        if ex is not None:
            mark_canonical(db, ex.id)
            audit(db, actor, "canonical", "explainer", ex.id, ex.topic)
    db.commit()
    return a


def reject(db: Session, action_id: int, actor: str) -> Action:
    a = _get(db, action_id)
    _claim(db, action_id, "rejected")
    db.refresh(a)
    audit(db, actor, "reject", "action", a.id)
    if a.type == "doc_append":
        ex = _run_explainer(db, a)
        if ex is not None and ex.status == "draft":
            ex.status = "rejected"
    db.commit()
    return a
```
Add `Explainer` to the models import in service.py. The `reply_publish` path previously audited `approve` then `execute` with detail `published to ticket {code}`; the new detail `ticket:{code}` keeps the same 2 audit rows. Plan 1's `test_approve_one_does_not_touch_other` still expects actions/tickets/2 audits, which this preserves.

- [ ] **Step 4: Run** → `pytest tests/test_executors_link2.py tests/test_approvals.py tests/test_review_fixes.py tests/test_tickets_api.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat(approvals): executor registry, outbox delivery, explainer canonical on doc approve (link 2)` (+ Co-Authored-By).

---

### Task 10: Canonical explainer reuse in the response loop

**Files:**
- Create: `api/app/link/canonical.py`
- Modify: `api/app/tickets/service.py` (`process_ticket`)
- Test: `api/tests/test_canonical.py`

**Interfaces:**
- Consumes: `Explainer`, `IntentResult`, `topic_of`, `covered_reply`, `review_draft`, `FactsResult`, `OrchestratorOutput`, `RoutingNote`, `last_checked`
- Produces:
  - `find_canonical(db, intent: IntentResult, text: str) -> Explainer | None`: only for `fee_question`; `topic = intent.fact_key if in FEE_TOPICS else topic_of(text)`; returns the canonical explainer for that topic
  - `reuse_reply(ex: Explainer, intent: IntentResult) -> tuple[str, dict] | None`:
    - If exactly one scheme is asked: use the bullet whose url is that scheme's page; if the explainer has none, return `None` (fall back to the desk).
    - If no scheme: use bullet 0 (the concept).
    - Returns `(reply_text, bullet)` where the reply is `covered_reply(bullet.text, bullet.url, ex.last_checked)`.
  - In `process_ticket`, after classify: `ex = find_canonical(...)`; when `reuse_reply` gives a reply, build an `OrchestratorOutput(disposition="reply", routing team "Fees and mutual fund ops", priority "P3", why=f"Reused canonical explainer #{ex.id} ({ex.topic}).")`, review it with `FactsResult(status="covered", scheme_id=intent.scheme_ids[0] if one else "reference", fact=bullet.text, citation=bullet.url, last_checked=ex.last_checked, searched=[f"explainer:{ex.id}"])`, store a `Draft` with `reused_explainer_id=ex.id`, then a pending `reply_publish` action, exactly as the desk path does. Otherwise use the existing desk path.

- [ ] **Step 1: Write the failing test**

`api/tests/test_canonical.py`:
```python
import asyncio

import pytest

from app.models import Draft, Explainer
from app.tickets.service import create_ticket, process_ticket
from tests.conftest_corpus import build_fixture_retriever

MID = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
CONCEPT = "https://groww.in/help/mutual-funds/order/what-is-exit-load--71"


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("cn"))


@pytest.fixture()
def canonical(db_session):
    ex = Explainer(topic="exit_load", title="Exit load", status="canonical", last_checked="2026-11-17", evidence={},
                   bullets=[{"text": "Exit load is a fee payable to a mutual fund house for exiting a fund before a specified period.", "url": CONCEPT},
                            {"text": "Exit load for HDFC Mid Cap Fund Direct Growth: Exit load of 1% if redeemed within 1 year.", "url": MID}])
    db_session.add(ex); db_session.commit()
    return ex


def ask(db, text, retriever):
    t, _ = asyncio.run(create_ticket(db, text))
    return asyncio.run(process_ticket(db, t.id, retriever=retriever))


def test_concept_question_reuses_canonical(db_session, canonical, retriever):
    d = ask(db_session, "What is exit load?", retriever)
    assert d.reused_explainer_id == canonical.id and d.citation == CONCEPT and d.review_status == "pass"


def test_scheme_question_uses_scheme_bullet(db_session, canonical, retriever):
    d = ask(db_session, "exit load of HDFC Mid Cap?", retriever)
    assert d.reused_explainer_id == canonical.id and d.citation == MID


def test_scheme_not_in_explainer_falls_back_to_desk(db_session, canonical, retriever):
    d = ask(db_session, "exit load of HDFC Small Cap?", retriever)
    assert d.reused_explainer_id is None and d.citation.endswith("hdfc-small-cap-fund-direct-growth")


def test_no_canonical_uses_desk(db_session, retriever):
    d = ask(db_session, "What is exit load?", retriever)
    assert d.reused_explainer_id is None and d.disposition == "handoff"


def test_superseded_not_reused(db_session, canonical, retriever):
    canonical.status = "superseded"; db_session.commit()
    assert ask(db_session, "What is exit load?", retriever).reused_explainer_id is None


def test_non_fee_intent_never_reuses(db_session, canonical, retriever):
    assert ask(db_session, "Should I redeem because of exit load?", retriever).reused_explainer_id is None
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

`api/app/link/canonical.py`:
```python
"""Link 2: an approved (canonical) fee explainer answers matching fee questions instead of a fresh draft."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import load_schemes
from app.desk.templates import covered_reply
from app.intent.classifier import IntentResult
from app.models import Explainer
from app.weekly.fee_topics import FEE_TOPICS, topic_of


def find_canonical(db: Session, intent: IntentResult, text: str) -> Explainer | None:
    if intent.intent != "fee_question":
        return None
    topic = intent.fact_key if intent.fact_key in FEE_TOPICS else topic_of(text)
    if topic is None:
        return None
    return (db.query(Explainer).filter_by(topic=topic, status="canonical")
            .order_by(Explainer.canonical_at.desc(), Explainer.id.desc()).first())


def reuse_reply(ex: Explainer, intent: IntentResult) -> tuple[str, dict] | None:
    if not ex.bullets:
        return None
    if len(intent.scheme_ids) == 1:
        url = {s["scheme_id"]: s["url"] for s in load_schemes()["schemes"]}.get(intent.scheme_ids[0])
        bullet = next((b for b in ex.bullets if b["url"] == url), None)
        if bullet is None:
            return None
    elif intent.scheme_ids:
        return None
    else:
        bullet = ex.bullets[0]
    return covered_reply(bullet["text"], bullet["url"], ex.last_checked), bullet
```

In `api/app/tickets/service.py` `process_ticket`, replace the body between `intent = await classify_intent(...)` and the `d = Draft(...)` construction with:
```python
        intent = await classify_intent(t.question_redacted)
        reuse = None
        ex = find_canonical(db, intent, t.question_redacted)
        if ex is not None:
            reuse = reuse_reply(ex, intent)
        if reuse is not None:
            reply, bullet = reuse
            draft_out = OrchestratorOutput(
                reply=reply, citation=bullet["url"], last_checked=ex.last_checked, disposition="reply",
                disagreement=False, routing_note=RoutingNote(team="Fees and mutual fund ops", priority="P3",
                                                             why=f"Reused canonical explainer #{ex.id} ({ex.topic})."))
            facts = FactsResult(status="covered", scheme_id=intent.scheme_ids[0] if len(intent.scheme_ids) == 1 else "reference",
                                fact=bullet["text"], citation=bullet["url"], last_checked=ex.last_checked,
                                searched=[f"explainer:{ex.id}"])
            review = review_draft(draft_out, facts=facts, round=1)
            searched, reused_id = facts.searched, ex.id
        else:
            res = await run_desk(t.question_redacted, list(t.pii_types), intent, retriever=retriever,
                                 themes=themes_provider(db), last_checked=lambda u: last_checked_for(db, u),
                                 today=date.today())
            draft_out, review, searched, reused_id = res.draft, res.review, res.facts.searched, None
        d = Draft(ticket_id=t.id, reply=draft_out.reply, citation=draft_out.citation,
                  last_checked=draft_out.last_checked, disposition=draft_out.disposition,
                  routing_team=draft_out.routing_note.team, routing_priority=draft_out.routing_note.priority,
                  routing_why=draft_out.routing_note.why, review_status=review.status,
                  review_failures=[f.model_dump() for f in review.failures], searched=searched,
                  reused_explainer_id=reused_id)
```
Add the imports: `from app.link.canonical import find_canonical, reuse_reply`, `from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote`, `from app.desk.reviewer import review_draft`.

- [ ] **Step 4: Run** → `pytest tests/test_canonical.py tests/test_tickets_api.py tests/test_orchestrator.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat(link): reuse canonical fee explainers in the response loop (link 2)` (+ Co-Authored-By).

---

### Task 11: Theme provider, scheduler and console endpoints

**Files:**
- Create: `api/app/scheduler.py`
- Modify: `api/app/deps.py` (`get_themes_provider`), `api/app/api/console.py`, `api/app/main.py` (start scheduler when enabled)
- Test: `api/tests/test_weekly_api.py`

**Interfaces:**
- Consumes: Tasks 1–10
- Produces:
  - `deps.latest_theme_stats(db) -> list[ThemeStat]`: from the latest run with status in (`awaiting_approval`, `done`), with `team=TEAMS[id]`, `cues=CUES[id]`, `window=DateWindow(run window)`, `recent_window=DateWindow(window_end-6d, window_end)`
  - `deps.get_themes_provider()` returns `latest_theme_stats`
  - `scheduler.start_scheduler() -> BackgroundScheduler | None`: when `scheduler_enabled`, adds a weekly loop job (Mon 09:00 Asia/Kolkata) and a corpus refresh job (Sun 21:00 Asia/Kolkata), each opening its own `SessionLocal()`
  - Console endpoints (all behind `require_console`):
    - `POST /api/console/weekly/run` → 202 `{"run_id": id, "status": "running"}`. It starts `run_weekly` in a daemon thread with its own session and returns immediately; 409 if a run is already `running`.
    - `GET /api/console/weekly/latest` → `{run, themes[], repeated[], actions[], explainer}` (themes with review_ids, windows and counts) or 404
    - `GET /api/console/explainers` → all explainers newest first, with `reuse_count` (drafts with `reused_explainer_id`)
    - `GET /api/console/actions?status=pending` → actions with type, target_label, content (exact text to be written), source_ref

- [ ] **Step 1: Write the failing test**

`api/tests/test_weekly_api.py`:
```python
import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app import deps
from app.models import Draft, Explainer, Theme, Ticket, WeeklyRun

H = {"X-Console-Key": "test-pass"}
RAW = json.loads((Path(__file__).parent / "fixtures" / "reviews.json").read_text())


@pytest.fixture()
def ran(client, db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir", "data_outbox_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=Path(__file__).parent / "fixtures" / "raw")
    from app.weekly.run import run_weekly
    r = asyncio.run(run_weekly(db_session, now=datetime(2026, 11, 17, 9, tzinfo=timezone.utc),
                               fetcher=lambda p, w, m: [dict(x) for x in RAW]))
    assert r.status == "awaiting_approval", r.error
    return r


def test_latest_shows_traced_themes_and_pending_actions(client, ran):
    body = client.get("/api/console/weekly/latest", headers=H).json()
    assert body["run"]["status"] == "awaiting_approval"
    assert all(t["review_ids"] and t["window_start"] and t["window_end"] for t in body["themes"])
    assert {a["type"] for a in body["actions"]} == {"doc_append", "email_draft"}
    assert all(a["content"] and a["target_label"] for a in body["actions"])


def test_approve_doc_makes_explainer_canonical_and_listed(client, ran):
    acts = client.get("/api/console/actions?status=pending", headers=H).json()
    doc = next(a for a in acts if a["type"] == "doc_append")
    assert client.post(f"/api/console/actions/{doc['id']}/approve", headers=H).status_code == 200
    exps = client.get("/api/console/explainers", headers=H).json()
    assert exps[0]["status"] == "canonical" and "reuse_count" in exps[0]


def test_theme_provider_feeds_pattern_agent(db_session, ran):
    stats = deps.latest_theme_stats(db_session)
    assert stats and all(s.cues and s.team for s in stats)
    assert stats[0].window.end == "2026-11-17"


def test_weekly_run_endpoint_conflict_when_running(client, db_session):
    db_session.add(WeeklyRun(status="running", window_start=date(2026, 9, 22), window_end=date(2026, 11, 17)))
    db_session.commit()
    assert client.post("/api/console/weekly/run", headers=H).status_code == 409


def test_latest_404_when_no_runs(client):
    assert client.get("/api/console/weekly/latest", headers=H).status_code == 404
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

In `api/app/deps.py` replace `get_themes_provider` with:
```python
def latest_theme_stats(db):
    from datetime import timedelta
    from app.desk.contracts import DateWindow, ThemeStat
    from app.models import Theme, WeeklyRun
    from app.weekly.vocab import CUES, TEAMS
    run = (db.query(WeeklyRun).filter(WeeklyRun.status.in_(("awaiting_approval", "done")))
           .order_by(WeeklyRun.id.desc()).first())
    if run is None:
        return []
    w = DateWindow(start=run.window_start.isoformat(), end=run.window_end.isoformat())
    rw = DateWindow(start=(run.window_end - timedelta(days=6)).isoformat(), end=run.window_end.isoformat())
    return [ThemeStat(theme_id=t.theme_id, name=t.label, team=TEAMS.get(t.theme_id, "General support"),
                      cues=CUES.get(t.theme_id, []), count=t.count, recent_count=t.recent_count, window=w,
                      recent_window=rw)
            for t in db.query(Theme).filter_by(run_id=run.id).order_by(Theme.rank)]


def get_themes_provider():
    return latest_theme_stats
```

`api/app/scheduler.py`:
```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.db import SessionLocal

log = logging.getLogger(__name__)


def _weekly_job() -> None:
    from app.weekly.run import run_weekly
    db = SessionLocal()
    try:
        run = asyncio.run(run_weekly(db, now=datetime.now(timezone.utc)))
        log.info("scheduled weekly run %s → %s", run.id, run.status)
    finally:
        db.close()


def _refresh_job() -> None:
    from app.corpus.refresh import refresh_corpus
    db = SessionLocal()
    try:
        refresh_corpus(db)
    finally:
        db.close()


def start_scheduler():
    if not get_settings().scheduler_enabled:
        return None
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    sch = BackgroundScheduler(timezone="Asia/Kolkata")
    sch.add_job(_weekly_job, CronTrigger(day_of_week="mon", hour=9, minute=0), id="weekly_loop", replace_existing=True)
    sch.add_job(_refresh_job, CronTrigger(day_of_week="sun", hour=21, minute=0), id="corpus_refresh", replace_existing=True)
    sch.start()
    log.info("scheduler started: weekly loop Mon 09:00 IST, corpus refresh Sun 21:00 IST")
    return sch
```
In `create_app` (main.py), after routers: `if init_corpus: from app.scheduler import start_scheduler; app.state.scheduler = start_scheduler()`.

Add to `api/app/api/console.py`:
```python
import asyncio
import threading
from datetime import datetime, timezone

from sqlalchemy import func

from app.db import SessionLocal
from app.link.question_keys import repeated_questions
from app.models import Explainer, Theme, WeeklyRun
from app.config import get_settings


def _action_out(a: Action) -> dict:
    return {"id": a.id, "type": a.type, "status": a.status, "target_label": a.target_label,
            "content": a.content, "source_ref": a.source_ref, "error": a.error,
            "created_at": a.created_at, "decided_at": a.decided_at, "executed_at": a.executed_at}


def _explainer_out(db, e: Explainer) -> dict:
    reuse = db.query(func.count(Draft.id)).filter(Draft.reused_explainer_id == e.id).scalar()
    return {"id": e.id, "topic": e.topic, "title": e.title, "bullets": e.bullets, "last_checked": e.last_checked,
            "status": e.status, "evidence": e.evidence, "run_id": e.run_id, "canonical_at": e.canonical_at,
            "reuse_count": reuse}


@router.post("/weekly/run", status_code=202)
def weekly_run(db: Session = Depends(get_db)):
    if db.query(WeeklyRun).filter_by(status="running").first():
        raise HTTPException(409, "a weekly run is already running")

    def go():
        from app.weekly.run import run_weekly
        s = SessionLocal()
        try:
            asyncio.run(run_weekly(s, now=datetime.now(timezone.utc)))
        finally:
            s.close()
    threading.Thread(target=go, daemon=True).start()
    return {"status": "started"}


@router.get("/weekly/latest")
def weekly_latest(db: Session = Depends(get_db)):
    run = db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
    if run is None:
        raise HTTPException(404, "no weekly runs yet")
    s = get_settings()
    themes = db.query(Theme).filter_by(run_id=run.id).order_by(Theme.rank).all()
    acts = db.query(Action).filter_by(source_ref=f"weekly_run:{run.id}").all()
    ex = db.query(Explainer).filter_by(run_id=run.id).first()
    rep = repeated_questions(db, now=datetime.now(timezone.utc), threshold=s.repeat_threshold, days=s.repeat_days)
    return {"run": {"id": run.id, "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at,
                    "window_start": run.window_start, "window_end": run.window_end, "review_count": run.review_count,
                    "pulse_text": run.pulse_text, "error": run.error, "llm_calls": run.llm_calls},
            "themes": [{"theme_id": t.theme_id, "label": t.label, "count": t.count, "recent_count": t.recent_count,
                        "review_ids": t.review_ids, "window_start": t.window_start, "window_end": t.window_end,
                        "rank": t.rank} for t in themes],
            "repeated": [r.__dict__ for r in rep],
            "actions": [_action_out(a) for a in acts],
            "explainer": _explainer_out(db, ex) if ex else None}


@router.get("/explainers")
def explainers(db: Session = Depends(get_db)):
    return [_explainer_out(db, e) for e in db.query(Explainer).order_by(Explainer.id.desc())]


@router.get("/actions")
def actions(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Action).order_by(Action.id.desc())
    if status:
        q = q.filter_by(status=status)
    return [_action_out(a) for a in q.limit(200)]
```
The `weekly_run` test only checks the 409 path; the thread path is exercised in the Task 12 live smoke.

- [ ] **Step 4: Run the full suite** → `pytest -q` → all PASS.

- [ ] **Step 5: Commit** — `feat: theme provider, weekly scheduler and console weekly/explainer/action endpoints` (+ Co-Authored-By).

---

### Task 12: Manual verification report (user requirement)

Spec source: `docs/superpowers/plans/2026-11-17-plan-2-manual-verification.md` (the user will check the data by hand).

**Files:**
- Create: `api/app/weekly/verify.py`, `api/scripts/verify_weekly.py`
- Modify: `.gitignore` (add `api/data/verify/`)
- Test: `api/tests/test_verify_report.py`

**Interfaces:**
- Consumes: `WeeklyRun, Theme, Review, Ticket, Draft, Explainer, Action, AuditLog, Source`, `load_reference`, `find_pii`, `word_count`, `bullet_count`, `check_output`, `repeated_questions`, `label_for`
- Produces:
  - `build_report(db, run_id: int | None = None, *, log_paths: list[Path] = ()) -> Report`, where `Report` is a dataclass `(run_id: int, markdown: str, flags: list[str])`. `flags` collects every mismatch: `"theme <id> count MISMATCH"`, `"quote <review_id> NOT FOUND"`, `"bullet <n> NOT IN SOURCE"`, `"PII <table>.<column> id=<id>: <types>"`, `"PII log <file>:<line>"`.
  - The script `scripts/verify_weekly.py [--run-id N]` writes `api/data/verify/weekly-run-<id>.md` and prints the path and the flag count.
- It is read-only: no DB writes, no LLM, no network.

Report sections, in order: Run summary · Themes (with recount) · Quotes (with full review text) · Repeated questions (keys ≥ threshold and near misses at threshold-2..threshold-1, with ticket codes and redacted questions) · Fee confusion · Explainer (each bullet, its URL, the source's last_checked, and the matching source sentence) · Caps & scope · Pending actions (exact content) · PII sweep · Manual checklist. The checklist is copied verbatim from the requirement file.

How quotes are found: the pulse lines `- "<text>" (<review_id>)` are parsed with `re.findall(r'- "(.+?)" \((rv_[a-z2-7]+)\)', pulse_text)`. A quote is OK when `text.rstrip("…")` is a substring of that review's `text_redacted`.

How bullets are traced: a bullet is OK when its text (minus a trailing "…") is a substring of `load_reference(topic).text` for any reference with that URL, or of the scheme section text in `data_processed_dir/<scheme>.json` whose `source_url` equals the bullet URL.

- [ ] **Step 1: Write the failing test**

`api/tests/test_verify_report.py`:
```python
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models import Review, Theme, Ticket, WeeklyRun
from app.weekly.verify import build_report

FIX = Path(__file__).parent / "fixtures"
RAW = json.loads((FIX / "reviews.json").read_text())


@pytest.fixture()
def run(db_session, tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    for k in ("data_raw_dir", "data_processed_dir", "data_index_dir", "data_outbox_dir"):
        monkeypatch.setattr(s, k, tmp_path / k)
    from app.corpus.refresh import refresh_corpus
    refresh_corpus(db_session, fetch=False, raw_dir=FIX / "raw")
    from app.weekly.run import run_weekly
    r = asyncio.run(run_weekly(db_session, now=datetime(2026, 11, 17, 9, tzinfo=timezone.utc),
                               fetcher=lambda p, w, m: [dict(x) for x in RAW]))
    assert r.status == "awaiting_approval", r.error
    return r


def test_clean_run_has_no_flags_and_all_sections(db_session, run):
    rep = build_report(db_session, run.id)
    assert rep.flags == [], rep.flags
    for h in ("## Run summary", "## Themes", "## Quotes", "## Repeated questions", "## Fee confusion",
              "## Explainer", "## Caps & scope", "## Pending actions", "## PII sweep", "## Manual checklist"):
        assert h in rep.markdown
    assert "count OK" in rep.markdown and "verbatim OK" in rep.markdown and "source OK" in rep.markdown


def test_theme_count_mismatch_flagged(db_session, run):
    t = db_session.query(Theme).filter_by(run_id=run.id).first()
    t.count += 1; db_session.commit()
    assert any("count MISMATCH" in f for f in build_report(db_session, run.id).flags)


def test_tampered_quote_flagged(db_session, run):
    r = db_session.get(WeeklyRun, run.id)
    rid = __import__("re").findall(r'\((rv_[a-z2-7]+)\)', r.pulse_text)[0]
    db_session.get(Review, rid).text_redacted = "completely different text"; db_session.commit()
    assert any(f"quote {rid} NOT FOUND" in f for f in build_report(db_session, run.id).flags)


def test_pii_sweep_finds_db_and_log_hits(db_session, run, tmp_path):
    db_session.add(Ticket(code="GRW-PII001", question_redacted="leaked 9876543210")); db_session.commit()
    log = tmp_path / "server.log"
    log.write_text("ok line\nuser pan ABCDE1234F\n", encoding="utf-8")
    flags = build_report(db_session, run.id, log_paths=[log]).flags
    assert any(f.startswith("PII tickets.question_redacted") for f in flags)
    assert any(f.startswith(f"PII log {log.name}:2") for f in flags)
```

- [ ] **Step 2: Run to verify failure** → FAIL (`ModuleNotFoundError: app.weekly.verify`).

- [ ] **Step 3: Implement**

`api/app/weekly/verify.py`:
```python
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
from app.guard.scope import bullet_count, check_output, word_count
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
    proc = Path(get_settings().data_processed_dir)
    for p in proc.glob("*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("source_url") == url:
            texts += [s.get("text", "") for s in doc.get("sections", [])]
    return texts


def build_report(db: Session, run_id: int | None = None, *, log_paths=()) -> Report:
    s = get_settings()
    run = db.get(WeeklyRun, run_id) if run_id else db.query(WeeklyRun).order_by(WeeklyRun.id.desc()).first()
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
    for key, ts in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(ts) >= s.repeat_threshold - 2:
            tag = "IN PULSE WINDOW CHECK" if len(ts) >= s.repeat_threshold else "near miss"
            L.append(f"- {label_for(key)} ({key}): {len(ts)} tickets [{tag}]")
            L += [f"  - {t.code} {t.created_at:%Y-%m-%d}: {t.question_redacted}" for t in ts]

    ex = db.query(Explainer).filter_by(run_id=run.id).first()
    L += ["", "## Fee confusion"]
    if ex:
        L.append(f"- topic: {ex.topic} · evidence: {json.dumps(ex.evidence)}")
    L += ["", "## Explainer"]
    if ex:
        for i, b in enumerate(ex.bullets, 1):
            src = _source_texts(b["url"])
            ok = any(b["text"].rstrip("…").strip() in t for t in src)
            if not ok:
                flags.append(f"bullet {i} NOT IN SOURCE")
            L.append(f"- {i}. {b['text']} — {b['url']} (last checked {ex.last_checked}) — "
                     f"{'source OK' if ok else 'NOT IN SOURCE'}")
        L.append(f"- distinct official URLs: {len({b['url'] for b in ex.bullets})} · bullets: {len(ex.bullets)}")

    L += ["", "## Caps & scope", f"- pulse words: {word_count(run.pulse_text or '')} (cap 250)"]
    if ex:
        L.append(f"- explainer bullets: {len(ex.bullets)} (cap 6)")
    L.append(f"- pulse scope violations: {[v.check for v in check_output(run.pulse_text or '', kind='pulse')]}")

    L += ["", "## Pending actions"]
    for a in db.query(Action).filter_by(source_ref=f"weekly_run:{run.id}"):
        L += [f"### Action {a.id} · {a.type} · {a.status}", f"Target: {a.target_label}", "```", a.content or "", "```"]

    L += ["", "## PII sweep"]
    for model in _SWEEP:
        cols = [c.key for c in sa_inspect(model).columns if str(c.type).upper().startswith(("TEXT", "VARCHAR", "JSON"))]
        for row in db.query(model):
            for c in cols:
                hits = find_pii(json.dumps(getattr(row, c), default=str) if not isinstance(getattr(row, c), str)
                                else getattr(row, c) or "")
                if hits:
                    flags.append(f"PII {model.__tablename__}.{c} id={row.id}: {','.join(hits)}")
    for p in log_paths:
        for n, line in enumerate(Path(p).read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if find_pii(line):
                flags.append(f"PII log {Path(p).name}:{n}")
    L += [f"- {f}" for f in flags if f.startswith("PII")] or ["- no PII found"]

    L += ["", "## Flags", *([f"- {f}" for f in flags] or ["- none"]), "", "## Manual checklist", CHECKLIST]
    return Report(run_id=run.id, markdown="\n".join(L), flags=flags)
```

`api/scripts/verify_weekly.py`:
```python
"""Write a manual verification page for a weekly run. Read-only. Usage: python scripts/verify_weekly.py [--run-id N]"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import API_ROOT  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.weekly.verify import build_report  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--run-id", type=int, default=None)
p.add_argument("--log", action="append", default=[], help="log file(s) to sweep for PII")
a = p.parse_args()
db = SessionLocal()
rep = build_report(db, a.run_id, log_paths=[Path(x) for x in a.log])
out = API_ROOT / "data" / "verify" / f"weekly-run-{rep.run_id}.md"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(rep.markdown, encoding="utf-8")
print(f"wrote {out} — {len(rep.flags)} flag(s)")
```
Add `api/data/verify/` to `.gitignore` (already covered by `api/data/`; add the line anyway for clarity).

`Review.id` in the PII sweep: review ids are hashes (`rv_` + hex) and will never match PII patterns; if one ever does, the test catches it.

- [ ] **Step 4: Run** → `pytest tests/test_verify_report.py -q` → PASS; then `pytest -q` → all PASS.

- [ ] **Step 5: Commit** — `feat(weekly): read-only manual verification report for weekly runs` (+ Co-Authored-By).

---

### Task 13: Live weekly smoke (real Play Store, real corpus, real Groq) + manual checkpoint

**Files:** none new (records results in the ledger)

- [ ] **Step 1: Refresh the live corpus including references**

```bash
cd api && .venv/Scripts/python -c "
from app.db import SessionLocal, init_db; init_db()
from app.corpus.refresh import refresh_corpus
db=SessionLocal(); print(refresh_corpus(db))"
```
Expected: the log line shows schemes ok=15 and references ok=4.

- [ ] **Step 2: Run the weekly loop live**

```bash
.venv/Scripts/python -c "
import asyncio, time
from datetime import datetime, timezone
from app.db import SessionLocal
from app.weekly.run import run_weekly
from app.models import Theme, Action
db=SessionLocal(); t=time.time()
r=asyncio.run(run_weekly(db, now=datetime.now(timezone.utc)))
print(r.status, r.error, 'reviews', r.review_count, 'llm_calls', r.llm_calls, 'secs', round(time.time()-t))
for th in db.query(Theme).filter_by(run_id=r.id).order_by(Theme.rank): print(th.rank, th.label, th.count, th.recent_count, th.review_ids[:3])
print(r.pulse_text)
print([ (a.type, a.status, a.target_label) for a in db.query(Action).filter_by(source_ref=f'weekly_run:{r.id}')])
"
```
Expected: status `awaiting_approval`, ≤5 themes with ids, a pulse ≤250 words, `llm_calls ≤ 5`, two pending actions, finished in a few minutes.

- [ ] **Step 3: Exercise link 2 live**

Start the server (`uvicorn --factory app.main:create_app --port 8000`), approve the run's `doc_append` via `POST /api/console/actions/{id}/approve`, then `POST /api/ask {"text":"What is <topic>?"}` for the explainer's topic. Expected: the queue item's draft has `reused_explainer_id` set and cites the explainer's first bullet URL. Confirm the outbox file exists, the `email_draft` action is still `pending`, and `grep -cE "ABCDE1234F|9876543210"` on the server log is 0.

- [ ] **Step 4: Generate the verification page**

```bash
.venv/Scripts/python scripts/verify_weekly.py --log ../.superpowers/server.log
```
Expected: `0 flag(s)`. Any flag gets a failing test plus a fix before continuing.

- [ ] **Step 5: CHECKPOINT — stop for the user's manual check.** Give the user the path to `api/data/verify/weekly-run-<id>.md` and the checklist at its end. Do not open the Plan 2 PR until they confirm. Anything they find becomes a failing test, then a fix, then a regenerated page.

- [ ] **Step 6: Record results** in the ledger (counts, timings, flags, user sign-off).

---

## Self-Review Notes

- **Spec coverage:**
  - §6 weekly loop steps 1–6 → Tasks 3, 4, 5, 6, 7, 8
  - Link 1 → Task 5 (keys), Task 7 (pulse section), Task 8 (wired)
  - Link 2 → Task 9 (canonicalize on executed doc_append), Task 10 (reuse)
  - §4 fee pages → Task 2
  - §7 approvals for doc/email (gate, independence, failure without silent retry) → Tasks 8, 9. MCP execution is Plan 3; the outbox is the interim executor.
  - §9 feasibility hooks (traced themes, windows, caps, run without manual steps) → Tasks 4, 7, 8, 11
  - Scheduler → Task 11
  - The Pattern agent's themes → Task 11 provider
- **Deliberate decisions:**
  - Themes use M2's fixed 5-theme vocabulary, so ≤5 is guaranteed by construction.
  - Quotes and explainer bullets are extractive (verbatim) for grounding; the LLM only labels ambiguous reviews and writes action ideas.
  - The recipient email is never stored.
  - A scheme the canonical explainer does not cover falls back to the desk.
- **Type consistency:** `ThemeOut`, `RepeatedQuestion`, `FeeConfusion`, `ExplainerDraft`, `Quote`, `run_weekly(db, now=, fetcher=)`, `EXECUTORS[type](db, action) -> str` and `mark_canonical(db, explainer_id)` are used identically across tasks.
