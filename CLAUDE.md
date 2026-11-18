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

## Status (end of 2026-11-18 session)

**Branch:** `plan-3-console-voice`, 28 commits ahead of `main`. Not pushed, no PR. Head `654899e`. Working tree clean.

**Plan 3 — done:**
- voice input (Whisper, in-memory audio, silence/phantom + Urdu guards);
- clarify ("Mid Cap or Small Cap?");
- background worker;
- validated Hindi replies;
- Listen (en-IN/hi-IN);
- Playwright harness.

Its final review fixes are applied.

**Plan 3b — done:**
- **Single page `/`** with inline answers, a "How this was checked" panel and a weekly section, fed by `GET /api/weekly/summary` and `checks` on `GET /api/tickets/{code}`.
- **Auto-approval** `app/approvals/auto.py`, actor `auto-reviewer`:
  - a fixed fallback reply for blocked drafts;
  - weekly auto-delivery with hourly retry, max 6.
- **Advice and off-topic refusals** (banking, loans, cards…) with `OUT_OF_SCOPE_REPLY`.
- **Rate limits:** `app/guard/ratelimit.py`, keyed on the last X-Forwarded-For hop when `TRUST_PROXY=1`.
- **Removed:** `/console`, `/t` and `/ask` now redirect to `/`.

Final review: 0 Critical. Important 1 (MF account questions misread as banking) and Important 2 (XFF spoofing) are fixed. Important 3 (in_review tickets never auto-decided) becomes moot with the next step.

**Tests at head:**
- API 391+ passed (~8 min);
- web vitest 37 passed;
- Playwright 15 passed;
- build ok.

**Live (2026-11-18):** the user approved weekly run 5's actions #25 (Google Doc append) and #26 (Gmail draft to d***@hotmail.com, unsent). Both executed. The Google refresh token was valid that day.

### DECIDED NEXT STEP — write + build "Plan 3c: one page, a person approves"

The user read the brief and their M3 app (https://multi-agentic-system-aj1q.vercel.app: one workbench page, "Approve draft" disabled until the reviewer passes, approve creates an email draft only). Their decision: keep ONE link, but bring the human gate back on the same page. **No password**: the brief doesn't require one, so any human click counts.

Agreed design. Write it as a short amendment spec, then the plan via superpowers:writing-plans; the user reviews the plan before building.
- **Ask** section: as now (voice/text → confirm → ticket, inline answer once approved, Listen, checks panel).
- **Queue** section, the restored Plan 3 console Queue as a section:
  - each ticket's draft, citation, reviewer flags and routing note;
  - **Approve / Edit / Reject**, with Approve disabled until the reviewer passes;
  - Re-run desk for failed tickets.
- **Weekly** section:
  - themes with counts, window and review ids; quotes; repeated questions;
  - the fee explainer and the canonical explainers being reused;
  - sources with last-checked dates;
  - an approval list showing exactly what will be written and where ("Append to the weekly pulse Google Doc (id)", "Gmail draft to the product team (d***@…), not sent"), each with its own **Approve / Reject** and **Retry** on failure;
  - a "Run weekly now" button.
- **Settings:**
  - `AUTO_APPROVE` default **0**. Keep auto mode as an off-by-default switch and document it as a design choice.
  - The scheduler builds the pulse; the writes wait for a click.
- **API:** the approve / edit / reject / retry / reprocess / weekly-run / queue / sources / explainers endpoints are reachable without `X-Console-Key`, audited with actor `page`. Keep the rate limits; consider limits on the action endpoints.
- **Reuse the deleted Plan 3 UI from git history:** `web/components/console/*`, `web/app/console/*` at commit `3d7bfdf`/`c9aafc1`.

### Then Plan 4
- Evals: feasibility, edit isolation (diff state before/after), grounding/compliance with PAN / account number / phone, in both loops.
- README items listed in the brief, including a reviews CSV sample (we fetch live; export a sample, maybe add CSV ingest).
- Railway (API, one uvicorn worker, `TRUST_PROXY=1`, `SCHEDULER_ENABLED=1`) + Vercel (web). The user has a Railway account with ~30 days of credit.
- Stretch: a Google service account for the Doc append.

### Open notes
- Google OAuth app stays in Testing, so the refresh token expires every 7 days. Re-run `npm run auth` in `C:/Users/dhruv/MCP Server 1` and update `GOOGLE_REFRESH_TOKEN` before demos/Mondays.
- Known limit: the MCP Doc append is plain text, so `#` headings show literally in the Doc.
- Next 16.4.2 has a published security advisory. `next dev`/`next build` sometimes stop to show it, and rerunning works. Upgrading is the user's call (pinned to match M3); decide in Plan 4.
- Deferred minors are listed in both ledgers.

## Run it
```bash
cd api && .venv/Scripts/python -m pytest -q                       # ~8 min, offline (USE_LLM=0 in tests)
.venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000
# /api/console/* needs header X-Console-Key: <CONSOLE_PASSWORD from api/.env> (until Plan 3c opens them to the page)
# settings: AUTO_APPROVE, SCHEDULER_ENABLED, TRUST_PROXY; tests set AUTO_APPROVE=0 unless a test turns it on
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
