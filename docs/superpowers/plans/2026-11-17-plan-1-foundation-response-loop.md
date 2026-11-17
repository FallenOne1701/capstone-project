# Plan 1 — Foundation + Response Loop (API) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI backend where a question (text) becomes a redacted ticket, runs through intent detection and the three-agent desk over the M1 corpus, and lands as a reviewed, cited reply draft that a human can approve, edit or reject via API.

**Architecture:** One Python package `app` under `support-desk/api/`. `guard/` redacts PII and filters output; `corpus/` is the M1 ingestion + retrieval port with fastembed replacing sentence-transformers; `desk/` is the M3 agent port rewired onto `corpus/`; `approvals/` owns pending actions and the audit log; `tickets/` glues it together. SQLAlchemy over SQLite locally/tests and Postgres in production.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2, pydantic-settings, LangGraph, chromadb, fastembed (`BAAI/bge-small-en-v1.5`), groq SDK, google-genai (optional fallback), httpx, BeautifulSoup/lxml/trafilatura, pytest.

**Spec:** `docs/superpowers/specs/2026-11-17-support-desk-design.md` (this plan covers spec §3 api skeleton, §4, §5 intent taxonomy, §6 response loop, §7 approvals core for `reply_publish`, §8, §11 unit tests, §12 LLM/corpus error handling). Plans 2–4 cover the weekly loop + links, console/voice/MCP, and evals/deploy.

## Global Constraints

- Python **3.14** locally and in Docker (`python:3.14-slim`); wheels for chromadb, fastembed, onnxruntime verified on cp314.
- LLM: Groq `openai/gpt-oss-120b` (drafting), `openai/gpt-oss-20b` (classification); free tier 1000 req/day + 8000 tokens/min **per model**. Gemini (`GEMINI_MODEL`, key `GOOGLE_API_KEY`) is an optional fallback with an **8 s timeout**.
- `USE_LLM=0` disables every LLM call; all tests run with `USE_LLM=0` and must pass offline.
- Embeddings: `BAAI/bge-small-en-v1.5` via fastembed (no PyTorch). Query prefix `"Represent this sentence for searching relevant passages: "`.
- Raw user text is **never** persisted, logged, or passed to an agent; only `guard.pii.redact(...)` output is.
- Reply ≤ **3 sentences**; every covered reply has exactly **one** corpus URL and its last-checked date.
- Question max length **500** characters.
- Corpus = the 15 HDFC scheme URLs from M1 `schemes.yaml` (+ reference pages added in Plan 2). Allowed citation hosts: `groww.in`, `amfiindia.com`, `sebi.gov.in`.
- Nothing is published to a ticket without an approved `reply_publish` action.
- Source code ported from: M1 `C:/Users/dhruv/OneDrive/Desktop/RAG Chat bot- Mutual Funds`, M3 `C:/Users/dhruv/multi agentic system/multi-agentic-system`, M2 `C:/Users/dhruv/Groww-and-MCP`.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Voice-style PII** — transcripts like `my pan is abcde 1234 f`, `+91 98765 43210`, `account 5010 0234 5678 90` must be redacted exactly like compact forms. → tests in Task 2.
2. **False positives that would wreck answers** — "How do I redeem my units?" is `how_to_process`, not advice; benchmark "NIFTY Midcap 150 Total Return Index" and fee "Exit load of 1%" must pass the output filter. → tests in Tasks 4 and 9.
3. **Junk input** — empty, whitespace, >500 chars, emoji-only, pure Devanagari question: API returns 422 for empty/too-long and a not-covered draft (never a 500) otherwise. → tests in Task 13.
4. **Corpus page fetch failure during refresh** — previous snapshot kept, source marked `stale` with its old `fetched_at`, retrieval still answers. → test in Task 7.
5. **LLM unavailable** (no key, 429, Gemini timeout) — desk still produces a deterministic draft; ticket never stuck in `received`. → tests in Tasks 5 and 12.

---

## File Structure

```
support-desk/
  .gitignore
  api/
    pyproject.toml
    .env.example
    app/
      __init__.py
      config.py              Settings + load_schemes + allowed-domain helpers
      db.py                  engine, SessionLocal, Base, init_db, get_db
      models.py              Source, Ticket, Draft, Action, AuditLog
      main.py                create_app(), /health, router wiring, log redaction install
      guard/
        __init__.py
        pii.py               redact(), find_pii()
        logfilter.py         RedactingFilter, install_log_redaction()
        scope.py             output checks + caps
      llm/
        __init__.py
        ratelimit.py         GroqRateLimiter (M2 port)
        client.py            complete_json() Groq→Gemini, llm_enabled()
      corpus/
        __init__.py
        sources.yaml         M1 schemes.yaml + kind field
        fetcher.py parser.py chunker.py indexer.py query_parser.py retriever.py   (M1 ports)
        embedder.py          fastembed EmbeddingService
        refresh.py           refresh_corpus() + Source rows
      intent/
        __init__.py
        classifier.py        classify_intent()
      desk/
        __init__.py
        contracts.py         M3 contracts, SchemeId/ThemeId widened to str
        facts.py             run_facts() over Retriever
        pattern.py           run_pattern() over ThemeStat list
        compliance.py        run_compliance() over guard
        reviewer.py          review_draft(), rewrite_draft() over guard.scope
        orchestrator.py      run_desk() LangGraph parallel + merge + review
        templates.py         refusal / account / not-covered replies
      approvals/
        __init__.py
        service.py           approve(), reject(), edit_draft(), audit()
      tickets/
        __init__.py
        service.py           create_ticket(), process_ticket(), preview()
      api/
        __init__.py
        public.py            /api/ask, /api/ask/preview, /api/tickets/{code}
        console.py           /api/console/* (X-Console-Key)
    tests/
      conftest.py
      fixtures/raw/          copied M1 data/raw HTML snapshots
      test_*.py
```

---

### Task 1: Scaffold the API package, settings, database and health check

**Files:**
- Create: `support-desk/.gitignore`, `api/pyproject.toml`, `api/.env.example`, `api/app/__init__.py`, `api/app/config.py`, `api/app/db.py`, `api/app/models.py`, `api/app/main.py`, `api/tests/conftest.py`
- Test: `api/tests/test_health.py`

**Interfaces:**
- Produces: `app.config.Settings`, `get_settings()`, `load_schemes(path=None) -> dict`, `is_allowed_source_url(url) -> bool`, `ALLOWED_SOURCE_DOMAINS`; `app.db.Base`, `engine`, `SessionLocal`, `init_db()`, `get_db()`; ORM classes `Source, Ticket, Draft, Action, AuditLog`; `app.main.create_app() -> FastAPI`.

- [ ] **Step 1: Create repo files**

`support-desk/.gitignore`:
```
__pycache__/
*.pyc
.venv/
.env
api/data/
*.db
node_modules/
.next/
token.json
```

`api/pyproject.toml`:
```toml
[project]
name = "support-desk-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115", "uvicorn[standard]>=0.32", "pydantic>=2.9", "pydantic-settings>=2.6",
  "sqlalchemy>=2.0", "psycopg[binary]>=3.2", "pyyaml>=6.0", "httpx>=0.27",
  "beautifulsoup4>=4.12", "lxml>=5.3", "trafilatura>=1.12",
  "chromadb>=1.0", "fastembed>=0.5", "groq>=0.11", "google-genai>=1.0",
  "langgraph>=0.2", "python-dotenv>=1.0",
]
[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.23"]
[tool.setuptools.packages.find]
include = ["app*"]
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`api/.env.example`:
```
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GROQ_MODEL_FAST=openai/gpt-oss-20b
GOOGLE_API_KEY=
GEMINI_MODEL=gemini-3.6-flash
USE_LLM=1
DATABASE_URL=sqlite:///./data/app.db
CONSOLE_PASSWORD=change-me
```

- [ ] **Step 2: Write the failing test**

`api/tests/conftest.py`:
```python
import os
os.environ["USE_LLM"] = "0"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CONSOLE_PASSWORD"] = "test-pass"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app import db as dbmod


@pytest.fixture()
def db_session(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    dbmod.init_db()
    s = dbmod.SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def client(db_session):
    from app.main import create_app
    app = create_app(init_corpus=False)
    app.dependency_overrides[dbmod.get_db] = lambda: db_session
    return TestClient(app)
```

`api/tests/test_health.py`:
```python
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert "corpus" in body
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `support-desk/api`): `py -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]" && .venv/Scripts/python -m pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'` (or missing `create_app`).

- [ ] **Step 4: Implement config, db, models, main**

`api/app/__init__.py`: empty.

`api/app/config.py`:
```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = API_ROOT / "app" / "corpus" / "sources.yaml"
ALLOWED_SOURCE_DOMAINS: frozenset[str] = frozenset({"groww.in", "amfiindia.com", "sebi.gov.in"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(API_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_model_fast: str = "openai/gpt-oss-20b"
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_s: float = 8.0
    use_llm: bool = True
    groq_rpm: int = 30
    groq_tpm: int = 8000

    # Storage
    database_url: str = f"sqlite:///{(API_ROOT / 'data' / 'app.db').as_posix()}"
    console_password: str = "change-me"

    # Corpus (field names kept identical to M1 so ported modules work unchanged)
    data_raw_dir: Path = API_ROOT / "data" / "corpus" / "raw"
    data_processed_dir: Path = API_ROOT / "data" / "corpus" / "processed"
    data_index_dir: Path = API_ROOT / "data" / "corpus" / "index"
    schemes_path: Path = SOURCES_PATH
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 32
    chroma_collection_name: str = "mf_faq_chunks"
    retrieval_top_k: int = 3
    retrieval_top_k_unfiltered: int = 5
    retrieval_rerank_top_n: int = 3
    retrieval_min_similarity: float = 0.58
    chunk_max_section_tokens: int = 400
    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 0
    fetch_timeout_seconds: float = 30.0
    fetch_delay_seconds: float = 1.0
    fetch_min_html_bytes: int = 2_000

    max_message_chars: int = 500

    @property
    def allowed_source_domains(self) -> frozenset[str]:
        return ALLOWED_SOURCE_DOMAINS


def load_schemes(path: Path | None = None) -> dict[str, Any]:
    f = path or SOURCES_PATH
    with f.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not data or not data.get("schemes"):
        raise ValueError(f"Invalid sources registry: {f}")
    return data


def is_allowed_source_url(url: str, domains: frozenset[str] | None = None) -> bool:
    allowed = domains or ALLOWED_SOURCE_DOMAINS
    host = (urlparse(url).hostname or "").lower()
    return bool(host) and any(host == d or host.endswith("." + d) for d in allowed)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`api/app/db.py`:
```python
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)
    Base.metadata.create_all(engine)


def get_db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
```

`api/app/models.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
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
```

`api/app/main.py`:
```python
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db, init_db


def create_app(*, init_corpus: bool = True) -> FastAPI:
    app = FastAPI(title="Groww Support Desk API")
    init_db()

    @app.get("/health")
    def health(db: Session = Depends(get_db)):
        db.execute(text("select 1"))
        from app.corpus.status import corpus_status  # added in Task 7
        return {"db": "ok", "corpus": corpus_status()}

    return app
```

There is deliberately **no** module-level `app = create_app()`: importing `app.main` must not start a corpus fetch. Run with `uvicorn --factory app.main:create_app`.

Note: `/health` imports `app.corpus.status`; until Task 7 create a stub `api/app/corpus/__init__.py` (empty) and `api/app/corpus/status.py`:
```python
def corpus_status() -> dict:
    return {"vectors": 0, "ready": False}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(api): scaffold FastAPI app, settings, ORM models, health check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: PII redactor (`guard/pii.py`)

**Files:**
- Create: `api/app/guard/__init__.py` (empty), `api/app/guard/pii.py`
- Test: `api/tests/test_pii.py`

**Interfaces:**
- Produces: `redact(text: str) -> Redaction` where `Redaction` is a frozen dataclass `(text: str, pii_types: list[str])`; `find_pii(text: str) -> list[str]`. PII type names: `PAN, AADHAAR, ACCOUNT, IFSC, PHONE, EMAIL, UPI, OTP, CARD`. Tokens: `[PAN]` etc.

Design: patterns tolerate single spaces/hyphens between characters (Whisper often spaces out spelled characters). Order matters: EMAIL before UPI; OTP and context-ACCOUNT before PHONE; PHONE before AADHAAR; AADHAAR before the bare-digit-run ACCOUNT fallback. The bare fallback redacts **any** 9–18 digit run (spaces/hyphens allowed, no commas) because fee/fund facts never contain one. Aadhaar is redacted for any 12-digit 4-4-4 group (no Verhoeff check — stricter than the spec, so fake test numbers are also caught).

- [ ] **Step 1: Write the failing test**

