# Plan 4a — Deploy (Railway API + Vercel page) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One public link: the page on Vercel talking to the API on Railway, with a person approving on the page.

**Architecture:** Two small code changes (configurable CORS, a Google-readiness line in `/health`), a Dockerfile
for the API (Python 3.12 + Node 22 + vendored MCP build + pre-downloaded embedding model), then CLI provisioning:
Railway service + volume at `/data` holding SQLite, corpus/index and outbox; Vercel project rooted at `web/`.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, fastembed 0.9 (honours `FASTEMBED_CACHE_PATH`), Node 22, Railway CLI
5.74, Vercel CLI via `npx vercel`, Next.js 16.

**Spec:** `docs/superpowers/specs/2026-11-19-deploy-railway-vercel-design.md` (amends §10 of
`2026-11-17-support-desk-design.md`).

## Global Constraints
- Never commit, print or echo a key. Railway variables are set from `api/.env` by a script that never prints values; the user approves that command.
- Never approve a Google write on the live site without the user's explicit instruction.
- Local dev and the existing test suites behave exactly as before (CORS default `*`).
- Railway: one uvicorn worker; `AUTO_APPROVE=0`, `SCHEDULER_ENABLED=1`, `TRUST_PROXY=1`, `USE_LLM=1`.
- Volume mounted at `/data`: `DATABASE_URL=sqlite:////data/app.db`, `DATA_RAW_DIR=/data/corpus/raw`, `DATA_PROCESSED_DIR=/data/corpus/processed`, `DATA_INDEX_DIR=/data/corpus/index`, `DATA_OUTBOX_DIR=/data/outbox`.
- Vercel: `NEXT_PUBLIC_API_URL` = the Railway public URL, set **before** the production build (Next bakes it in).

## Review Focus
1. `CORS_ORIGINS` written with spaces or a trailing slash (`https://x.vercel.app/ , http://localhost:3000`) must still allow both origins — Task 1 test.
2. A disallowed origin gets no `access-control-allow-origin` header, while same-origin/no-Origin requests (health checks, curl) still work — Task 1 test.
3. `/health` must answer 200 while the corpus is still building on first boot (Railway would otherwise kill the deploy) — Task 2 test.
4. `/health` must never leak a key value, only which names are missing — Task 2 test.
5. First boot on an empty volume: the SQLite parent dir and corpus dirs must be created (`_make_engine` already mkdirs; corpus refresh creates its dirs) — verified live in Task 4 via `/health` showing `db: ok` then `corpus.ready: true`.

---

### Task 1: Configurable CORS origins

**Files:**
- Modify: `api/app/config.py` (Settings), `api/app/main.py:81`
- Test: `api/tests/test_deploy_config.py`

**Interfaces:**
- Produces: `Settings.cors_origins: str = "*"`; `def cors_origin_list(raw: str) -> list[str]` in `app/config.py` (split on commas, strip spaces and trailing `/`, drop empties; `"*"` → `["*"]`).

- [ ] **Step 1: Write the failing tests**

```python
def test_cors_origin_list_cleans_entries():
    from app.config import cors_origin_list
    assert cors_origin_list("https://x.vercel.app/ , http://localhost:3000,") == ["https://x.vercel.app", "http://localhost:3000"]
    assert cors_origin_list("*") == ["*"]

def test_listed_origin_allowed_other_refused(monkeypatch):
    # build an app with CORS_ORIGINS set; preflight from listed origin echoes it, from evil.com has no allow-origin header;
    # GET /health with no Origin still 200
```

- [ ] **Step 2: Run** `cd api && .venv/Scripts/python -m pytest tests/test_deploy_config.py -q` — Expected: FAIL (ImportError `cors_origin_list`).
- [ ] **Step 3: Implement** `cors_origin_list` and pass `allow_origins=cors_origin_list(get_settings().cors_origins)` in `create_app`.
- [ ] **Step 4: Run** the same command — Expected: PASS; then `pytest tests/test_desk_api.py -q` still passes.
- [ ] **Step 5: Commit** `feat: CORS origins from CORS_ORIGINS (default * unchanged)`.

### Task 2: `/health` says whether the Google tool is ready

**Files:**
- Modify: `api/app/delivery/mcp_client.py`, `api/app/main.py` (health)
- Test: `api/tests/test_deploy_config.py`

**Interfaces:**
- Produces: `def google_status() -> dict` in `app/delivery/mcp_client.py` returning `{"ready": bool, "missing": list[str]}`; missing names drawn from `"node"` (`shutil.which(settings.node_command)` is None), `"mcp_build"` (`dist/server.js` absent), `"GOOGLE_CLIENT_ID"`, `"GOOGLE_CLIENT_SECRET"`, `"GOOGLE_REFRESH_TOKEN"`, `"PULSE_DOC_ID"`. `/health` body gains `"google": google_status()`; still 200 regardless.

