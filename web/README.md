# Groww Support Desk — web

The Next.js app for the support desk:

- **`/ask`** is the public page. People speak or type a question, check what was understood (personal details hidden), then follow the ticket at `/t/<code>` and listen to the approved answer in English or Hindi.
- **`/console`** is the password-protected staff console: Queue, Pulse, Approvals, Explainers and Sources. Nothing is published or written to Google without an Approve click.

All data comes from the FastAPI service in `../api` over REST.

## Run locally

```bash
# 1. API (port 8000) — see ../api, needs api/.env
cd ../api && .venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000

# 2. Web (port 3000)
cd web
npm ci
cp .env.example .env.local        # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Then open:
- http://localhost:3000/ask
- http://localhost:3000/console, signing in with `CONSOLE_PASSWORD` from `api/.env`

**Microphone access.** Browsers only allow the microphone on `https://` or `http://localhost`. On any other plain-http address, the mic button is replaced by a typing hint.

## Environment

| Variable | Where | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `web/.env.local` | Base URL of the API (default `http://localhost:8000`) |
| `CONSOLE_PASSWORD` | `api/.env` | Shared console password, sent as `X-Console-Key`. It is kept in `sessionStorage` for the tab only. |

## Tests

```bash
npm test            # vitest: labels, API client, recorder, speech helpers
npm run build       # type-check + production build
npm run e2e         # Playwright smoke tests
```

`npm run e2e` starts its own isolated stack, so it never touches your real data:

- **API on :8001.** It uses a throwaway SQLite file at `api/data/e2e/`, with `USE_LLM=0` and no Google credentials. Its corpus is never refreshed, and its sample data comes from `E2E_SEED=1` (one weekly run built from fixture reviews).
- **`next dev` on :3001.** The browser tests run here.

Chromium runs with a fake microphone. The first run needs `npx playwright install chromium`.

Stop any `npm run dev` for this folder first: Next allows only one dev server per project directory.