`api/tests/test_pii.py`:
```python
import pytest

from app.guard.pii import find_pii, redact


@pytest.mark.parametrize("raw,ptype,token", [
    ("my pan is ABCDE1234F", "PAN", "[PAN]"),
    ("my pan is abcde1234f", "PAN", "[PAN]"),
    ("pan A B C D E 1 2 3 4 F please", "PAN", "[PAN]"),
    ("my pan is abcde 1234 f", "PAN", "[PAN]"),
    ("call me on 9876543210", "PHONE", "[PHONE]"),
    ("call +91 98765 43210 today", "PHONE", "[PHONE]"),
    ("phone 98765-43210", "PHONE", "[PHONE]"),
    ("aadhaar 1234 5678 9012", "AADHAAR", "[AADHAAR]"),
    ("account no 50100234567890", "ACCOUNT", "[ACCOUNT]"),
    ("account 5010 0234 5678 90", "ACCOUNT", "[ACCOUNT]"),
    ("a/c: 123456789", "ACCOUNT", "[ACCOUNT]"),
    ("my number is 501002345678901", "ACCOUNT", "[ACCOUNT]"),
    ("ifsc HDFC0001234", "IFSC", "[IFSC]"),
    ("mail me at ravi.k@example.com", "EMAIL", "[EMAIL]"),
    ("upi ravi@okhdfcbank", "UPI", "[UPI]"),
    ("OTP is 482913", "OTP", "[OTP]"),
    ("card 4111 1111 1111 1111", "CARD", "[CARD]"),
])
def test_redacts_each_type(raw, ptype, token):
    r = redact(raw)
    assert ptype in r.pii_types
    assert token in r.text
    for ch in ("1234", "98765", "ravi", "482913", "5010"):
        if ch in raw:
            assert ch not in r.text


@pytest.mark.parametrize("clean", [
    "What is the exit load of HDFC Mid Cap Fund?",
    "Exit load of 1% if redeemed within 1 year.",
    "The minimum SIP amount is ₹100.",
    "The expense ratio is 0.74%.",
    "AUM is ₹83,105 Cr as of 31 Oct 2026.",
    "Benchmark: NIFTY Midcap 150 Total Return Index",
    "Lock-in of 3 years for ELSS.",
    "Minimum SIP is 1000 a month.",
    "Last checked: 2026-11-17.",
    "Ticket GRW-AB12CD is in review.",
])
def test_leaves_clean_text_untouched(clean):
    r = redact(clean)
    assert r.text == clean
    assert r.pii_types == []


def test_multiple_types_and_order_stable():
    r = redact("PAN ABCDE1234F, phone 9876543210, acct 123456789012345")
    assert set(r.pii_types) == {"PAN", "PHONE", "ACCOUNT"}
    assert "ABCDE" not in r.text and "98765" not in r.text and "123456789012345" not in r.text


def test_find_pii_matches_redact():
    assert find_pii("ABCDE1234F") == ["PAN"]
    assert find_pii("nothing here") == []


def test_redact_is_idempotent():
    once = redact("pan ABCDE1234F phone 9876543210").text
    assert redact(once).text == once
    assert redact(once).pii_types == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pii.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.guard'`.

- [ ] **Step 3: Implement**

`api/app/guard/pii.py`:
```python
"""Deterministic PII redaction. Runs on every input before storage, logging or agents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_S = r"[\s\-]?"  # optional single space/hyphen between characters (voice transcripts)


def _spaced(chars: str) -> str:
    return _S.join(chars)


@dataclass(frozen=True)
class Redaction:
    text: str
    pii_types: list[str] = field(default_factory=list)


_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    ("UPI", re.compile(r"\b[A-Za-z0-9._-]{2,}@[A-Za-z]{2,}\b"), "[UPI]"),
    # compact, grouped ("abcde 1234 f") or fully spaced ("A B C D E 1 2 3 4 F") — never partial spacing,
    # which would match ordinary text such as "SIP is 1000 a month".
    ("PAN", re.compile(r"(?i)\b(?:[a-z]{5}\d{4}[a-z]|[a-z]{5}[\s-]\d{4}[\s-][a-z]|(?:[a-z][\s-]){5}(?:\d[\s-]){4}[a-z])\b"), "[PAN]"),
    ("IFSC", re.compile(r"(?i)\b[a-z]{4}0[a-z0-9]{6}\b"), "[IFSC]"),
    ("OTP", re.compile(r"(?i)\b(?:otp|one[\s-]?time[\s-]?password)\s*(?:is|:|-)?\s*(?:\d" + _S + r"){3,7}\d\b"), "[OTP]"),
    ("CARD", re.compile(r"\b(?:\d" + _S + r"){15}\d\b"), "[CARD]"),
    ("ACCOUNT", re.compile(
        r"(?i)\b(?:account|acct|acc|a/c)\s*(?:no\.?|number|num|#)?\s*(?:is|:|-)?\s*(?:\d" + _S + r"){8,17}\d\b"
    ), "[ACCOUNT]"),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91" + _S + r")?[6-9](?:" + _S + r"\d){9}(?!\d)"), "[PHONE]"),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"), "[AADHAAR]"),
    ("ACCOUNT", re.compile(r"(?<![\d,.])(?:\d[\s-]?){8,17}\d(?![\d,.])"), "[ACCOUNT]"),
]


def redact(text: str) -> Redaction:
    out = text or ""
    found: list[str] = []
    for ptype, pattern, token in _RULES:
        out, n = pattern.subn(token, out)
        if n and ptype not in found:
            found.append(ptype)
    return Redaction(text=out, pii_types=found)


def find_pii(text: str) -> list[str]:
    return redact(text).pii_types
```

- [ ] **Step 4: Run tests; fix pattern order until all pass**

Run: `.venv/Scripts/python -m pytest tests/test_pii.py -v`
Expected: PASS. If a clean-text case fails (e.g. a date like `31 Oct 2026` matched), tighten the offending pattern with lookarounds rather than deleting the test.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(guard): PII redactor tolerant of voice-transcript spacing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Log redaction filter (`guard/logfilter.py`)

**Files:**
- Create: `api/app/guard/logfilter.py`
- Modify: `api/app/main.py` (call `install_log_redaction()` at the top of `create_app`)
- Test: `api/tests/test_logfilter.py`

**Interfaces:**
- Consumes: `app.guard.pii.redact`
- Produces: `RedactingFilter(logging.Filter)`, `install_log_redaction() -> None` (idempotent; attaches to root logger handlers and `uvicorn`, `uvicorn.access`, `uvicorn.error` loggers).

- [ ] **Step 1: Write the failing test**

`api/tests/test_logfilter.py`:
```python
import logging

from app.guard.logfilter import RedactingFilter, install_log_redaction


def test_filter_redacts_message_and_args(caplog):
    logger = logging.getLogger("t.redact")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="t.redact"):
        logger.info("user said %s", "my pan is ABCDE1234F and phone 9876543210")
    text = caplog.text
    assert "ABCDE1234F" not in text and "9876543210" not in text
    assert "[PAN]" in text and "[PHONE]" in text


def test_install_is_idempotent():
    install_log_redaction()
    install_log_redaction()
    root = logging.getLogger()
    n = sum(isinstance(f, RedactingFilter) for h in root.handlers for f in h.filters)
    assert n <= len(root.handlers)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_logfilter.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

`api/app/guard/logfilter.py`:
```python
from __future__ import annotations

import logging

from app.guard.pii import redact


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = redact(msg).text
        record.args = ()
        return True


def install_log_redaction() -> None:
    logging.basicConfig(level=logging.INFO)
    targets = [logging.getLogger()] + [logging.getLogger(n) for n in ("uvicorn", "uvicorn.access", "uvicorn.error")]
    for lg in targets:
        if not any(isinstance(f, RedactingFilter) for f in lg.filters):
            lg.addFilter(RedactingFilter())
        for h in lg.handlers:
            if not any(isinstance(f, RedactingFilter) for f in h.filters):
                h.addFilter(RedactingFilter())
```

In `app/main.py`, first line inside `create_app`: `from app.guard.logfilter import install_log_redaction; install_log_redaction()`.

- [ ] **Step 4: Run tests** → `pytest tests/test_logfilter.py tests/test_health.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(guard): redact PII in every log record" ` (with the Co-Authored-By line).

---

### Task 4: Output scope filter and caps (`guard/scope.py`)

**Files:**
- Create: `api/app/guard/scope.py`
- Test: `api/tests/test_scope.py`

**Interfaces:**
- Produces:
  - `Violation` dataclass `(check: str, detail: str)`; `check ∈ {"advice","performance","pii","shape"}`
  - `detect_advice(text) -> bool`, `detect_performance(text) -> bool`
  - `sentence_count(text) -> int`, `word_count(text) -> int`, `bullet_count(text) -> int`
  - `check_output(text: str, *, kind: Literal["reply","pulse","explainer"]) -> list[Violation]` — caps: reply ≤3 sentences, pulse ≤250 words, explainer ≤6 bullets
  - `strip_advice_and_performance(text) -> str`, `truncate_sentences(text, limit=3) -> str`

Rules (outputs only — the input side is intent classification, Task 9):
- **Advice:** recommendation phrases (`you should`, `we recommend`, `i recommend`, `consider (buying|selling|switching|investing|staying)`, `good time to`, `better to (buy|sell|invest|switch)`, `worth investing`, `stay invested`) or whole-word `buy|sell|hold|switch` used as verbs. `redeem/redeemed/redemption` are **allowed** (exit-load facts use them).
- **Performance:** `cagr|xirr|annuali[sz]ed|performance|outperform|underperform`, or `returns?` **unless** inside `total return index` / `TRI`, or a percentage within 6 words of `return|returned|gain|grew|growth|gave|delivered|yield`.
- Fee percentages (`exit load`, `expense ratio`, `stamp duty`) are never flagged.

- [ ] **Step 1: Write the failing test**

`api/tests/test_scope.py`:
```python
import pytest

from app.guard.scope import (
    bullet_count, check_output, detect_advice, detect_performance,
    sentence_count, strip_advice_and_performance, truncate_sentences, word_count,
)


@pytest.mark.parametrize("text", [
    "You should buy this fund now.",
    "We recommend switching to the large cap fund.",
    "Consider staying invested for the long term.",
    "It is a good time to sell.",
    "Hold your units.",
])
def test_advice_detected(text):
    assert detect_advice(text)


@pytest.mark.parametrize("text", [
    "Exit load of 1% if redeemed within 1 year.",
    "Redemption proceeds are credited to your bank account.",
    "The minimum SIP amount is ₹100.",
    "Fund holdings are listed on the scheme page.",
])
def test_advice_not_flagged_for_facts(text):
    assert not detect_advice(text)


@pytest.mark.parametrize("text", [
    "The fund gave 24% returns last year.",
    "3-year CAGR is 21.4%.",
    "It returned 18% in 2025.",
    "Performance has been strong.",
    "Expected returns are high.",
])
def test_performance_detected(text):
    assert detect_performance(text)


@pytest.mark.parametrize("text", [
    "The fund benchmark is NIFTY Midcap 150 Total Return Index.",
    "Benchmark: NIFTY 100 TRI.",
    "The expense ratio is 0.74%.",
    "Exit load of 1% if redeemed within 1 year.",
    "Stamp duty of 0.005% applies on purchases.",
])
def test_performance_not_flagged_for_fee_facts(text):
    assert not detect_performance(text)


def test_counts():
    assert sentence_count("One. Two! Three? Four.") == 4
    assert sentence_count("Source: https://groww.in/mutual-funds/x. Last checked: 2026-11-17.") == 2
    assert word_count("a b  c\nd") == 4
    assert bullet_count("- a\n- b\n* c\n1. d\ntext") == 4


def test_check_output_caps():
    assert [v.check for v in check_output("A. B. C. D.", kind="reply")] == ["shape"]
    assert check_output("A. B. C.", kind="reply") == []
    assert [v.check for v in check_output(" ".join(["w"] * 251), kind="pulse")] == ["shape"]
    assert [v.check for v in check_output("\n".join(["- x"] * 7), kind="explainer")] == ["shape"]


def test_check_output_flags_pii_and_advice():
    checks = {v.check for v in check_output("You should buy. Call 9876543210.", kind="reply")}
    assert {"advice", "pii"} <= checks


def test_strip_and_truncate():
    cleaned = strip_advice_and_performance("Exit load is 1%. You should buy now. It gave 20% returns.")
    assert not detect_advice(cleaned) and not detect_performance(cleaned)
    assert "Exit load is 1%." in cleaned
    assert truncate_sentences("A. B. C. D.", 3) == "A. B. C."
```

