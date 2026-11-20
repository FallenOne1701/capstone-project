# Groww Support Desk — web

One page, `/`, for an AI support desk for HDFC mutual funds on Groww. Agents draft and check every reply and every weekly Google write, and **a person on the same page approves each one**. Nothing is published or written until they do.

The page has three tabs: **Ask | This week | Queue**. Switching tabs never loses what you typed or opened, and the address keeps the tab (`/?tab=week`, `/?tab=queue`) and the open ticket (`/?t=GRW-XXXXXX`), so a link or a reload opens the same view.

- **Ask** (two columns):
  - Left: speak or type the question. Continue shows what was understood, with personal details hidden, under the box.
  - Right: "How it works" with three example questions to try. After Send, the ticket with its 4 steps: Received → Checked → Waiting for a person → Answered. While a person reviews it, the asker sees "Waiting for a person to approve this answer." A rejected question shows "We couldn't answer this one." with **Ask again**.
  - **Listen** reads the answer in English, or in Hindi for Hindi and Hinglish questions. **"How this was checked"** shows what the agents did.
- **This week** (shows a dot when a Google write waits for a person):
  - top themes from Play Store reviews, real quotes, repeated questions, and the fee explainer; rebuilt automatically every Monday;
  - **Run weekly now** (at most once an hour);
  - "Waiting for your approval": each card states exactly what is written where ("Append to the weekly pulse Google Doc (id)", "Gmail draft to the product team (d***@…), not sent") and shows the exact text. Each has its own Approve / Reject, plus Retry if it failed;
  - **Fee explainers** (canonical ones are reused in replies) and **Sources** with last-checked dates, open by default.
- **Queue** (the badge counts tickets waiting for a person): filters **Waiting / Answered / Closed**; every draft with its source, the reviewer's flags and the routing note. **Approve** stays off until the reviewer passes it. **Edit** re-runs the reviewer, **Reject** closes the ticket, and **Re-run desk** retries failed tickets.

Advice, returns and off-topic questions (banking, loans, cards, insurance, …) are never answered. They get a fixed facts-only reply.

Old links still work: `/ask` and `/t/<code>` both open the main page.

## Run locally

```bash
# 1. API (port 8000) — needs api/.env
cd ../api && .venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000

# 2. Web (port 3000)
cd web
npm ci
cp .env.example .env.local        # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000.

Browsers allow the microphone only on `https://` or `http://localhost`. On other plain-http addresses, the page shows a typing hint instead of the mic button.

## Environment

| Variable | Where | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `web/.env.local` | Base URL of the API (default `http://localhost:8000`). |
| `AUTO_APPROVE` | `api/.env` | Default `0`: a person approves every reply and Google write on the page. `1` is an optional unattended mode: the reviewer agent publishes passing replies (a fixed safe reply when blocked) and delivers the weekly writes itself, with hourly retries. |
| `SCHEDULER_ENABLED` | `api/.env` | Turns on the schedule: weekly pulse Mon 09:00 IST, corpus refresh Sun 21:00 IST, failed-delivery retry hourly (max 6). |
| `TRUST_PROXY` | `api/.env` | Set to `1` behind a proxy (Railway) so rate limits are per visitor. |

**Google sign-in expires every 7 days.** Re-run `npm run auth` in `MCP Server 1` and update `GOOGLE_REFRESH_TOKEN`. Until you do, the page shows the delivery as "pending (retrying)" or "failed — sign-in expired".

## Tests

```bash
npm test            # vitest: labels, tab/queue rules, API client, recorder, speech helpers
npm run build       # type-check + production build
npm run e2e         # Playwright smoke tests
```

`npm run e2e` starts its own isolated stack:

- **API on :8001.** It uses a throwaway SQLite DB with `USE_LLM=0`, `AUTO_APPROVE=0` (tests approve through the page's desk API) and no Google credentials. It does no corpus refresh, and `E2E_SEED=1` gives it one weekly run. `TRUST_PROXY=1` lets test helpers act as separate visitors, so setup calls don't use up the browser's ask limit.
- **`next dev` on :3001.**

Before running it:
- Stop any `npm run dev` for this folder first. Next allows only one dev server per project directory.
- The first run needs `npx playwright install chromium`.

## Deployed

- **Page (Vercel):** https://groww-support-desk.vercel.app — project rooted at `web/`, `NEXT_PUBLIC_API_URL` set for Production (Next bakes it in at build time, so change it and redeploy).
- **API (Railway):** https://api-production-c6d78bb8.up.railway.app — built from `api/Dockerfile` (Python 3.12 + Node 22 for the Google MCP tool + the embedding model baked in), one uvicorn worker. `/health` reports `db`, `corpus` and `google` readiness (names of missing settings only).
- **Storage:** SQLite on a Railway volume at `/data` (database, scraped corpus, search index, outbox). A deliberate choice over Postgres: the app runs as one process with one scheduler, every test runs on SQLite, and the volume survives redeploys.
- **Railway variables (names):** `GROQ_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_MODEL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `PULSE_DOC_ID`, `PULSE_DRAFT_RECIPIENT`, `CONSOLE_PASSWORD`, `AUTO_APPROVE=0`, `SCHEDULER_ENABLED=1`, `TRUST_PROXY=1`, `USE_LLM=1`, `DATABASE_URL=sqlite:////data/app.db`, `DATA_RAW_DIR`/`DATA_PROCESSED_DIR`/`DATA_INDEX_DIR`/`DATA_OUTBOX_DIR` under `/data`, `CORS_ORIGINS=https://groww-support-desk.vercel.app,http://localhost:3000`.
- **Redeploy:** API — `railway up --detach --service api` from `api/` (`.railwayignore` keeps `.env`, data and tests out of the upload). Page — `npx vercel deploy --prod` from `web/` (a build can fail once fetching Google Fonts; a plain retry works).
