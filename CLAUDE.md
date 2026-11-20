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

## Status (2026-11-20, Plan 5 merged + live: RESUME HERE)

**Merged to `main`:** Plans 1-5 (PR #4 `4f9a216` = the deploy; PR #5 `da11a9d` = evals + README; PR #6 `f1a155a` = tab layout). Spec/plan for 4b: `docs/superpowers/specs/2026-11-19-evals-and-readme-design.md`, `docs/superpowers/plans/2026-11-19-plan-4b-evals-readme.md`.
Done 2026-11-19 night: after the PC restart Groq connects (5/5); PR #5 merged; API redeployed on Railway (deployment `8c9ae937`, SUCCESS, `/health` all ready). The page needed no redeploy.

**Plan 5 (tab layout, 2026-11-20) merged (PR #6) and live on Vercel (checked: tabs, `?tab=queue`, old ticket link).** Spec `docs/superpowers/specs/2026-11-20-tab-layout-design.md`, plan `docs/superpowers/plans/2026-11-20-plan-5-tab-layout.md`, ledger `.superpowers/sdd/2026-11-20-plan-5-tab-layout/progress.md` (Rulings). Tabs Ask | This week | Queue (user's order); `?tab=week|queue`, `?t=CODE`; all tabs stay mounted (`components/desk/DeskTabs.tsx`); rules in `web/lib/desk.ts`. Stitch design: `C:/Users/dhruv/Downloads/stitch_hdfc_mutual_funds_support_desk/`.

**2026-11-20 later:** the loop link was shown live (5 brokerage questions → "Reused canonical explainer #4", reuse 5; weekly run 5 pulse "Asked repeatedly: Brokerage & charges 5" + "71 reviews and 5 questions"; user approved run 5's Doc append + Gmail draft). Fix PR #7 (merged, API redeployed): a reused explainer adds the same page's figure line unless the question is a pure definition. GRW-567CN9 (the fixed answer) left pending in the Queue for the user's demo. README "The link in action" + `docs/samples/weekly_delivery.md` = run 5 (branch `docs-link-demo`).

**Next steps, in order:**
1. Optional before the 24th: Google OAuth app to "In production" (refresh token stops expiring); a demo run-through.
2. Plan 5 deferred minors (in its ledger): Queue filter chips need arrow keys; tab aria-label names the panel incl. the count; header chip always says a person approves (even if AUTO_APPROVE=1); RunWeeklyButton interval depends on onRunDone identity.

**Plan 4b results** (`api/EVALS.md` has runs 1-7): run 7 = feasibility 44/45, isolation 5/5, grounding 55/55, intent 41/41; the only miss is a Devanagari-script question (known limitation). Run: `cd api && .venv/Scripts/python -m app.evals run all` (~2.5 min, ~30 Groq calls; results in `api/evals/results/`). Root `README.md` has the eval table; `docs/samples/` has the reviews CSV, 5 Q&As, and the real weekly Doc entry + Gmail draft (live run 3, approved by the user 2026-11-19 15:47 UTC).
Product fixes found by evals: off-topic checked before how-to (bitcoin); the AI names the fact for unclear wording and retrieval uses it; a fee question with no named fee asks the AI which fee, but named other fees (stamp duty, brokerage, GST...) never borrow a fact; the AI can't call a named HDFC fund out of scope; more advice phrasings are rules.
Deferred minors (4b): repeat:2 double-counts grounding cases (noted in EVALS.md); the generic "Searched: all 15..." reply passes the names-what-was-searched check; a suite crash loses earlier suites' results; extra AI call on unnamed-fee questions; "how do I sell and get money in my bank account" is now out_of_scope; leak scan matches whole tokens only; a weekly run never moves to status `done` after both writes execute (display unaffected).

**Tests at head:** API 479 passed, 5 skipped (~8 min); web vitest 65, Playwright 37. The two voice e2e tests are flaky on this PC (fake mic sometimes judged silent; also on the pre-Plan-5 commit).

**Live:**
- Page: https://groww-support-desk.vercel.app (Vercel, user's Gmail/GitHub account `fallenone1701`, team `bomba8`).
- API: https://api-production-c6d78bb8.up.railway.app (Railway project `groww-support-desk`, service `api`, the user's SECOND Railway account; the CLI is logged in to it).
- SQLite on the Railway volume `/data` (user chose this over Postgres). `CORS_ORIGINS` = the Vercel address + localhost. `/health` shows db / corpus / google readiness.
- Live checks 2026-11-19: GRW-9WYGL7 approved and answered (0.73%, cited); weekly run 3 on Railway, Doc append + Gmail draft approved by the user and executed.
- Redeploy steps are in `web/README.md` → "Deployed".
- User decision 2026-11-19: no password on the page. Approvals (including Google writes) stay open to anyone on the page; Google writes only append to the Doc or create a Gmail draft, never send.

**What Plan 3c built** (still true): `AUTO_APPROVE` default 0; open page API `/api/desk/*` (actor `page`, rate-limited, approve must send the reply text seen, else 409); ticket `closed` on reject + "Ask again"; weekly approvals show exactly what is written where; Google errors in plain words. Deferred minors from 3c: no length cap on edit text; Retry after a Google timeout may double-write; a daily cap on open weekly runs; the `models.py` status comment.

### Open notes
- **2026-11-19: this PC ran out of network ports** (~18.5k stuck TIME_WAIT connections after 30 days without a real restart; Windows fast startup is on, so only Start > Restart clears it). Symptom: `APIConnectionError` / curl "Address already in use" to Groq while other sites work. Fix = Restart. Gemini's free daily quota (429) was also used up that day.
- Google OAuth app stays in Testing, so the refresh token expires every 7 days. Re-run `npm run auth` in `C:/Users/dhruv/MCP Server 1` and update `GOOGLE_REFRESH_TOKEN` in `api/.env` AND on Railway (`railway variable set GOOGLE_REFRESH_TOKEN --stdin --service api` from `api/`) before demos/Mondays — or switch the OAuth app to "In production".
- Known limit: the MCP Doc append is plain text, so `#` headings show literally in the Doc.
- Next upgraded 16.4.2 → 16.4.6 on 2026-11-20 (npm audit: 0 vulnerabilities; the security notice that stopped `next dev`/`build` is gone).
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
