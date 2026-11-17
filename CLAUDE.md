# Groww Support Desk — capstone (Milestone 4)

Final project: one deployed system for Groww (HDFC mutual funds) with a **response loop** (questions → cited, compliance-checked reply drafts) and a **weekly loop** (Play Store reviews → themes → pulse + fee explainer), linked, with nothing written or sent without human approval. Due ~2026-11-24. Graded on: Voice UX & intent 25%, MCP usage & design 20%, Grounding/RAG 15%, AI evals & iteration 20%, Workflow automation 10%, Deployment & code quality 10%.

## Where things are
- Spec: `docs/superpowers/specs/2026-11-17-support-desk-design.md` (binding authority)
- Plans: `docs/superpowers/plans/` — Plan 1 (API foundation + response loop, merged as PR #1), Plan 2 (weekly loop + links + Google delivery, branch `plan-2-weekly-loop`), Plan 3 (console UI, voice), Plan 4 (evals, Railway + Vercel deploy). Plan 1 ledger: `docs/superpowers/plans/2026-11-17-plan-1-ledger.md`.
- Live execution ledger for the current plan: `.superpowers/sdd/<plan>/progress.md` (git-ignored; read it first when resuming).
- GitHub: private `FallenOne1701/capstone-project`. Each plan = its own branch + PR.

## Status (2026-11-17)
- Plan 2: done — 290 tests green, live runs 3–4 delivered to Google Doc + Gmail draft after user approval, Link 2 verified live (brokerage question → reused canonical explainer #4). Fresh-context final review fixed (ledger: `docs/superpowers/plans/2026-11-17-plan-2-ledger.md`, incl. deferred items for Plan 3/4). PR open for user review — do not merge without their say-so.
- Known limit for Plan 3/4: the MCP Doc append is plain text, so `#` headings show literally in the Doc.
- Failed Google actions (e.g. expired token) can be retried: `POST /api/console/actions/{id}/retry`.
- Google OAuth app could not be published (restricted Gmail scope) → stays in Testing; refresh token expires every 7 days: re-run `npm run auth` in `C:/Users/dhruv/MCP Server 1` and update `GOOGLE_REFRESH_TOKEN` before demo/deploy.

## Run it
```bash
cd api && .venv/Scripts/python -m pytest -q                       # ~6 min, offline (USE_LLM=0 in tests)
.venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000
# console endpoints need header X-Console-Key: <CONSOLE_PASSWORD from api/.env>
.venv/Scripts/python scripts/verify_weekly.py --log ../.superpowers/server.log
```
`api/mcp_server/` is MCP Server 1 vendored (build: `npm ci && npm run build`); `api/.env` holds keys (never commit).

## Working rules
- User reviews each plan; execution is Native (inline) + one fresh reviewer at the end; TDD for every change; rulings go in the ledger.
- Never approve Google writes or push/merge without the user's explicit instruction.
- Earlier milestones (reference only): M1 `~/OneDrive/Desktop/RAG Chat bot- Mutual Funds`, M2 `~/Groww-and-MCP`, M3 `~/multi agentic system/multi-agentic-system` (has a Next.js UI + Stitch design), MCP `~/MCP Server 1`.
