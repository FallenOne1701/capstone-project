# Groww Support Desk — capstone (Milestone 4)

Final project: one deployed system for Groww (HDFC mutual funds) with two loops, linked, and nothing written or sent without human approval:
- **Response loop:** questions → cited, compliance-checked reply drafts.
- **Weekly loop:** Play Store reviews → themes → pulse + fee explainer.

Due ~2026-11-24. Graded on:
- Voice UX & intent 25%
- MCP usage & design 20%
- Grounding/RAG 15%
- AI evals & iteration 20%
- Workflow automation 10%
- Deployment & code quality 10%

The assignment brief was pasted into the 2026-11-18 session. Its key rules:
- one deployed link;
- a human approves / edits / rejects each draft, and nothing is written or sent without a human approving that specific action;
- interface: queue view, weekly pulse view, sources panel, approval screen showing exactly what is written where, canonical explainers view;
- 3 evals: feasibility, edit isolation, grounding/compliance;
- README contents + reviews CSV sample, 5 sample Q&As, appended doc entry, email draft, eval results.

## Where things are
- **Specs:**
  - `docs/superpowers/specs/2026-11-17-support-desk-design.md` (binding);
  - amended by `docs/superpowers/specs/2026-11-18-single-page-autonomous-desk-design.md`. Its "no human approval" part is now REVERSED; see Status.
- **Plans** (`docs/superpowers/plans/`):
  - Plan 1: API + response loop (merged, PR #1).
  - Plan 2: weekly loop + links + Google delivery (merged, PR #2).
  - Plan 3: `2026-11-17-plan-3-console-and-voice.md`.
  - Plan 3b: `2026-11-18-plan-3b-single-page-autonomous.md`.
  - Plan 4: evals + Railway/Vercel deploy (not written yet).
- **Ledgers** (git-ignored; read first when resuming):
  - `.superpowers/sdd/2026-11-17-plan-3-console-and-voice/progress.md`
  - `.superpowers/sdd/2026-11-18-plan-3b-single-page-autonomous/progress.md`

  Both hold every Ruling, the final-review results and the deferred minors.
- **GitHub:** private `FallenOne1701/capstone-project`. Each plan = its own branch + PR.

## Status (2026-11-19, Plan 4a deployed)

**Merged:** Plans 3, 3b, 3c are in `main` (PR #3, `8ff0ce7`).
**Branch:** `plan-4a-deploy` (Plan 4a), spec `docs/superpowers/specs/2026-11-19-deploy-railway-vercel-design.md`, plan `docs/superpowers/plans/2026-11-19-plan-4a-deploy.md`.

**Live:**
- Page: https://groww-support-desk.vercel.app (Vercel, user's Gmail/GitHub account `fallenone1701`, team `bomba8`).
- API: https://api-production-c6d78bb8.up.railway.app (Railway project `groww-support-desk`, service `api`, the user's SECOND Railway account; the CLI is logged in to it).
- SQLite on the Railway volume `/data` (user chose this over Postgres). `CORS_ORIGINS` = the Vercel address + localhost. `/health` shows db / corpus / google readiness.
- Live check 2026-11-19: GRW-9WYGL7 waited for a person, was approved via the page API and answered (0.73%, cited). No weekly run yet on Railway; no Google action touched.
- Redeploy steps are in `web/README.md` → "Deployed".
- User decision 2026-11-19: no password on the page. Approvals (including Google writes) stay open to anyone on the page; Google writes only append to the Doc or create a Gmail draft, never send.

**What Plan 3c built** (still true): `AUTO_APPROVE` default 0; open page API `/api/desk/*` (actor `page`, rate-limited, approve must send the reply text seen, else 409); ticket `closed` on reject + "Ask again"; weekly approvals show exactly what is written where; Google errors in plain words. Deferred minors from 3c: no length cap on edit text; Retry after a Google timeout may double-write; a daily cap on open weekly runs; the `models.py` status comment.

**Tests:** API 425+ passed (full run ~6–24 min), web vitest 48, Playwright 20.

### Then Plan 4b (not started; wait for the user)
- Evals: feasibility, edit isolation (diff state before/after), grounding/compliance with PAN / account number / phone, in both loops.
- README items listed in the brief, including a reviews CSV sample (we fetch live; export a sample, maybe add CSV ingest).
- Stretch: a Google service account for the Doc append.

### Open notes
- Google OAuth app stays in Testing, so the refresh token expires every 7 days. Re-run `npm run auth` in `C:/Users/dhruv/MCP Server 1` and update `GOOGLE_REFRESH_TOKEN` in `api/.env` AND on Railway (`railway variable set GOOGLE_REFRESH_TOKEN --stdin --service api` from `api/`) before demos/Mondays — or switch the OAuth app to "In production".
- Known limit: the MCP Doc append is plain text, so `#` headings show literally in the Doc.
- Next 16.4.2 has a published security advisory. `next dev`/`next build` sometimes stop to show it, and rerunning works. Upgrading is the user's call (pinned to match M3); decide in Plan 4.
- Deferred minors are listed in both ledgers.

## Run it
```bash
cd api && .venv/Scripts/python -m pytest -q                       # ~8 min, offline (USE_LLM=0 in tests)
.venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000
# /api/desk/* is the page's open approval API (actor "page", rate-limited); /api/console/* still needs X-Console-Key
# settings: AUTO_APPROVE (default 0 = a person approves), SCHEDULER_ENABLED, TRUST_PROXY
.venv/Scripts/python scripts/verify_weekly.py --log ../.superpowers/server.log

cd web && npm run dev          # the single page on :3000 (NEXT_PUBLIC_API_URL in web/.env.local)
npm test && npm run build && npm run e2e   # vitest, build, Playwright (own API :8001 + web :3001, e2e DB, no LLM/Google)
```
- Stop `npm run dev` before `npm run e2e`, because Next allows only one dev server per folder.
- `api/mcp_server/` is MCP Server 1 vendored (build: `npm ci && npm run build`).
- `api/.env` holds keys: never commit it, never print it.

## Working rules
- The user is not deeply technical: explain in plain language. They review each plan.
- Execution is Native (inline) + one fresh reviewer at the end. TDD for every change. Rulings go in the ledger.
- Never approve Google writes or push/merge without the user's explicit instruction.
- Earlier milestones (reference only):
  - M1 `~/OneDrive/Desktop/RAG Chat bot- Mutual Funds`
  - M2 `~/Groww-and-MCP`
  - M3 `~/multi agentic system/multi-agentic-system` (Next.js UI + Stitch design)
  - MCP `~/MCP Server 1`