- [ ] **Step 2: Run to verify failure** → `pytest tests/test_scope.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

`api/app/guard/scope.py`:
```python
"""Output scope filter: facts-only, no advice, no performance figures, hard caps."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.guard.pii import find_pii

Kind = Literal["reply", "pulse", "explainer"]
CAPS = {"reply": ("sentences", 3), "pulse": ("words", 250), "explainer": ("bullets", 6)}


@dataclass(frozen=True)
class Violation:
    check: str
    detail: str


_ADVICE_PHRASES = re.compile(
    r"(?i)\b(you should|we recommend|i recommend|we suggest|i suggest|"
    r"consider (?:buying|selling|switching|investing|staying)|good time to|"
    r"better to (?:buy|sell|invest|switch)|worth investing|stay invested|must invest)\b"
)
_ADVICE_VERBS = re.compile(r"(?i)\b(buy|sell|hold|switch)\b")
_PERF_WORDS = re.compile(r"(?i)\b(cagr|xirr|annuali[sz]ed|performance|outperform\w*|underperform\w*)\b")
_RETURN_WORD = re.compile(r"(?i)\breturns?\b")
_TRI = re.compile(r"(?i)\btotal return index\b|\bTRI\b")
_PCT_NEAR_GAIN = re.compile(
    r"(?i)(\d+(?:\.\d+)?\s?%(?:\W+\w+){0,6}?\W+(?:return\w*|gain\w*|grew|growth|gave|delivered|yield\w*))|"
    r"((?:return\w*|gain\w*|grew|growth|gave|delivered|yield\w*)(?:\W+\w+){0,6}?\W+\d+(?:\.\d+)?\s?%)"
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[(\"'₹])")
_BULLET = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")


def detect_advice(text: str) -> bool:
    return bool(_ADVICE_PHRASES.search(text) or _ADVICE_VERBS.search(text))


def detect_performance(text: str) -> bool:
    if _PERF_WORDS.search(text):
        return True
    without_tri = _TRI.sub(" ", text)
    if _RETURN_WORD.search(without_tri):
        return True
    return bool(_PCT_NEAR_GAIN.search(without_tri))


def sentence_count(text: str) -> int:
    t = text.strip()
    return len([p for p in _SENT_SPLIT.split(t) if p.strip()]) if t else 0


def word_count(text: str) -> int:
    return len(text.split())


def bullet_count(text: str) -> int:
    return len(_BULLET.findall(text))


def check_output(text: str, *, kind: Kind) -> list[Violation]:
    out: list[Violation] = []
    if detect_advice(text):
        out.append(Violation("advice", "advice or buy/sell language"))
    if detect_performance(text):
        out.append(Violation("performance", "return or performance figure"))
    pii = find_pii(text)
    if pii:
        out.append(Violation("pii", f"residual PII: {', '.join(pii)}"))
    unit, cap = CAPS[kind]
    n = {"sentences": sentence_count, "words": word_count, "bullets": bullet_count}[unit](text)
    if n > cap:
        out.append(Violation("shape", f"{kind} has {n} {unit} (cap {cap})"))
    return out


def truncate_sentences(text: str, limit: int = 3) -> str:
    parts = [p.strip() for p in _SENT_SPLIT.split(text.strip()) if p.strip()]
    return " ".join(parts[:limit])


def strip_advice_and_performance(text: str) -> str:
    parts = [p.strip() for p in _SENT_SPLIT.split(text.strip()) if p.strip()]
    kept = [p for p in parts if not detect_advice(p) and not detect_performance(p)]
    return " ".join(kept)
```

- [ ] **Step 4: Run tests** → `pytest tests/test_scope.py -v` → PASS. If the `_SENT_SPLIT` rule splits inside a URL (it should not: URLs contain no `". "` followed by capital), add a failing case first, then fix.

- [ ] **Step 5: Commit** — `git commit -am "feat(guard): output scope filter and length caps"` (+ Co-Authored-By).

---

### Task 5: LLM client with rate limiting and fallback (`llm/`)

**Files:**
- Create: `api/app/llm/__init__.py` (empty), `api/app/llm/ratelimit.py`, `api/app/llm/client.py`
- Test: `api/tests/test_llm_client.py`

**Interfaces:**
- Consumes: `get_settings()`
- Produces: `llm_enabled() -> bool`; `async complete_json(system: str, user: str, *, fast: bool = False) -> dict | None` — Groq first (model `groq_model_fast` if `fast` else `groq_model`), then Gemini with `gemini_timeout_s` timeout, else `None`. Never raises. `GroqRateLimiter` per model.

- [ ] **Step 1: Copy the M2 rate limiter**

```bash
cp "C:/Users/dhruv/Groww-and-MCP/src/agent/rate_limit.py" api/app/llm/ratelimit.py
```
Then delete the last function `invoke_with_rate_limit` and the module-level `_LIMITER`/`get_rate_limiter` (the client creates one limiter per model).

- [ ] **Step 2: Write the failing test**

`api/tests/test_llm_client.py`:
```python
import asyncio

import pytest

from app.llm import client as c


def test_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: False)
    assert asyncio.run(c.complete_json("s", "u")) is None


def test_groq_success_parses_json(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)

    async def fake_groq(model, system, user):
        return '{"ok": true}'
    monkeypatch.setattr(c, "_groq_call", fake_groq)
    assert asyncio.run(c.complete_json("s", "u")) == {"ok": True}


def test_groq_failure_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)

    async def boom(model, system, user):
        raise RuntimeError("429 rate limited")

    async def fake_gemini(system, user):
        return '{"via": "gemini"}'
    monkeypatch.setattr(c, "_groq_call", boom)
    monkeypatch.setattr(c, "_gemini_call", fake_gemini)
    assert asyncio.run(c.complete_json("s", "u")) == {"via": "gemini"}


def test_gemini_timeout_returns_none(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)
    monkeypatch.setattr(c, "_gemini_timeout", lambda: 0.05)

    async def boom(model, system, user):
        raise RuntimeError("down")

    async def slow(system, user):
        await asyncio.sleep(1)
        return "{}"
    monkeypatch.setattr(c, "_groq_call", boom)
    monkeypatch.setattr(c, "_gemini_call", slow)
    assert asyncio.run(c.complete_json("s", "u")) is None


def test_non_json_returns_none(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)

    async def junk(model, system, user):
        return "not json"

    async def none_gemini(system, user):
        return "still not json"
    monkeypatch.setattr(c, "_groq_call", junk)
    monkeypatch.setattr(c, "_gemini_call", none_gemini)
    assert asyncio.run(c.complete_json("s", "u")) is None
```

- [ ] **Step 3: Run to verify failure** → FAIL (module missing).

- [ ] **Step 4: Implement**

`api/app/llm/client.py`:
```python
"""Groq-first JSON completion with Gemini fallback. Never raises; returns None on failure."""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.llm.ratelimit import GroqRateLimiter

log = logging.getLogger(__name__)
_limiters: dict[str, GroqRateLimiter] = {}


def llm_enabled() -> bool:
    s = get_settings()
    return s.use_llm and bool(s.groq_api_key or s.google_api_key)


def _limiter(model: str) -> GroqRateLimiter:
    s = get_settings()
    if model not in _limiters:
        _limiters[model] = GroqRateLimiter(rpm=s.groq_rpm, tpm=s.groq_tpm)
    return _limiters[model]


def _gemini_timeout() -> float:
    return get_settings().gemini_timeout_s


async def _groq_call(model: str, system: str, user: str) -> str:
    from groq import AsyncGroq
    s = get_settings()
    if not s.groq_api_key:
        raise RuntimeError("no groq key")
    await asyncio.to_thread(_limiter(model).wait, GroqRateLimiter.estimate_tokens(system + user) + 400)
    resp = await AsyncGroq(api_key=s.groq_api_key).chat.completions.create(
        model=model, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content or ""


async def _gemini_call(system: str, user: str) -> str:
    from google import genai
    from google.genai import types
    s = get_settings()
    if not s.google_api_key:
        raise RuntimeError("no gemini key")
    client = genai.Client(api_key=s.google_api_key)
    resp = await client.aio.models.generate_content(
        model=s.gemini_model, contents=user,
        config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0),
    )
    return resp.text or ""


def _parse(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def complete_json(system: str, user: str, *, fast: bool = False) -> dict | None:
    if not llm_enabled():
        return None
    s = get_settings()
    model = s.groq_model_fast if fast else s.groq_model
    try:
        data = _parse(await _groq_call(model, system, user))
        if data is not None:
            return data
    except Exception as exc:  # noqa: BLE001
        log.warning("groq call failed: %s", type(exc).__name__)
    try:
        return _parse(await asyncio.wait_for(_gemini_call(system, user), timeout=_gemini_timeout()))
    except Exception as exc:  # noqa: BLE001
        log.warning("gemini fallback failed: %s", type(exc).__name__)
        return None
```

- [ ] **Step 5: Run tests** → `pytest tests/test_llm_client.py -v` → PASS.

- [ ] **Step 6: Commit** — `feat(llm): Groq JSON client with per-model rate limit and Gemini fallback` (+ Co-Authored-By).

---

### Task 6: Port M1 corpus pipeline with fastembed

**Files:**
- Create: `api/app/corpus/sources.yaml`, `fetcher.py`, `parser.py`, `chunker.py`, `indexer.py`, `query_parser.py`, `retriever.py` (ported), `embedder.py` (new)
- Create: `api/tests/fixtures/raw/` (copied HTML snapshots)
- Test: `api/tests/test_corpus_port.py` plus ported M1 tests `test_parser.py`, `test_chunker.py`, `test_retrieval.py`

**Interfaces:**
- Consumes: `app.config` (`Settings`, `get_settings`, `load_schemes`, `is_allowed_source_url`, `ALLOWED_SOURCE_DOMAINS`)
- Produces (unchanged M1 signatures): `fetch_scheme_pages(...) -> FetchReport`, `parse_scheme_pages(...) -> ParseReport`, `chunk_scheme_pages(...) -> ChunkReport`, `build_index(...) -> IndexReport`, `open_collection(...)`, `collection_count(...)`, `parse_query(query, schemes=None) -> QueryHints`, `Retriever(...).retrieve(query) -> RetrievalResult` with `.status ∈ {"ok","empty","ambiguous_scheme","no_scheme","low_confidence"}`, `.winner: RetrievedChunk | None` (`source_url, fact_key, page_or_section, text, scheme_id, scheme_name, ingested_at, document_date`), `.hints`, `.candidates`. New: `app.corpus.embedder.EmbeddingService` (same protocol: `embed_documents`, `embed_query`, `model_name`, `dimension`), `get_embedding_service()`.

- [ ] **Step 1: Copy files and rewrite imports**

```bash
M1="C:/Users/dhruv/OneDrive/Desktop/RAG Chat bot- Mutual Funds"
cp "$M1/src/config/schemes.yaml" api/app/corpus/sources.yaml
for f in fetcher parser chunker indexer; do cp "$M1/src/ingestion/$f.py" api/app/corpus/; done
for f in query_parser retriever; do cp "$M1/src/retrieval/$f.py" api/app/corpus/; done
mkdir -p api/tests/fixtures/raw && cp "$M1"/data/raw/*.html "$M1"/data/raw/*.meta.json api/tests/fixtures/raw/
for f in api/app/corpus/*.py; do
  sed -i -e 's/from src\.config\.settings import/from app.config import/' \
         -e 's/from src\.ingestion\./from app.corpus./' \
         -e 's/from src\.retrieval\./from app.corpus./' \
         -e 's/from src\.retrieval import/from app.corpus import/' "$f"
done
grep -rn "src\." api/app/corpus/ || echo "no src. imports left"
```
Expected: `no src. imports left`.

In `sources.yaml`, add `kind: scheme` under every scheme entry, and append an empty list for Plan 2:
```yaml
# Reference pages (fee concepts) — added in Plan 2 after inspection
references: []
```

- [ ] **Step 2: Replace the embedder**

`api/app/corpus/embedder.py`:
```python
"""fastembed (ONNX) embedding service — same BGE model as M1, no PyTorch."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol, Sequence

from app.config import Settings, get_settings

log = logging.getLogger(__name__)
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    @property
    def model_name(self) -> str: ...
    @property
    def dimension(self) -> int: ...


class EmbeddingService:
    def __init__(self, model_name: str | None = None, *, settings: Settings | None = None, model: object | None = None) -> None:
        cfg = settings or get_settings()
        self._model_name = model_name or cfg.embedding_model_name
        self._batch_size = cfg.embedding_batch_size
        self._model = model
        self._dimension: int | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_documents(["dimension probe"])[0])
        return self._dimension

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            log.info("Loading embedding model: %s", self._model_name)
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._get_model().embed(list(texts), batch_size=self._batch_size)
        return [[float(x) for x in v] for v in vecs]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([f"{_BGE_QUERY_INSTRUCTION}{text.strip()}"])[0]


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
```

- [ ] **Step 3: Port M1's parser/chunker/retrieval tests**

```bash
for t in test_parser test_chunker test_retrieval; do cp "$M1/tests/$t.py" api/tests/; done
sed -i -e 's/from src\.config\.settings import/from app.config import/' -e 's/from src\.ingestion\./from app.corpus./' \
       -e 's/from src\.retrieval\./from app.corpus./' -e 's/from src\.retrieval import/from app.corpus import/' \
       -e 's/from src\.config import/from app.config import/' api/tests/test_parser.py api/tests/test_chunker.py api/tests/test_retrieval.py
```
Where a ported test reads `PROJECT_ROOT / "data" / "raw"` or `settings.data_raw_dir`, point it to `Path(__file__).parent / "fixtures" / "raw"`. Where a test asserts `sentence_transformers` behaviour, delete only that test function.

- [ ] **Step 4: Write the new end-to-end corpus test**

`api/tests/test_corpus_port.py`:
```python
from pathlib import Path

import pytest

from app.corpus.chunker import chunk_scheme_pages
from app.corpus.embedder import EmbeddingService
from app.corpus.indexer import build_index
from app.corpus.parser import parse_scheme_pages
from app.corpus.retriever import Retriever

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