- [ ] **Step 1: Write the failing tests**

```python
def test_google_status_lists_missing_names_only(monkeypatch):
    # settings with refresh token "SECRET-VALUE" set, client id empty
    st = google_status()
    assert st["ready"] is False and "GOOGLE_CLIENT_ID" in st["missing"]
    assert "SECRET-VALUE" not in str(st)

def test_health_is_200_while_corpus_empty(client):
    r = client.get("/health")
    assert r.status_code == 200 and "google" in r.json() and r.json()["db"] == "ok"
```

- [ ] **Step 2: Run** the file — Expected: FAIL (`google_status` missing).
- [ ] **Step 3: Implement** `google_status()` and add it to the health body.
- [ ] **Step 4: Run** the file — Expected: PASS.
- [ ] **Step 5: Commit** `feat: /health reports Google tool readiness (names only)`.

### Task 3: API container

**Files:**
- Create: `api/Dockerfile`, `api/.dockerignore`, `api/railway.json`

**Decisions:**
- Base `python:3.12-slim`; install Node 22 from NodeSource; `WORKDIR /app`; copy `pyproject.toml` + `app/` then `pip install .` (no dev extras).
- `mcp_server/`: copy `package*.json` first, `npm ci`, copy `src/` + `tsconfig.json`, `npm run build`, then `npm prune --omit=dev`.
- `ENV FASTEMBED_CACHE_PATH=/opt/fastembed` and pre-download: `python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"`.
- `CMD sh -c "uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"`.
- `.dockerignore`: `.venv`, `data`, `.env`, `**/__pycache__`, `tests`, `mcp_server/node_modules`, `mcp_server/dist`, `mcp_server/.tokens`, `*.egg-info`.
- `railway.json`: builder DOCKERFILE, `healthcheckPath: "/health"`, `healthcheckTimeout: 300`, restart ON_FAILURE.

- [ ] **Step 1:** Write the three files. (No local Docker on this machine; the build is verified on Railway in Task 4.)
- [ ] **Step 2: Check** `git check-ignore` shows `.env` would not be sent: `cat api/.dockerignore | grep -x ".env"` — Expected: `.env`.
- [ ] **Step 3: Commit** `build: API Dockerfile for Railway (Python 3.12 + Node 22 + MCP + embedding model)`.

### Task 4: Railway provisioning (operational, user-approved commands)

- [ ] **Step 1:** `railway init` (project `groww-support-desk`) from `api/`; add a service; `railway volume add --mount-path /data`.
- [ ] **Step 2:** Set variables from `api/.env` with a script that reads the file and calls `railway variables --set KEY=VALUE --skip-deploys` per key, printing only key names; plus the Global Constraints values. Show the user the command before running it.
- [ ] **Step 3:** `railway up --detach` from `api/`; follow `railway logs --build` until the image builds — Expected: build success. Fix any build error (systematic-debugging) and redeploy.
- [ ] **Step 4:** `railway domain` → public URL. `curl <url>/health` — Expected: 200, `db: ok`, `google.ready: true` (or `missing` lists only what is genuinely unset); within ~10 min `corpus.ready: true`.
- [ ] **Step 5:** Record the URL in the ledger (not secrets).

### Task 5: Vercel page

- [ ] **Step 1:** User runs `! npx vercel login` (Gmail).
- [ ] **Step 2:** From `web/`: `npx vercel link` (new project `groww-support-desk`), `npx vercel env add NEXT_PUBLIC_API_URL production` = Railway URL, `npx vercel deploy --prod` — Expected: a `*.vercel.app` production URL.
- [ ] **Step 3:** `railway variables --set CORS_ORIGINS=<vercel url>,http://localhost:3000` (triggers redeploy). Expected after redeploy: preflight from the Vercel origin echoes it.
- [ ] **Step 4:** Ensure `web/.vercel/` is git-ignored; commit any ignore change.

### Task 6: Live check + handoff docs

- [ ] **Step 1:** On the Vercel URL (API calls via curl/Playwright against the live origin): ask "What is the expense ratio of HDFC Mid Cap Fund?" → ticket shows "Waiting for a person to approve this answer." → approve via `/api/desk/actions/{id}/approve` with the seen reply → ticket `answered` with a citation. Weekly section loads (`/api/desk/weekly/latest` 200 or 404 "no weekly runs yet"). Do **not** approve any Google action.
- [ ] **Step 2:** Update `web/README.md` (deploy section: URLs, env vars by name, SQLite-on-volume choice) and `CLAUDE.md` Status (Plan 4a done, URLs, how to redeploy: `railway up` from `api/`, `npx vercel deploy --prod` from `web/`).
- [ ] **Step 3:** Run full API pytest + web vitest; commit `docs: Plan 4a deployed — live URLs and redeploy steps`.
