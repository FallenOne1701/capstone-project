# Groww Support Desk — web

One page, `/`, that works by itself as an AI support desk for HDFC mutual funds on Groww.

- **Ask** by speaking or typing. The page shows what was understood, with personal details hidden.
- **Get the answer on the same page.** It's checked by the agents (facts, pattern, compliance, reviewer) against the official pages and the rules, then published automatically. If a check fails, a fixed safe reply goes out instead.
- **Listen** to the answer in English, or in Hindi for Hindi and Hinglish questions.
- **"How this was checked"** shows what the agents did.
- **Weekly pulse**:
  - top themes from Play Store reviews, real quotes, repeated questions, and the fee explainer;
  - rebuilt automatically every Monday;
  - delivered to the Google Doc, plus an **unsent** Gmail draft.

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
| `AUTO_APPROVE` | `api/.env` | Default `1`: the reviewer agent publishes passing replies and weekly deliveries. |
| `SCHEDULER_ENABLED` | `api/.env` | Turns on the schedule: weekly pulse Mon 09:00 IST, corpus refresh Sun 21:00 IST, failed-delivery retry hourly (max 6). |
| `TRUST_PROXY` | `api/.env` | Set to `1` behind a proxy (Railway) so rate limits are per visitor. |

**Google sign-in expires every 7 days.** Re-run `npm run auth` in `MCP Server 1` and update `GOOGLE_REFRESH_TOKEN`. Until you do, the page shows the delivery as "pending (retrying)" or "failed — sign-in expired".

## Tests

```bash
npm test            # vitest: labels, API client, recorder, speech helpers
npm run build       # type-check + production build
npm run e2e         # Playwright smoke tests
```

`npm run e2e` starts its own isolated stack:

- **API on :8001.** It uses a throwaway SQLite DB with `USE_LLM=0`, `AUTO_APPROVE=1` and no Google credentials. It does no corpus refresh, and `E2E_SEED=1` gives it one weekly run.
- **`next dev` on :3001.**

Before running it:
- Stop any `npm run dev` for this folder first. Next allows only one dev server per project directory.
- The first run needs `npx playwright install chromium`.