@pytest.fixture(scope="module")
def built_index(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    processed, index = root / "processed", root / "index"
    assert parse_scheme_pages(raw_dir=FIXTURES, processed_dir=processed).ok_count == 15
    chunk_scheme_pages(processed_dir=processed)
    report = build_index(processed_dir=processed, index_dir=index, embedder=EmbeddingService())
    assert report.all_ok
    return index


def test_embedder_dimension():
    assert EmbeddingService().dimension == 384


def test_retrieves_mid_cap_exit_load(built_index):
    r = Retriever(index_dir=built_index).retrieve("What is the exit load of HDFC Mid Cap Fund?")
    assert r.status == "ok"
    assert r.winner.fact_key == "exit_load"
    assert r.winner.source_url == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"


def test_hinglish_query_still_resolves(built_index):
    r = Retriever(index_dir=built_index).retrieve("mid cap ka exit load kitna hai")
    assert r.status == "ok" and r.winner.fact_key == "exit_load"


def test_ambiguous_scheme(built_index):
    r = Retriever(index_dir=built_index).retrieve("exit load of mid cap and small cap")
    assert r.status == "ambiguous_scheme"
```

- [ ] **Step 5: Run** → `pytest tests/test_corpus_port.py tests/test_parser.py tests/test_chunker.py tests/test_retrieval.py -v`
Expected: PASS (first run downloads the ~130 MB ONNX model). Fix any remaining import or path errors in the ported files, not in the tests' assertions.

- [ ] **Step 6: Commit** — `feat(corpus): port M1 ingestion and retrieval onto fastembed` (+ Co-Authored-By).

---

### Task 7: Corpus refresh service, Source rows and status

**Files:**
- Create: `api/app/corpus/refresh.py`; Modify: `api/app/corpus/status.py`
- Test: `api/tests/test_refresh.py`

**Interfaces:**
- Consumes: Task 6 pipeline functions; `Source` model.
- Produces: `refresh_corpus(db: Session, *, fetch: bool = True, raw_dir: Path | None = None) -> RefreshResult` (dataclass: `ok: int, stale: int, error: int, reindexed: bool`); `corpus_status() -> dict` (`{"vectors": int, "ready": bool}`); `last_checked_for(db, url) -> str | None` (ISO date).

Behaviour: fetch all scheme pages (unless `fetch=False`, which reuses `raw_dir`); for each scheme upsert a `Source` row: on success `status="ok"`, `fetched_at=now`, `content_hash` from the fetch report; on fetch error keep the previous raw snapshot, set `status="stale"` if a previous `fetched_at` exists else `"error"`, leaving `fetched_at` unchanged. Re-parse → re-chunk → rebuild index only if any hash changed or the index is empty.

- [ ] **Step 1: Write the failing test**

`api/tests/test_refresh.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from app.corpus import refresh as rf
from app.models import Source

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


def _settings(tmp_path, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "data_raw_dir", tmp_path / "raw")
    monkeypatch.setattr(s, "data_processed_dir", tmp_path / "processed")
    monkeypatch.setattr(s, "data_index_dir", tmp_path / "index")
    return s


def test_refresh_from_fixtures_creates_sources(db_session, tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    res = rf.refresh_corpus(db_session, fetch=False, raw_dir=FIXTURES)
    assert res.ok == 15 and res.reindexed
    rows = db_session.query(Source).all()
    assert len(rows) == 15 and all(r.status == "ok" and r.fetched_at for r in rows)


def test_fetch_failure_marks_stale_and_keeps_date(db_session, tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    rf.refresh_corpus(db_session, fetch=False, raw_dir=FIXTURES)
    before = {r.url: r.fetched_at for r in db_session.query(Source)}

    def failing_fetch(**kwargs):
        from app.corpus.fetcher import FetchReport, FetchResult
        return FetchReport(results=[FetchResult(scheme_id=s["scheme_id"], url=s["url"], status="error", error="timeout")
                                    for s in kwargs["schemes"]])
    monkeypatch.setattr(rf, "fetch_scheme_pages", failing_fetch)
    res = rf.refresh_corpus(db_session, fetch=True, raw_dir=FIXTURES)
    assert res.stale == 15
    for r in db_session.query(Source):
        assert r.status == "stale" and r.fetched_at == before[r.url]
```

Note: check the real `FetchReport`/`FetchResult` constructor fields in `app/corpus/fetcher.py` (lines 60–140 in M1) and adjust the fake to match exactly.

- [ ] **Step 2: Run to verify failure** → FAIL (no `refresh_corpus`).

- [ ] **Step 3: Implement**

`api/app/corpus/refresh.py`:
```python
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
            new_hash = getattr(r, "content_hash", None) if r else row.content_hash or "fixture"
            changed |= new_hash != row.content_hash
            row.status, row.fetched_at, row.content_hash, row.error = "ok", now, new_hash, None
            res.ok += 1
        else:
            row.error = getattr(r, "error", "fetch failed")
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
```

`api/app/corpus/status.py`:
```python
def corpus_status() -> dict:
    try:
        from app.corpus.indexer import collection_count
        n = collection_count()
    except Exception:  # noqa: BLE001
        n = 0
    return {"vectors": n, "ready": n > 0}
```

Adjust attribute names (`r.ok`, `r.content_hash`, `r.error`, `report.results`) to the real `FetchResult`/`FetchReport` fields; adjust `collection_count()` call to its real signature.

- [ ] **Step 4: Run** → `pytest tests/test_refresh.py tests/test_health.py -v` → PASS.

- [ ] **Step 5: Commit** — `feat(corpus): refresh service with stale-on-failure Source rows` (+ Co-Authored-By).

---

### Task 8: Desk contracts and templates

**Files:**
- Create: `api/app/desk/__init__.py` (empty), `api/app/desk/contracts.py`, `api/app/desk/templates.py`
- Test: `api/tests/test_contracts.py`

**Interfaces:**
- Produces: M3 contracts with `SchemeId = str`, `ThemeId = str`: `DateWindow, FactsResult, PatternResult, ComplianceResult, RoutingNote, OrchestratorOutput, ReviewerFailure, ReviewerResult`; `Disposition = Literal["reply","escalate","handoff","refuse","disagree","account"]`; `ThemeStat` (new, below). Templates: `ADVICE_REFUSAL`, `PERFORMANCE_REFUSAL`, `ACCOUNT_REPLY`, `not_covered_reply(searched: list[str]) -> str`, `covered_reply(fact, citation, last_checked) -> str`, `REFUSAL_LINK = "https://groww.in/p/mutual-funds"`.

- [ ] **Step 1: Copy and adapt contracts**

```bash
cp "C:/Users/dhruv/multi agentic system/multi-agentic-system/src/groww_support/contracts.py" api/app/desk/contracts.py
```
Edit `api/app/desk/contracts.py`:
- Replace `SchemeId = Literal[...]` with `SchemeId = str` and `ThemeId = Literal[...]` with `ThemeId = str`.
- Replace `Disposition = Literal[...]` with `Disposition = Literal["reply", "escalate", "handoff", "refuse", "disagree", "account"]`.
- Change `PiiType = Literal[...]` to `PiiType = str`.
- Delete `AgentsFiredEntry` and `SessionState` (refinement sessions are out of scope).
- Append:
```python
class ThemeStat(BaseModel):
    """Weekly-loop theme snapshot consumed by the Pattern agent (populated in Plan 2)."""
    theme_id: str
    name: str
    team: str
    cues: list[str]
    count: int
    recent_count: int
    window: DateWindow
    recent_window: DateWindow
```

`api/app/desk/templates.py`:
```python
REFUSAL_LINK = "https://groww.in/p/mutual-funds"

ADVICE_REFUSAL = (
    "We share facts only and can't advise on buying, selling or holding any fund. "
    "Each scheme's official facts are on its Groww page."
)
PERFORMANCE_REFUSAL = (
    "We can't share past or projected figures for any fund. "
    "Please refer to the scheme's official page on Groww for its published information."
)
ACCOUNT_REPLY = (
    "We can't see or change individual accounts from here. "
    "Please raise this through Help & Support in the Groww app so the team can check your account."
)


def not_covered_reply(searched: list[str]) -> str:
    where = ", ".join(searched[:6]) if searched else "our HDFC scheme pages"
    return f"Our official sources don't cover this question. Searched: {where}."


def covered_reply(fact: str, citation: str, last_checked: str) -> str:
    fact = fact.strip().rstrip(".") + "."
    return f"{fact} Source: {citation} Last checked: {last_checked}."
```

- [ ] **Step 2: Write the failing test**

`api/tests/test_contracts.py`:
```python
import pytest

from app.desk.contracts import FactsResult
from app.desk.templates import ADVICE_REFUSAL, ACCOUNT_REPLY, PERFORMANCE_REFUSAL, covered_reply, not_covered_reply
from app.guard.scope import check_output


def test_covered_requires_citation():
    with pytest.raises(ValueError):
        FactsResult(status="covered", searched=[], fact="x")


@pytest.mark.parametrize("text", [
    ADVICE_REFUSAL, PERFORMANCE_REFUSAL, ACCOUNT_REPLY,
    not_covered_reply(["hdfc-mid-cap-fund-direct-growth:exit_load"]),
    covered_reply("Exit load of 1% if redeemed within 1 year..", "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth", "2026-11-17"),
])
def test_templates_pass_scope_filter(text):
    assert check_output(text, kind="reply") == []
```

- [ ] **Step 3: Run** → `pytest tests/test_contracts.py -v` → initially FAIL; after Step 1 files exist, PASS. If a template trips the filter (e.g. "holding" in ADVICE_REFUSAL hits `\bhold\b` — it should not, since `holding` ≠ `hold`), reword the template, not the filter.

- [ ] **Step 4: Commit** — `feat(desk): contracts and fixed reply templates` (+ Co-Authored-By).

---

### Task 9: Intent classifier (`intent/classifier.py`)

**Files:**
- Create: `api/app/intent/__init__.py` (empty), `api/app/intent/classifier.py`
- Test: `api/tests/test_intent.py`

**Interfaces:**
- Consumes: `app.corpus.query_parser.parse_query`, `app.llm.client.complete_json`
- Produces: `IntentResult` (pydantic: `intent: Intent, scheme_ids: list[str], fact_key: str | None, language: Literal["en","hi","hinglish"], confidence: Literal["rule","llm","default"]`); `Intent = Literal["fee_question","fund_fact","how_to_process","advice_request","performance_request","account_issue","out_of_scope"]`; `async classify_intent(redacted_text: str) -> IntentResult`; `detect_language(text) -> str`.

Rule priority: transactional how-to ("how do I buy/redeem") > advice > performance > account_issue > fee > how_to > fund_fact > LLM (fast model) > out_of_scope. Misrouting between how_to and fund_fact is harmless: the Facts agent retrieves either way.

- [ ] **Step 1: Write the failing test**

`api/tests/test_intent.py`:
```python
import asyncio

import pytest

from app.intent.classifier import classify_intent, detect_language


def run(text):
    return asyncio.run(classify_intent(text))


@pytest.mark.parametrize("text,intent", [
    ("What is the exit load of HDFC Mid Cap?", "fee_question"),
    ("expense ratio of hdfc small cap fund", "fee_question"),
    ("mid cap ka exit load kitna hai", "fee_question"),
    ("What is the minimum SIP for HDFC ELSS?", "fund_fact"),
    ("benchmark of hdfc gilt fund", "fund_fact"),
    ("How do I redeem my units?", "how_to_process"),
    ("How do I buy HDFC Mid Cap on Groww?", "how_to_process"),
    ("How to sell my mutual fund units", "how_to_process"),
    ("sip kaise start kare", "how_to_process"),
    ("Should I buy HDFC Defence Fund?", "advice_request"),
    ("is mid cap fund good to invest now", "advice_request"),
    ("should I redeem because exit load is high", "advice_request"),
    ("kya mujhe small cap lena chahiye", "advice_request"),
    ("What returns did HDFC Mid Cap give last year?", "performance_request"),
    ("3 year CAGR of large cap fund", "performance_request"),
    ("kitna return milega", "performance_request"),
    ("My SIP amount was debited but units not credited", "account_issue"),
    ("my redemption money is stuck", "account_issue"),
    ("What is the weather today?", "out_of_scope"),
    ("🙂🙂", "out_of_scope"),
])
def test_rule_intents(text, intent):
    assert run(text).intent == intent


def test_scheme_and_fact_extracted():
    r = run("What is the exit load of HDFC Mid Cap?")
    assert r.scheme_ids == ["hdfc-mid-cap-fund-direct-growth"] and r.fact_key == "exit_load"


@pytest.mark.parametrize("text,lang", [
    ("What is the exit load?", "en"),
    ("mid cap ka exit load kitna hai", "hinglish"),
    ("एग्जिट लोड क्या है", "hi"),
])
def test_language(text, lang):
    assert detect_language(text) == lang


def test_devanagari_without_llm_is_out_of_scope_not_crash():
    assert run("एग्जिट लोड क्या है").intent in {"out_of_scope", "fee_question"}
```

- [ ] **Step 2: Run to verify failure** → FAIL (module missing).

- [ ] **Step 3: Implement**

`api/app/intent/classifier.py`:
```python
"""Rules-first intent classification; the fast LLM only resolves the gray zone."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from app.corpus.query_parser import parse_query
from app.llm.client import complete_json

Intent = Literal["fee_question", "fund_fact", "how_to_process", "advice_request",
                 "performance_request", "account_issue", "out_of_scope"]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]


class IntentResult(BaseModel):
    intent: Intent
    scheme_ids: list[str]
    fact_key: str | None
    language: Literal["en", "hi", "hinglish"]
    confidence: Literal["rule", "llm", "default"]


def _rx(*parts: str) -> re.Pattern[str]:
    return re.compile(r"(?i)\b(?:" + "|".join(parts) + r")\b")


_ADVICE = _rx(r"should i", r"shall i", r"is (?:it|this|the \w+(?: \w+)?(?: fund)?) (?:good|safe|worth|right|better)",
              r"good to (?:invest|buy)", r"worth (?:it|investing)", r"which (?:fund|scheme) (?:is|should)",
              r"recommend", r"better (?:fund|option|to)", r"buy", r"sell", r"switch (?:to|from)",
              r"lena chahiye", r"le lu", r"lu kya", r"kharid\w*", r"bech\w*", r"accha hai", r"sahi hai",
              r"invest karu", r"stay invested", r"exit now")
_PERF = _rx(r"returns?", r"cagr", r"xirr", r"performance", r"how much (?:will|did|can) (?:i|it) (?:earn|make|get|grow|gain)",
            r"kitna return", r"profit", r"nav (?:prediction|forecast|tomorrow|target)", r"outperform\w*", r"beat the market")
_ACCOUNT = _rx(r"not credited", r"debited", r"refund", r"stuck", r"failed", r"pending since",
               r"my (?:order|sip|money|units|payment|redemption|kyc)\w* (?:is|was|has|hasn'?t|not|didn'?t|got)",
               r"mera (?:paisa|sip|account|order)", r"paisa (?:nahi|nhi|not)", r"kyc (?:rejected|failed|pending)", r"not received", r"didn'?t receive")
_FEE = _rx(r"exit[\s-]?load", r"expense ratio", r"\bter\b", r"charges?", r"fees?", r"stamp duty", r"brokerage", r"commission",
           r"redemption load", r"kitna (?:charge|kat\w*)", r"kya charge")
_HOWTO = _rx(r"how (?:do|to|can|long|does)", r"kaise", r"steps?", r"process", r"procedure", r"redeem", r"withdraw\w*",
             r"start (?:a |an )?sip", r"stop (?:my |a )?sip", r"cancel (?:my |a )?sip", r"kyc", r"nominee", r"statement")
_HOWTO_TXN = _rx(r"how (?:do|to|can|should) (?:i |we |one )?(?:buy|sell|redeem|invest|purchase|switch)",
                 r"(?:buy|sell|redeem|invest) kaise")
_FACT_KEYS_FEE = {"exit_load", "expense_ratio"}
_HINGLISH = _rx(r"kya", r"hai", r"kaise", r"kitna", r"mera", r"mujhe", r"nahi", r"nhi", r"karu", r"kare", r"paisa", r"ka", r"ki", r"ke", r"chahiye")
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def detect_language(text: str) -> str:
    if _DEVANAGARI.search(text):
        return "hi"
    return "hinglish" if len(_HINGLISH.findall(text)) >= 2 else "en"


_LLM_SYSTEM = (
    "Classify a mutual-fund support question into exactly one intent. Return JSON {\"intent\": ...}. "
    f"Allowed: {list(INTENTS)}. advice_request = asks whether to buy/sell/hold/switch or if a fund is good. "
    "performance_request = asks for returns, CAGR, NAV forecasts. account_issue = a problem with the user's own "
    "order, money, SIP or KYC. fee_question = exit load, expense ratio, charges. fund_fact = minimum SIP, benchmark, "
    "riskometer, objective, fund manager. how_to_process = how to do something on the platform. Otherwise out_of_scope. "
    "The text may be Hindi or Hinglish. Tokens like [PAN] are redacted PII."
)


async def classify_intent(redacted_text: str) -> IntentResult:
    text = redacted_text.strip()
    hints = parse_query(text)
    base = dict(scheme_ids=list(hints.scheme_ids), fact_key=hints.fact_key, language=detect_language(text))

    def mk(intent: str, conf: str = "rule") -> IntentResult:
        return IntentResult(intent=intent, confidence=conf, **base)

    if _HOWTO_TXN.search(text) and not re.search(r"(?i)\bshould i\b", text):
        return mk("how_to_process")
    if _ADVICE.search(text):
        return mk("advice_request")
    if _PERF.search(text):
        return mk("performance_request")
    if _ACCOUNT.search(text):
        return mk("account_issue")
    if _FEE.search(text) or hints.fact_key in _FACT_KEYS_FEE:
        return mk("fee_question")
    if _HOWTO.search(text):
        return mk("how_to_process")
    if hints.fact_key:
        return mk("fund_fact")
    data = await complete_json(_LLM_SYSTEM, text, fast=True)
    if data and data.get("intent") in INTENTS:
        return mk(data["intent"], "llm")
    return mk("out_of_scope", "default")
```

- [ ] **Step 4: Run** → `pytest tests/test_intent.py -v` → PASS. When a case fails, adjust the narrowest regex; never reorder the priority (advice must beat fee for "should I redeem because exit load is high").

- [ ] **Step 5: Commit** — `feat(intent): rules-first intent classifier with Hinglish cues` (+ Co-Authored-By).

---

### Task 10: Facts, Pattern and Compliance agents

**Files:**
- Create: `api/app/desk/facts.py`, `api/app/desk/pattern.py`, `api/app/desk/compliance.py`
- Test: `api/tests/test_agents.py`

**Interfaces:**
- Consumes: `Retriever`, `IntentResult`, `ThemeStat`, `guard.pii.find_pii`, `templates.REFUSAL_LINK`
- Produces:
  - `run_facts(redacted_text: str, retriever: Retriever, last_checked: Callable[[str], str | None]) -> FactsResult` (sync; retriever is CPU-bound)
  - `run_pattern(redacted_text: str, themes: list[ThemeStat], *, today: date) -> PatternResult`
  - `run_compliance(redacted_text: str, pii_types: list[str], intent: IntentResult) -> ComplianceResult`
  - `team_for(theme: PatternResult) -> str` in pattern.py (default `"General support"`)

Facts semantics: `retrieve()` status `ok` → covered with `fact=winner.text`, `citation=winner.source_url`, `last_checked=last_checked(url) or winner.ingested_at[:10]`, `scheme_id=winner.scheme_id`, `section_title=winner.page_or_section`, `searched=[f"{scheme}:{fact_key}"]`. Any other status → not_covered with `searched` = `[f"{hit.scheme_id}:{hit.fact_key}" for hit in candidates]` or, when no candidates, the resolved scheme ids or `"all 15 HDFC scheme pages"`.

Pattern semantics: pick the theme whose `cues` appear most in the text (ties → higher count); none → synthetic `other` theme with count 0 and a 7-day window ending `today`. Signal: `count < 20 → one-off`; `recent_count >= 2 * (count - recent_count) / max(1, weeks_in_window - 1)` → `rising`; else `recurring`.

Compliance semantics: `flags` include `advice` if `intent.intent == "advice_request"`, `performance_claim` if `"performance_request"`, `pii` if `pii_types` or `find_pii(text)`; `advice_refusal = advice or performance`. No regex on raw verbs — intent already decided (fixes "how do I redeem" false positive).

- [ ] **Step 1: Write the failing test**

`api/tests/test_agents.py`:
```python
from datetime import date
from pathlib import Path

import pytest

from app.desk.compliance import run_compliance
from app.desk.contracts import DateWindow, ThemeStat
from app.desk.facts import run_facts
from app.desk.pattern import run_pattern
from app.intent.classifier import IntentResult

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    from app.corpus.chunker import chunk_scheme_pages
    from app.corpus.indexer import build_index
    from app.corpus.parser import parse_scheme_pages
    from app.corpus.retriever import Retriever
    root = tmp_path_factory.mktemp("c")
    parse_scheme_pages(raw_dir=FIXTURES, processed_dir=root / "p")
    chunk_scheme_pages(processed_dir=root / "p")
    build_index(processed_dir=root / "p", index_dir=root / "i")
    return Retriever(index_dir=root / "i")


def test_facts_covered(retriever):
    f = run_facts("exit load of hdfc mid cap fund", retriever, lambda url: "2026-11-17")
    assert f.status == "covered" and f.last_checked == "2026-11-17"
    assert f.citation.endswith("hdfc-mid-cap-fund-direct-growth")


def test_facts_not_covered_names_search(retriever):
    f = run_facts("who is the CEO of Groww", retriever, lambda url: None)
    assert f.status == "not_covered" and f.searched


def _theme(**kw):
    w = DateWindow(start="2026-09-22", end="2026-11-16")
    r = DateWindow(start="2026-11-10", end="2026-11-16")
    base = dict(theme_id="fees_charges", name="Fees & charges", team="Fees and mutual fund ops",
                cues=["exit load", "charges", "fee"], count=60, recent_count=30, window=w, recent_window=r)
    base.update(kw)
    return ThemeStat(**base)


def test_pattern_matches_cues_and_rising():
    p = run_pattern("why was exit load charged", [_theme()], today=date(2026, 11, 17))
    assert p.theme_id == "fees_charges" and p.signal == "rising" and p.count == 60


def test_pattern_no_themes_is_other_one_off():
    p = run_pattern("anything", [], today=date(2026, 11, 17))
    assert p.theme_id == "other" and p.signal == "one-off" and p.count == 0
    assert p.window.end == "2026-11-17"


def _intent(name):
    return IntentResult(intent=name, scheme_ids=[], fact_key=None, language="en", confidence="rule")


def test_compliance_uses_intent_not_verbs():
    c = run_compliance("How do I redeem my units?", [], _intent("how_to_process"))
    assert c.flags == [] and not c.advice_refusal
    c2 = run_compliance("should I buy", [], _intent("advice_request"))
    assert "advice" in c2.flags and c2.advice_refusal


def test_compliance_flags_residual_pii():
    c = run_compliance("call 9876543210", [], _intent("account_issue"))
    assert "pii" in c.flags and "PHONE" in c.pii_types
```

- [ ] **Step 2: Run to verify failure** → FAIL (modules missing).

- [ ] **Step 3: Implement**

`api/app/desk/facts.py`:
```python
from __future__ import annotations

from typing import Callable

from app.corpus.retriever import Retriever
from app.desk.contracts import FactsResult


def run_facts(redacted_text: str, retriever: Retriever, last_checked: Callable[[str], str | None]) -> FactsResult:
    r = retriever.retrieve(redacted_text)
    if r.status == "ok" and r.winner is not None:
        w = r.winner
        checked = last_checked(w.source_url) or (w.ingested_at or "")[:10] or None
        return FactsResult(status="covered", scheme_id=w.scheme_id, section_title=w.page_or_section,
                           fact=w.text, citation=w.source_url, last_checked=checked,
                           searched=[f"{w.scheme_id}:{w.fact_key}"])
    searched = [f"{c.scheme_id}:{c.fact_key}" for c in r.candidates]
    if not searched:
        searched = list(r.hints.scheme_ids) or ["all 15 HDFC scheme pages"]
    return FactsResult(status="not_covered", searched=searched)
```

`api/app/desk/pattern.py`:
```python
from __future__ import annotations

from datetime import date, timedelta

from app.desk.contracts import DateWindow, PatternResult, ThemeStat

DEFAULT_TEAM = "General support"


def _signal(t: ThemeStat) -> str:
    if t.count < 20:
        return "one-off"
    start, end = date.fromisoformat(t.window.start), date.fromisoformat(t.window.end)
    weeks = max(1, ((end - start).days + 1) // 7)
    earlier_weekly = (t.count - t.recent_count) / max(1, weeks - 1)
    return "rising" if t.recent_count >= 2 * earlier_weekly else "recurring"


def run_pattern(redacted_text: str, themes: list[ThemeStat], *, today: date) -> PatternResult:
    low = redacted_text.lower()
    scored = [(sum(c in low for c in t.cues), t.count, t) for t in themes]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        w = DateWindow(start=(today - timedelta(days=6)).isoformat(), end=today.isoformat())
        return PatternResult(theme_id="other", theme_name="Other", signal="one-off", count=0,
                             recent_count=0, window=w, recent_window=w)
    t = max(scored, key=lambda s: (s[0], s[1]))[2]
    return PatternResult(theme_id=t.theme_id, theme_name=t.name, signal=_signal(t), count=t.count,
                         recent_count=t.recent_count, window=t.window, recent_window=t.recent_window)


def team_for(theme_id: str, themes: list[ThemeStat]) -> str:
    return next((t.team for t in themes if t.theme_id == theme_id), DEFAULT_TEAM)
```

`api/app/desk/compliance.py`:
```python
from __future__ import annotations

from app.desk.contracts import ComplianceResult
from app.guard.pii import find_pii
from app.intent.classifier import IntentResult


def run_compliance(redacted_text: str, pii_types: list[str], intent: IntentResult) -> ComplianceResult:
    flags: list[str] = []
    advice = intent.intent == "advice_request"
    perf = intent.intent == "performance_request"
    if advice:
        flags.append("advice")
    if perf:
        flags.append("performance_claim")
    merged = list(dict.fromkeys([*pii_types, *find_pii(redacted_text)]))
    if merged:
        flags.append("pii")
    return ComplianceResult(flags=flags, pii_types=merged, advice_refusal=advice or perf, redacted_text=redacted_text)
```

- [ ] **Step 4: Run** → `pytest tests/test_agents.py -v` → PASS.

- [ ] **Step 5: Commit** — `feat(desk): facts over corpus, pattern over theme stats, intent-driven compliance` (+ Co-Authored-By).

---

### Task 11: Reviewer (`desk/reviewer.py`)

**Files:**
- Create: `api/app/desk/reviewer.py`
- Test: `api/tests/test_reviewer.py`

**Interfaces:**
- Consumes: `OrchestratorOutput`, `FactsResult`, `guard.scope`, `guard.pii.redact`, `templates`
- Produces: `review_draft(draft, *, facts, round: int) -> ReviewerResult`; `rewrite_draft(draft, *, facts, failures) -> OrchestratorOutput`.

Port of M3 `reviewer.py` with these differences: advice/performance/PII/shape checks call `guard.scope.check_output(draft.reply, kind="reply")` plus `check_output(draft.routing_note.why, kind="pulse")` filtered to `advice/performance/pii` (routing note has no sentence cap); no Gemini call; citation rules kept verbatim from M3 `_citation_failures` but `handoff`, `refuse` and `account` dispositions must have **no** URL except `templates.REFUSAL_LINK` is also disallowed in reply text (it is shown by the UI, not inside the reply). Covered dispositions (`reply`, `escalate`, `disagree`) require `last_checked` inside the reply text.

- [ ] **Step 1: Write the failing test**

`api/tests/test_reviewer.py`:
```python
from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.reviewer import review_draft, rewrite_draft
from app.desk.templates import covered_reply

URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
FACTS = FactsResult(status="covered", scheme_id="hdfc-mid-cap-fund-direct-growth", section_title="Exit Load",
                    fact="Exit load of 1% if redeemed within 1 year.", citation=URL, last_checked="2026-11-17",
                    searched=["x"])


def draft(reply, disposition="reply", citation=URL, last_checked="2026-11-17", why="Facts covered."):
    return OrchestratorOutput(reply=reply, citation=citation, last_checked=last_checked, disposition=disposition,
                              disagreement=False, routing_note=RoutingNote(team="t", priority="P3", why=why))


def test_good_covered_draft_passes():
    r = review_draft(draft(covered_reply(FACTS.fact, URL, "2026-11-17")), facts=FACTS, round=1)
    assert r.status == "pass", r.failures


def test_advice_fails_then_rewrite_passes():
    bad = draft("Exit load is 1%. You should buy now. Source: " + URL + " Last checked: 2026-11-17.")
    r1 = review_draft(bad, facts=FACTS, round=1)
    assert r1.status == "fail" and {f.check for f in r1.failures} >= {"advice"}
    fixed = rewrite_draft(bad, facts=FACTS, failures=r1.failures)
    assert review_draft(fixed, facts=FACTS, round=2).status == "pass"


def test_four_sentences_fail_shape():
    r = review_draft(draft("A. B. C. D. Source: " + URL + " Last checked: 2026-11-17."), facts=FACTS, round=1)
    assert "shape" in {f.check for f in r.failures}


def test_wrong_citation_fails():
    r = review_draft(draft(covered_reply(FACTS.fact, "https://groww.in/x", "2026-11-17"), citation="https://groww.in/x"),
                     facts=FACTS, round=1)
    assert "citation" in {f.check for f in r.failures}


def test_handoff_with_link_fails_and_second_round_blocks():
    d = draft("Not covered. See " + URL, disposition="handoff", citation=None, last_checked=None)
    assert review_draft(d, facts=None, round=1).status == "fail"
    assert review_draft(d, facts=None, round=2).status == "blocked"


def test_pii_in_routing_note_fails():
    d = draft(covered_reply(FACTS.fact, URL, "2026-11-17"), why="user phone 9876543210")
    assert "pii" in {f.check for f in review_draft(d, facts=FACTS, round=1).failures}
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

`api/app/desk/reviewer.py`:
```python
"""Outgoing-draft reviewer: hard checks in code, one deterministic rewrite, then block."""

from __future__ import annotations

import re

from app.desk.contracts import FactsResult, OrchestratorOutput, ReviewerFailure, ReviewerResult, RoutingNote
from app.desk.templates import covered_reply
from app.guard.pii import redact
from app.guard.scope import check_output, strip_advice_and_performance, truncate_sentences

_URL = re.compile(r"https?://[^\s\]\)>]+")
COVERED = ("reply", "escalate", "disagree")


def _clean(u: str) -> str:
    return u.rstrip(".,);")


def _citation_failures(d: OrchestratorOutput, facts: FactsResult | None) -> list[ReviewerFailure]:
    out: list[ReviewerFailure] = []
    urls = [_clean(u) for u in _URL.findall(d.reply)]
    if len(urls) > 1:
        out.append(ReviewerFailure(check="citation", detail=f"multiple links: {len(urls)}"))
    if d.disposition in COVERED:
        if not d.citation:
            out.append(ReviewerFailure(check="citation", detail="covered draft missing citation"))
        if facts is not None and facts.status == "covered" and d.citation and d.citation != facts.citation:
            out.append(ReviewerFailure(check="citation", detail="citation does not match Facts source"))
        if urls and d.citation and any(u != d.citation for u in urls):
            out.append(ReviewerFailure(check="citation", detail="reply link differs from citation"))
    elif urls:
        out.append(ReviewerFailure(check="citation", detail=f"{d.disposition} draft must not include links"))
    return out


def _shape_failures(d: OrchestratorOutput) -> list[ReviewerFailure]:
    if d.disposition in COVERED and (not d.last_checked or d.last_checked not in d.reply):
        return [ReviewerFailure(check="shape", detail="covered reply must include last_checked date")]
    return []


def review_draft(draft: OrchestratorOutput, *, facts: FactsResult | None, round: int) -> ReviewerResult:
    failures = _citation_failures(draft, facts) + _shape_failures(draft)
    failures += [ReviewerFailure(check=v.check, detail=v.detail) for v in check_output(draft.reply, kind="reply")]
    failures += [ReviewerFailure(check=v.check, detail="routing note: " + v.detail)
                 for v in check_output(draft.routing_note.why, kind="pulse") if v.check != "shape"]
    seen: set[str] = set()
    unique = [f for f in failures if not (f.check in seen or seen.add(f.check))]
    status = "pass" if not unique else ("blocked" if round >= 2 else "fail")
    return ReviewerResult(status=status, round=round, failures=unique)


def rewrite_draft(draft: OrchestratorOutput, *, facts: FactsResult | None,
                  failures: list[ReviewerFailure]) -> OrchestratorOutput:
    checks = {f.check for f in failures}
    reply, why = draft.reply, draft.routing_note.why
    citation, last_checked = draft.citation, draft.last_checked
    covered = facts is not None and facts.status == "covered"
    if covered and draft.disposition in COVERED and checks & {"citation", "shape", "advice", "performance"}:
        citation, last_checked = facts.citation, facts.last_checked
        reply = covered_reply(facts.fact, facts.citation, facts.last_checked)
    else:
        if checks & {"advice", "performance"}:
            reply = strip_advice_and_performance(reply)
        if "citation" in checks and draft.disposition not in COVERED:
            reply = _URL.sub("", reply).strip()
    reply = redact(truncate_sentences(reply, 3)).text
    why = redact(strip_advice_and_performance(why) or why).text
    return OrchestratorOutput(reply=reply, citation=citation, last_checked=last_checked,
                              disposition=draft.disposition, disagreement=draft.disagreement,
                              routing_note=RoutingNote(team=draft.routing_note.team,
                                                       priority=draft.routing_note.priority, why=why))
```

- [ ] **Step 4: Run** → `pytest tests/test_reviewer.py -v` → PASS.

- [ ] **Step 5: Commit** — `feat(desk): reviewer over shared scope filter with one rewrite` (+ Co-Authored-By).

---

### Task 12: Orchestrator — parallel desk run (`desk/orchestrator.py`)

**Files:**
- Create: `api/app/desk/orchestrator.py`
- Test: `api/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: Tasks 8–11.
- Produces: `DeskResult` (pydantic: `draft: OrchestratorOutput, review: ReviewerResult, facts: FactsResult, pattern: PatternResult, compliance: ComplianceResult`); `async run_desk(redacted_text: str, pii_types: list[str], intent: IntentResult, *, retriever: Retriever, themes: list[ThemeStat], last_checked: Callable[[str], str | None], today: date) -> DeskResult`.

Graph: LangGraph `START → {facts, pattern, compliance} → join → END` (the three run concurrently; facts runs via `asyncio.to_thread`). Then `merge_draft` (ported from M3 with templates) and `review → rewrite once → review`. Disposition rules (in order): `compliance.advice_refusal` → `refuse` (reply = `PERFORMANCE_REFUSAL` if `performance_claim` flag else `ADVICE_REFUSAL`); `intent == account_issue` → `account` (`ACCOUNT_REPLY`, team "Customer support", priority P2); facts not covered → `handoff` (`not_covered_reply(facts.searched)`); pattern rising & recent_count ≥ 40 → `disagree`; pattern recurring/rising → `escalate`; else `reply`. Covered dispositions use `covered_reply(facts.fact, facts.citation, facts.last_checked)`. Routing `why` text is ported from M3 `_routing_why`, adding `"account"` → `"Account-specific issue routed to customer support; no account data accessed."`. Priority from M3 `priority_for`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_orchestrator.py`:
```python
import asyncio
from datetime import date
from pathlib import Path

import pytest

from app.desk.orchestrator import run_desk
from app.desk.templates import ACCOUNT_REPLY, ADVICE_REFUSAL, PERFORMANCE_REFUSAL
from app.guard.scope import sentence_count
from app.intent.classifier import classify_intent

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    from app.corpus.chunker import chunk_scheme_pages
    from app.corpus.indexer import build_index
    from app.corpus.parser import parse_scheme_pages
    from app.corpus.retriever import Retriever
    root = tmp_path_factory.mktemp("o")
    parse_scheme_pages(raw_dir=FIXTURES, processed_dir=root / "p")
    chunk_scheme_pages(processed_dir=root / "p")
    build_index(processed_dir=root / "p", index_dir=root / "i")
    return Retriever(index_dir=root / "i")


def desk(text, retriever):
    async def go():
        intent = await classify_intent(text)
        return await run_desk(text, [], intent, retriever=retriever, themes=[],
                              last_checked=lambda u: "2026-11-17", today=date(2026, 11, 17))
    return asyncio.run(go())


def test_covered_question_replies_with_citation(retriever):
    r = desk("What is the exit load of HDFC Mid Cap Fund?", retriever)
    assert r.draft.disposition == "reply" and r.review.status == "pass"
    assert r.draft.citation.endswith("hdfc-mid-cap-fund-direct-growth")
    assert "2026-11-17" in r.draft.reply and sentence_count(r.draft.reply) <= 3


@pytest.mark.parametrize("text,expected", [
    ("Should I buy HDFC Defence Fund?", ADVICE_REFUSAL),
    ("What returns did mid cap give?", PERFORMANCE_REFUSAL),
    ("my SIP was debited but units not credited", ACCOUNT_REPLY),
])
def test_template_dispositions(retriever, text, expected):
    r = desk(text, retriever)
    assert r.draft.reply == expected and r.review.status == "pass"


def test_not_covered_names_searched(retriever):
    r = desk("Who is the CEO of Groww?", retriever)
    assert r.draft.disposition == "handoff" and "Searched:" in r.draft.reply
    assert r.review.status == "pass"


def test_works_with_llm_disabled_and_no_themes(retriever):
    r = desk("minimum sip for hdfc elss", retriever)
    assert r.pattern.theme_id == "other" and r.draft.reply
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement**

`api/app/desk/orchestrator.py`:
```python
"""Three specialists in parallel (LangGraph) → merge → reviewer (one rewrite)."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.corpus.retriever import Retriever
from app.desk.compliance import run_compliance
from app.desk.contracts import (ComplianceResult, FactsResult, OrchestratorOutput, PatternResult,
                                ReviewerResult, RoutingNote, ThemeStat)
from app.desk.facts import run_facts
from app.desk.pattern import run_pattern, team_for
from app.desk.reviewer import review_draft, rewrite_draft
from app.desk.templates import ACCOUNT_REPLY, ADVICE_REFUSAL, PERFORMANCE_REFUSAL, covered_reply, not_covered_reply
from app.intent.classifier import IntentResult

SURGE_RECENT = 40


class DeskResult(BaseModel):
    draft: OrchestratorOutput
    review: ReviewerResult
    facts: FactsResult
    pattern: PatternResult
    compliance: ComplianceResult


class _S(TypedDict, total=False):
    text: str
    pii: list[str]
    intent: IntentResult
    ctx: dict[str, Any]
    facts: FactsResult
    pattern: PatternResult
    compliance: ComplianceResult


async def _facts(s: _S):
    c = s["ctx"]
    return {"facts": await asyncio.to_thread(run_facts, s["text"], c["retriever"], c["last_checked"])}


async def _pattern(s: _S):
    return {"pattern": run_pattern(s["text"], s["ctx"]["themes"], today=s["ctx"]["today"])}


async def _compliance(s: _S):
    return {"compliance": run_compliance(s["text"], s["pii"], s["intent"])}


async def _join(s: _S):
    return {}


def _build():
    g = StateGraph(_S)
    for name, fn in (("facts", _facts), ("pattern", _pattern), ("compliance", _compliance), ("join", _join)):
        g.add_node(name, fn)
    for n in ("facts", "pattern", "compliance"):
        g.add_edge(START, n)
        g.add_edge(n, "join")
    g.add_edge("join", END)
    return g.compile()


_GRAPH = _build()


def _disposition(intent: IntentResult, f: FactsResult, p: PatternResult, c: ComplianceResult) -> str:
    if c.advice_refusal:
        return "refuse"
    if intent.intent == "account_issue":
        return "account"
    if f.status == "not_covered":
        return "handoff"
    if p.signal == "rising" and p.recent_count >= SURGE_RECENT:
        return "disagree"
    if p.signal in ("recurring", "rising"):
        return "escalate"
    return "reply"


def _priority(signal: str, disposition: str) -> str:
    if signal == "rising":
        return "P1"
    if disposition in ("escalate", "disagree", "account") or signal == "recurring":
        return "P2"
    return "P3"


def _why(disp: str, f: FactsResult, p: PatternResult) -> str:
    if disp == "refuse":
        return f"Compliance refusal (theme {p.theme_id}, signal={p.signal}, count={p.count})."
    if disp == "account":
        return "Account-specific issue routed to customer support; no account data accessed."
    if disp == "handoff":
        return f"Facts not covered for theme {p.theme_id}. Searched: {', '.join(f.searched[:12]) or 'none'}."
    if disp == "disagree":
        return (f"Corpus answers {f.scheme_id} {f.section_title}, but {p.recent_count} recent reviews match "
                f"{p.theme_id}; ticket stays open.")
    if disp == "escalate":
        return (f"Facts covered for {f.scheme_id} {f.section_title}. Theme {p.theme_id} is {p.signal} across "
                f"{p.count} reviews from {p.window.start} to {p.window.end}.")
    return f"Facts covered for {f.scheme_id} {f.section_title}. Theme {p.theme_id} is {p.signal} (count={p.count})."


def merge_draft(intent: IntentResult, f: FactsResult, p: PatternResult, c: ComplianceResult,
                themes: list[ThemeStat]) -> OrchestratorOutput:
    disp = _disposition(intent, f, p, c)
    citation = last_checked = None
    if disp == "refuse":
        reply = PERFORMANCE_REFUSAL if "performance_claim" in c.flags else ADVICE_REFUSAL
    elif disp == "account":
        reply = ACCOUNT_REPLY
    elif disp == "handoff":
        reply = not_covered_reply(f.searched)
    else:
        reply = covered_reply(f.fact, f.citation, f.last_checked)
        citation, last_checked = f.citation, f.last_checked
    team = "Customer support" if disp == "account" else team_for(p.theme_id, themes)
    return OrchestratorOutput(reply=reply, citation=citation, last_checked=last_checked, disposition=disp,
                              disagreement=disp == "disagree",
                              routing_note=RoutingNote(team=team, priority=_priority(p.signal, disp), why=_why(disp, f, p)))


async def run_desk(redacted_text: str, pii_types: list[str], intent: IntentResult, *, retriever: Retriever,
                   themes: list[ThemeStat], last_checked: Callable[[str], str | None], today: date) -> DeskResult:
    ctx = {"retriever": retriever, "themes": themes, "last_checked": last_checked, "today": today}
    s = await _GRAPH.ainvoke({"text": redacted_text, "pii": list(pii_types), "intent": intent, "ctx": ctx})
    draft = merge_draft(intent, s["facts"], s["pattern"], s["compliance"], themes)
    review = review_draft(draft, facts=s["facts"], round=1)
    if review.status == "fail":
        draft = rewrite_draft(draft, facts=s["facts"], failures=review.failures)
        review = review_draft(draft, facts=s["facts"], round=2)
    return DeskResult(draft=draft, review=review, facts=s["facts"], pattern=s["pattern"], compliance=s["compliance"])
```

Add `"account"` to `Disposition` in contracts (done in Task 8). If `OrchestratorOutput` still validates `disposition` against the old literal, update it.

- [ ] **Step 4: Run** → `pytest tests/test_orchestrator.py -v` → PASS.

- [ ] **Step 5: Commit** — `feat(desk): LangGraph parallel desk with merge and review` (+ Co-Authored-By).

---

### Task 13: Ticket service, approvals core and HTTP API

**Files:**
- Create: `api/app/tickets/__init__.py`, `api/app/tickets/service.py`, `api/app/approvals/__init__.py`, `api/app/approvals/service.py`, `api/app/api/__init__.py`, `api/app/api/public.py`, `api/app/api/console.py`, `api/app/deps.py`
- Modify: `api/app/main.py` (include routers; on startup, if `init_corpus` and index empty, run `refresh_corpus` in a background thread)
- Test: `api/tests/test_tickets_api.py`, `api/tests/test_approvals.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `tickets.service.preview(text: str) -> PreviewOut` (`redacted_text, pii_types, intent, scheme_ids, language, needs_clarification: bool, options: list[str]`)
  - `tickets.service.create_ticket(db, text: str, *, channel="text") -> Ticket` — redacts, classifies, stores, status `received`; raises `ValueError` on empty or > `max_message_chars`
  - `async tickets.service.process_ticket(db, ticket_id: int, *, retriever, themes_provider: Callable[[Session], list[ThemeStat]] = lambda db: []) -> Draft` — runs desk, stores `Draft`, creates `Action(type="reply_publish", draft_id=..., target_label=f"Reply to ticket {code}", target_ref=code)`, audit `create`, ticket → `in_review`. On any exception: ticket → `failed`, audit `fail`.
  - `approvals.service.approve(db, action_id, actor) -> Action`; `reject(db, action_id, actor) -> Action`; `edit_draft(db, draft_id, new_reply, actor) -> Draft` (redacts input, re-reviews, sets `edited=True`); `audit(db, actor, verb, entity, entity_id, detail="")`.
    - approve `reply_publish`: action `executed` (`decided_at`, `executed_at`), ticket `answered` with `answer_text = draft.reply`; audit `approve` + `execute`. Refuses (`ValueError`) if the draft's `review_status == "blocked"` or action not `pending`.
    - reject: action `rejected`; audit `reject`; ticket untouched.
    - edit: only that draft row + one audit row change.
  - HTTP:
    - `POST /api/ask/preview {text}` → PreviewOut
    - `POST /api/ask {text}` → `{code, status, notice}`; `notice` = static scope copy when intent is advice/performance, else null; schedules `process_ticket` as a background task
    - `GET /api/tickets/{code}` → `{code, status, question, answer, answered_at}` (`answer` only when `answered`)
    - Console (header `X-Console-Key` must equal `CONSOLE_PASSWORD`, else 401): `GET /api/console/queue` (tickets newest first with current draft + pending action), `POST /api/console/drafts/{id}/edit {reply}`, `POST /api/console/actions/{id}/approve`, `POST /api/console/actions/{id}/reject`, `GET /api/console/sources`, `POST /api/console/sources/refresh`
  - `app.deps.get_retriever()` (process-wide `Retriever`), `get_themes_provider()` (returns `lambda db: []` in Plan 1; Plan 2 replaces).

Clarification rule for preview: `needs_clarification = len(scheme_ids) > 1`; `options` = those scheme names.

- [ ] **Step 1: Write the failing tests**

`api/tests/test_tickets_api.py`:
```python
import asyncio

import pytest

from app import deps
from app.models import Action, AuditLog, Draft, Ticket
from app.tickets import service as ts

H = {"X-Console-Key": "test-pass"}


@pytest.fixture()
def wired(client, monkeypatch, tmp_path_factory):
    from pathlib import Path
    from app.corpus.chunker import chunk_scheme_pages
    from app.corpus.indexer import build_index
    from app.corpus.parser import parse_scheme_pages
    from app.corpus.retriever import Retriever
    fx = Path(__file__).parent / "fixtures" / "raw"
    root = tmp_path_factory.mktemp("t")
    parse_scheme_pages(raw_dir=fx, processed_dir=root / "p")
    chunk_scheme_pages(processed_dir=root / "p")
    build_index(processed_dir=root / "p", index_dir=root / "i")
    r = Retriever(index_dir=root / "i")
    monkeypatch.setattr(deps, "get_retriever", lambda: r)
    return client


def test_preview_redacts_and_classifies(wired):
    body = wired.post("/api/ask/preview", json={"text": "exit load of mid cap? my pan ABCDE1234F"}).json()
    assert "ABCDE1234F" not in body["redacted_text"] and body["intent"] == "fee_question"
    assert body["needs_clarification"] is False


def test_preview_ambiguous_asks_clarification(wired):
    body = wired.post("/api/ask/preview", json={"text": "exit load of mid cap and small cap"}).json()
    assert body["needs_clarification"] and len(body["options"]) == 2


@pytest.mark.parametrize("text", ["", "   ", "x" * 501])
def test_ask_rejects_empty_and_long(wired, text):
    assert wired.post("/api/ask", json={"text": text}).status_code == 422


def test_ask_flow_end_to_end(wired, db_session):
    r = wired.post("/api/ask", json={"text": "What is the exit load of HDFC Mid Cap? call 9876543210"})
    assert r.status_code == 200
    code = r.json()["code"]
    t = db_session.query(Ticket).filter_by(code=code).one()
    assert "9876543210" not in t.question_redacted and t.status == "in_review"
    q = wired.get("/api/console/queue", headers=H).json()
    item = next(i for i in q if i["code"] == code)
    assert item["draft"]["citation"].endswith("hdfc-mid-cap-fund-direct-growth")
    aid = item["action"]["id"]
    assert wired.get(f"/api/tickets/{code}").json()["answer"] is None
    assert wired.post(f"/api/console/actions/{aid}/approve", headers=H).status_code == 200
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["status"] == "answered" and "Last checked" in pub["answer"]


def test_advice_gets_notice_and_refusal_draft(wired):
    r = wired.post("/api/ask", json={"text": "Should I buy HDFC Defence Fund?"}).json()
    assert r["notice"]
    item = next(i for i in wired.get("/api/console/queue", headers=H).json() if i["code"] == r["code"])
    assert item["draft"]["disposition"] == "refuse"


@pytest.mark.parametrize("text", ["🙂🙂", "एग्जिट लोड क्या है", "asdfghjkl"])
def test_junk_input_never_500(wired, text):
    r = wired.post("/api/ask", json={"text": text})
    assert r.status_code == 200


def test_console_requires_key(wired):
    assert wired.get("/api/console/queue").status_code == 401


def test_nothing_in_db_contains_raw_pii(wired, db_session):
    wired.post("/api/ask", json={"text": "pan ABCDE1234F acct 50100234567890 phone +91 98765 43210 exit load mid cap"})
    blob = " ".join(str(v) for model in (Ticket, Draft, Action, AuditLog)
                    for row in db_session.query(model) for v in row.__dict__.values())
    for raw in ("ABCDE1234F", "50100234567890", "98765"):
        assert raw not in blob
```

`api/tests/test_approvals.py`:
```python
import asyncio

import pytest

from app.approvals.service import approve, edit_draft, reject
from app.models import Action, AuditLog, Draft, Ticket


def _snapshot(db):
    return {m.__tablename__: {r.id: {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
                              for r in db.query(m)} for m in (Ticket, Draft, Action, AuditLog)}


def _diff(a, b):
    changed = {}
    for table in a:
        ids = set(a[table]) | set(b[table])
        changed[table] = sorted(i for i in ids if a[table].get(i) != b[table].get(i))
    return changed


@pytest.fixture()
def two_tickets(db_session):
    rows = []
    for i in range(2):
        t = Ticket(code=f"T{i}", question_redacted="q", status="in_review")
        db_session.add(t); db_session.flush()
        d = Draft(ticket_id=t.id, reply="Fact. Source: https://groww.in/x Last checked: 2026-11-17.", citation="https://groww.in/x",
                  last_checked="2026-11-17", disposition="reply", routing_team="t", routing_priority="P3",
                  routing_why="w", review_status="pass")
        db_session.add(d); db_session.flush()
        a = Action(type="reply_publish", target_label="x", target_ref=t.code, draft_id=d.id)
        db_session.add(a); db_session.flush()
        rows.append((t, d, a))
    db_session.commit()
    return rows


def test_edit_changes_only_that_draft(db_session, two_tickets):
    (t0, d0, a0), _ = two_tickets
    before = _snapshot(db_session)
    edit_draft(db_session, d0.id, "Edited fact. Source: https://groww.in/x Last checked: 2026-11-17.", "agent")
    diff = _diff(before, _snapshot(db_session))
    assert diff["drafts"] == [d0.id] and diff["tickets"] == [] and diff["actions"] == []
    assert len(diff["audit_log"]) == 1


def test_approve_one_does_not_touch_other(db_session, two_tickets):
    (t0, d0, a0), (t1, d1, a1) = two_tickets
    before = _snapshot(db_session)
    approve(db_session, a0.id, "agent")
    diff = _diff(before, _snapshot(db_session))
    assert diff["actions"] == [a0.id] and diff["tickets"] == [t0.id] and diff["drafts"] == []
    assert len(diff["audit_log"]) == 2


def test_reject_leaves_queue_untouched(db_session, two_tickets):
    (t0, d0, a0), _ = two_tickets
    before = _snapshot(db_session)
    reject(db_session, a0.id, "agent")
    diff = _diff(before, _snapshot(db_session))
    assert diff["actions"] == [a0.id] and diff["tickets"] == [] and diff["drafts"] == []
    assert len(diff["audit_log"]) == 1


def test_cannot_approve_twice_or_blocked(db_session, two_tickets):
    (t0, d0, a0), (t1, d1, a1) = two_tickets
    approve(db_session, a0.id, "agent")
    with pytest.raises(ValueError):
        approve(db_session, a0.id, "agent")
    d1.review_status = "blocked"; db_session.commit()
    with pytest.raises(ValueError):
        approve(db_session, a1.id, "agent")


def test_edit_redacts_pii(db_session, two_tickets):
    (t0, d0, a0), _ = two_tickets
    d = edit_draft(db_session, d0.id, "Call 9876543210. Source: https://groww.in/x Last checked: 2026-11-17.", "agent")
    assert "9876543210" not in d.reply
```

- [ ] **Step 2: Run to verify failure** → `pytest tests/test_tickets_api.py tests/test_approvals.py -v` → FAIL.

- [ ] **Step 3: Implement approvals**

`api/app/approvals/service.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.reviewer import review_draft
from app.guard.pii import redact
from app.models import Action, AuditLog, Draft, Ticket


def _now():
    return datetime.now(timezone.utc)


def audit(db: Session, actor: str, verb: str, entity: str, entity_id: int, detail: str = "") -> None:
    db.add(AuditLog(actor=actor, verb=verb, entity=entity, entity_id=entity_id, detail=redact(detail).text))


def _pending(db: Session, action_id: int) -> Action:
    a = db.get(Action, action_id)
    if a is None:
        raise LookupError(f"action {action_id} not found")
    if a.status != "pending":
        raise ValueError(f"action {action_id} is {a.status}, not pending")
    return a


def approve(db: Session, action_id: int, actor: str) -> Action:
    a = _pending(db, action_id)
    if a.type != "reply_publish":
        raise ValueError(f"executor for {a.type} not available")  # Plan 3 adds doc_append/email_draft
    d = db.get(Draft, a.draft_id)
    if d.review_status == "blocked":
        raise ValueError("blocked draft cannot be approved; edit it first")
    t = db.get(Ticket, d.ticket_id)
    now = _now()
    a.status, a.decided_at, a.executed_at = "executed", now, now
    t.status, t.answer_text, t.answered_at = "answered", d.reply, now
    audit(db, actor, "approve", "action", a.id)
    audit(db, actor, "execute", "action", a.id, f"published to ticket {t.code}")
    db.commit()
    return a


def reject(db: Session, action_id: int, actor: str) -> Action:
    a = _pending(db, action_id)
    a.status, a.decided_at = "rejected", _now()
    audit(db, actor, "reject", "action", a.id)
    db.commit()
    return a


def edit_draft(db: Session, draft_id: int, new_reply: str, actor: str) -> Draft:
    d = db.get(Draft, draft_id)
    if d is None:
        raise LookupError(f"draft {draft_id} not found")
    reply = redact(new_reply.strip()).text
    out = OrchestratorOutput(reply=reply, citation=d.citation, last_checked=d.last_checked,
                             disposition=d.disposition, disagreement=d.disposition == "disagree",
                             routing_note=RoutingNote(team=d.routing_team, priority=d.routing_priority, why=d.routing_why))
    facts = (FactsResult(status="covered", scheme_id="edited", fact=reply, citation=d.citation,
                         last_checked=d.last_checked, searched=[]) if d.citation and d.last_checked else None)
    review = review_draft(out, facts=facts, round=1)
    d.reply, d.edited = reply, True
    d.review_status = "pass" if review.status == "pass" else "blocked"
    d.review_failures = [f.model_dump() for f in review.failures]
    audit(db, actor, "edit", "draft", d.id, f"review={d.review_status}")
    db.commit()
    return d
```

- [ ] **Step 4: Implement ticket service, deps and routers**

`api/app/deps.py`:
```python
from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException

from app.config import get_settings


@lru_cache
def get_retriever():
    from app.corpus.retriever import Retriever
    return Retriever()


def get_themes_provider():
    return lambda db: []


def require_console(x_console_key: str = Header(default="")) -> None:
    if x_console_key != get_settings().console_password:
        raise HTTPException(status_code=401, detail="console key required")
```

`api/app/tickets/service.py`:
```python
from __future__ import annotations

import logging
import secrets
from datetime import date
from typing import Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approvals.service import audit
from app.config import get_settings, load_schemes
from app.corpus.refresh import last_checked_for
from app.desk.orchestrator import run_desk
from app.guard.pii import redact
from app.intent.classifier import IntentResult, classify_intent
from app.models import Action, Draft, Ticket

log = logging.getLogger(__name__)
SCOPE_NOTICE = "We share facts only and can't advise on buying, selling or returns."
_ALPH = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PreviewOut(BaseModel):
    redacted_text: str
    pii_types: list[str]
    intent: str
    scheme_ids: list[str]
    language: str
    needs_clarification: bool
    options: list[str]


def _validate(text: str) -> str:
    t = (text or "").strip()
    if not t:
        raise ValueError("empty question")
    if len(t) > get_settings().max_message_chars:
        raise ValueError("question too long")
    return t


def _scheme_names() -> dict[str, str]:
    return {s["scheme_id"]: s["scheme_name"] for s in load_schemes()["schemes"]}


async def preview(text: str) -> PreviewOut:
    red = redact(_validate(text))
    intent = await classify_intent(red.text)
    names = _scheme_names()
    return PreviewOut(redacted_text=red.text, pii_types=red.pii_types, intent=intent.intent,
                      scheme_ids=intent.scheme_ids, language=intent.language,
                      needs_clarification=len(intent.scheme_ids) > 1,
                      options=[names.get(s, s) for s in intent.scheme_ids] if len(intent.scheme_ids) > 1 else [])


async def create_ticket(db: Session, text: str, *, channel: str = "text") -> tuple[Ticket, IntentResult]:
    red = redact(_validate(text))
    intent = await classify_intent(red.text)
    t = Ticket(code="GRW-" + "".join(secrets.choice(_ALPH) for _ in range(6)), channel=channel,
               language=intent.language, question_redacted=red.text, pii_types=red.pii_types,
               intent=intent.intent, scheme_id=intent.scheme_ids[0] if len(intent.scheme_ids) == 1 else None,
               fact_key=intent.fact_key, status="received")
    db.add(t)
    db.flush()
    audit(db, "public", "create", "ticket", t.id, f"intent={intent.intent}")
    db.commit()
    return t, intent


async def process_ticket(db: Session, ticket_id: int, *, retriever, themes_provider: Callable = lambda db: []) -> Draft | None:
    t = db.get(Ticket, ticket_id)
    try:
        intent = await classify_intent(t.question_redacted)
        res = await run_desk(t.question_redacted, list(t.pii_types), intent, retriever=retriever,
                             themes=themes_provider(db), last_checked=lambda u: last_checked_for(db, u),
                             today=date.today())
        d = Draft(ticket_id=t.id, reply=res.draft.reply, citation=res.draft.citation,
                  last_checked=res.draft.last_checked, disposition=res.draft.disposition,
                  routing_team=res.draft.routing_note.team, routing_priority=res.draft.routing_note.priority,
                  routing_why=res.draft.routing_note.why, review_status=res.review.status,
                  review_failures=[f.model_dump() for f in res.review.failures], searched=res.facts.searched)
        db.add(d)
        db.flush()
        a = Action(type="reply_publish", target_label=f"Reply to ticket {t.code}", target_ref=t.code, draft_id=d.id,
                   source_ref=f"ticket:{t.id}")
        db.add(a)
        db.flush()
        t.status = "in_review"
        audit(db, "desk", "create", "draft", d.id, f"disposition={d.disposition} review={d.review_status}")
        audit(db, "desk", "create", "action", a.id, "reply_publish")
        db.commit()
        return d
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("desk failed for ticket %s", t.code)
        t.status = "failed"
        audit(db, "desk", "fail", "ticket", t.id, type(exc).__name__)
        db.commit()
        return None
```

`api/app/api/public.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import deps
from app.db import SessionLocal, get_db
from app.models import Ticket
from app.tickets import service as ts

router = APIRouter(prefix="/api")


class AskIn(BaseModel):
    text: str


async def _process(ticket_id: int, db: Session | None = None):
    own = db is None
    db = db or SessionLocal()
    try:
        await ts.process_ticket(db, ticket_id, retriever=deps.get_retriever(), themes_provider=deps.get_themes_provider())
    finally:
        if own:
            db.close()


@router.post("/ask/preview")
async def ask_preview(body: AskIn):
    try:
        return await ts.preview(body.text)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/ask")
async def ask(body: AskIn, db: Session = Depends(get_db)):
    try:
        t, intent = await ts.create_ticket(db, body.text)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await _process(t.id, db)  # synchronous in Plan 1; Plan 3 moves this to a worker queue for latency
    notice = ts.SCOPE_NOTICE if intent.intent in ("advice_request", "performance_request") else None
    return {"code": t.code, "status": db.get(Ticket, t.id).status, "notice": notice}


@router.get("/tickets/{code}")
def ticket_status(code: str, db: Session = Depends(get_db)):
    t = db.query(Ticket).filter_by(code=code).one_or_none()
    if t is None:
        raise HTTPException(404, "ticket not found")
    return {"code": t.code, "status": t.status, "question": t.question_redacted,
            "answer": t.answer_text if t.status == "answered" else None, "answered_at": t.answered_at,
            "language": t.language}
```

`api/app/api/console.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approvals import service as ap
from app.corpus.refresh import refresh_corpus
from app.db import get_db
from app.deps import require_console
from app.models import Action, Draft, Source, Ticket

router = APIRouter(prefix="/api/console", dependencies=[Depends(require_console)])


class EditIn(BaseModel):
    reply: str


def _draft_out(d: Draft | None):
    if d is None:
        return None
    return {"id": d.id, "reply": d.reply, "citation": d.citation, "last_checked": d.last_checked,
            "disposition": d.disposition, "routing": {"team": d.routing_team, "priority": d.routing_priority,
                                                      "why": d.routing_why},
            "review_status": d.review_status, "review_failures": d.review_failures, "searched": d.searched,
            "reused_explainer_id": d.reused_explainer_id, "edited": d.edited}


@router.get("/queue")
def queue(db: Session = Depends(get_db)):
    out = []
    for t in db.query(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(200):
        d = db.query(Draft).filter_by(ticket_id=t.id).order_by(Draft.id.desc()).first()
        a = db.query(Action).filter_by(draft_id=d.id).order_by(Action.id.desc()).first() if d else None
        out.append({"code": t.code, "status": t.status, "intent": t.intent, "language": t.language,
                    "question": t.question_redacted, "pii_types": t.pii_types, "created_at": t.created_at,
                    "draft": _draft_out(d),
                    "action": {"id": a.id, "status": a.status, "target": a.target_label} if a else None})
    return out


def _guard(fn, *args):
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/drafts/{draft_id}/edit")
def edit(draft_id: int, body: EditIn, db: Session = Depends(get_db)):
    return _draft_out(_guard(ap.edit_draft, db, draft_id, body.reply, "console"))


@router.post("/actions/{action_id}/approve")
def approve(action_id: int, db: Session = Depends(get_db)):
    a = _guard(ap.approve, db, action_id, "console")
    return {"id": a.id, "status": a.status}


@router.post("/actions/{action_id}/reject")
def reject(action_id: int, db: Session = Depends(get_db)):
    a = _guard(ap.reject, db, action_id, "console")
    return {"id": a.id, "status": a.status}


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    return [{"url": s.url, "title": s.title, "kind": s.kind, "status": s.status,
             "last_checked": s.fetched_at.date().isoformat() if s.fetched_at else None, "error": s.error}
            for s in db.query(Source).order_by(Source.kind, Source.title)]


@router.post("/sources/refresh")
def refresh(db: Session = Depends(get_db)):
    r = refresh_corpus(db)
    return {"ok": r.ok, "stale": r.stale, "error": r.error, "reindexed": r.reindexed}
```

`api/app/main.py` — replace with:
```python
from __future__ import annotations

import logging
import threading

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db, init_db

log = logging.getLogger(__name__)


def _bootstrap_corpus() -> None:
    from app.corpus.refresh import refresh_corpus
    from app.corpus.status import corpus_status
    if corpus_status()["ready"]:
        return
    db = SessionLocal()
    try:
        refresh_corpus(db)
    except Exception:  # noqa: BLE001
        log.exception("initial corpus refresh failed")
    finally:
        db.close()


def create_app(*, init_corpus: bool = True) -> FastAPI:
    from app.guard.logfilter import install_log_redaction
    install_log_redaction()
    app = FastAPI(title="Groww Support Desk API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    init_db()

    from app.api.console import router as console_router
    from app.api.public import router as public_router
    app.include_router(public_router)
    app.include_router(console_router)

    @app.get("/health")
    def health(db: Session = Depends(get_db)):
        db.execute(text("select 1"))
        from app.corpus.status import corpus_status
        return {"db": "ok", "corpus": corpus_status()}

    if init_corpus:
        threading.Thread(target=_bootstrap_corpus, daemon=True).start()
    return app
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all PASS. In `test_tickets_api.py`, `get_db` is overridden to the test session, and `_process(t.id, db)` reuses it, so the queue sees the draft immediately.

- [ ] **Step 6: Live smoke (real Groq, real corpus)**

```bash
cd api && cp "C:/Users/dhruv/Groww-and-MCP/.env" .env  # GROQ_API_KEY, GOOGLE_API_KEY, GEMINI_MODEL
echo "CONSOLE_PASSWORD=dev-pass" >> .env
.venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000
```
In another shell, after `/health` shows `"ready": true` (first boot fetches 15 pages + builds the index, ~1–2 min):
```bash
curl -s -X POST localhost:8000/api/ask -H "Content-Type: application/json" -d '{"text":"What is the expense ratio of HDFC Small Cap Fund?"}'
curl -s localhost:8000/api/console/queue -H "X-Console-Key: dev-pass" | head -c 1200
```
Expected: a `reply` draft citing `https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth` with today's last-checked date, `review_status: "pass"`. Check the uvicorn log has no raw PII when you repeat with `my pan ABCDE1234F`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: ticket service, approvals core and public/console HTTP API

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage (Plan 1 scope):** §4 corpus/grounding → Tasks 6–7, 10; §5 intents → Task 9 (voice in Plan 3); §6 response loop → Tasks 10–13 (canonical check + question keys in Plan 2); §7 approvals core → Task 13 (MCP actions in Plan 3); §8 guard → Tasks 2–4, 10–11, 13; §11 unit tests → every task; §12 LLM/corpus errors → Tasks 5, 7, 13.
- **Deliberate deviation:** Aadhaar is redacted for any 4-4-4 digit group without a Verhoeff check (stricter than spec §8, so test/fake numbers are also caught).
- **Type consistency checked:** `ThemeStat`, `IntentResult`, `DeskResult`, `run_desk(...)` signature, `process_ticket(..., themes_provider=...)`, `Action.draft_id`, `Draft.searched` are used identically across tasks.
