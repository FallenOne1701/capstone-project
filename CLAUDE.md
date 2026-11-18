# Groww Support Desk — capstone (Milestone 4)

Final project: one deployed system for Groww (HDFC mutual funds) with a **response loop** (questions → cited, compliance-checked reply drafts) and a **weekly loop** (Play Store reviews → themes → pulse + fee explainer), linked, with nothing written or sent without human approval. Due ~2026-11-24. Graded on: Voice UX & intent 25%, MCP usage & design 20%, Grounding/RAG 15%, AI evals & iteration 20%, Workflow automation 10%, Deployment & code quality 10%.

## Where things are
- Spec: `docs/superpowers/specs/2026-11-17-support-desk-design.md` (binding authority)
- Plans: `docs/superpowers/plans/` — Plan 1 (API foundation + response loop, merged as PR #1), Plan 2 (weekly loop + links + Google delivery, branch `plan-2-weekly-loop`), Plan 3 (console UI, voice), Plan 4 (evals, Railway + Vercel deploy). Plan 1 ledger: `docs/superpowers/plans/2026-11-17-plan-1-ledger.md`.
- Live execution ledger for the current plan: `.superpowers/sdd/<plan>/progress.md` (git-ignored; read it first when resuming).
- GitHub: private `FallenOne1701/capstone-project`. Each plan = its own branch + PR.

## Status (2026-11-18)
- Plans 1–2 merged. Plan 3 (voice, Hindi replies, worker) + Plan 3b (single page, auto-approval) built on branch `plan-3-console-voice`, not pushed. Ledgers: `.superpowers/sdd/2026-11-17-plan-3-console-and-voice/`, `.superpowers/sdd/2026-11-18-plan-3b-single-page-autonomous/`.
- Product decision (user, 2026-11-18): ONE public page `/`, no console page, no human approval. The reviewer agent (actor `auto-reviewer`) approves passing replies and the weekly Doc/Gmail-draft delivery; blocked drafts get a fixed fallback; advice and off-topic (banking, loans, cards…) are refused with fixed replies. Design: `docs/superpowers/specs/2026-11-18-single-page-autonomous-desk-design.md`.
- Google OAuth app stays in Testing → refresh token expires every 7 days: re-run `npm run auth` in `C:/Users/dhruv/MCP Server 1` and update `GOOGLE_REFRESH_TOKEN` before demos/Mondays (user chose this over a service account; service account = stretch goal after Plan 4). The page shows delivery as "pending (retrying)" / "failed — sign-in expired".
- Known limit: the MCP Doc append is plain text, so `#` headings show literally in the Doc.
- Next: Plan 4 (evals, Railway + Vercel deploy; set TRUST_PROXY=1, SCHEDULER_ENABLED=1, one uvicorn worker).

## Run it
```bash
cd api && .venv/Scripts/python -m pytest -q                       # ~6 min, offline (USE_LLM=0 in tests)
.venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000
# /api/console/* (unlinked, for operators/tests) needs header X-Console-Key: <CONSOLE_PASSWORD from api/.env>
# settings: AUTO_APPROVE (default 1), SCHEDULER_ENABLED, TRUST_PROXY; tests set AUTO_APPROVE=0 unless a test turns it on
.venv/Scripts/python scripts/verify_weekly.py --log ../.superpowers/server.log

cd web && npm run dev          # the single page on :3000 (NEXT_PUBLIC_API_URL in web/.env.local)
npm test && npm run build && npm run e2e   # vitest, build, Playwright (own API :8001 + web :3001, e2e DB, no LLM/Google)
```
- Next 16.4.2 sometimes prints a security advisory and exits 1 on `next dev`/`next build` in agent sessions; rerunning works. Upgrading Next is the user's call (pinned to match M3).
`api/mcp_server/` is MCP Server 1 vendored (build: `npm ci && npm run build`); `api/.env` holds keys (never commit).

## Working rules
- User reviews each plan; execution is Native (inline) + one fresh reviewer at the end; TDD for every change; rulings go in the ledger.
- Never approve Google writes or push/merge without the user's explicit instruction.
- Earlier milestones (reference only): M1 `~/OneDrive/Desktop/RAG Chat bot- Mutual Funds`, M2 `~/Groww-and-MCP`, M3 `~/multi agentic system/multi-agentic-system` (has a Next.js UI + Stitch design), MCP `~/MCP Server 1`.
