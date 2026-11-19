# Plan 4a — Deploy: Railway (API) + Vercel (page)

Amends §10 of `2026-11-17-support-desk-design.md`. Approved by the user 2026-11-19.

## Intent
The brief needs **one deployed link**. Deploy first (before evals) because it is where the surprises are
(Python + Node + the embedding model in one container), so finding them early leaves days to fix them, and the
evals in Plan 4b can then run against the real system.

## Goals
- The API runs on Railway (the user's second Railway account, already logged in on the CLI).
- The single page runs on Vercel (the user's Gmail account; the user runs `! npx vercel login` once).
- Live check passes: the link opens; a question asked there waits for a person, is approved on the page and
  shows the answer; the weekly section loads.

## Non-goals
Evals, README, the Google OAuth "In production" switch (guided separately), Postgres, more than one server.

## Anti-goals
- A key in git, in a log, or printed on screen. Keys go from `api/.env` into Railway variables by a command the
  user approves; values are never echoed.
- Any Google write approved during the live check without the user's explicit say-so.
- Changing behaviour that the existing tests pin (local dev and tests must keep working unchanged).

## Approaches (database) — user picked A on my recommendation
- **A. SQLite on a Railway volume (chosen).** Every test runs on SQLite; the API already runs as one process
  (one scheduler); the volume survives redeploys and also keeps the Chroma index and corpus. Lowest risk 5 days
  before the deadline. The README records this as a deliberate choice.
- B. Railway Postgres (the original spec). New driver path and dialect differences that the tests never exercise;
  only worth it for several servers or heavy traffic.

## Decided
- **API container:** Dockerfile in `api/`: Python 3.12 + Node 22; installs the package; builds the vendored MCP
  server (`npm ci && npm run build`); downloads the fastembed model at build time. One uvicorn worker on `$PORT`.
- **Railway variables:** the keys from `api/.env` plus `AUTO_APPROVE=0`, `SCHEDULER_ENABLED=1`,
  `TRUST_PROXY=1`, `USE_LLM=1`, and the database/corpus/outbox paths pointed at the volume (mounted at `/data`).
- **CORS:** a new `CORS_ORIGINS` setting (comma list). Default stays `*` so local dev and tests are unchanged;
  Railway sets it to the Vercel address plus `http://localhost:3000`.
- **Health:** `/health` keeps db + corpus, and adds whether the Google tool is ready (node present, MCP build
  present, Google keys set) — a cheap check, not a live Google call, because Railway polls it.
- **Vercel:** project rooted at `web/`, `NEXT_PUBLIC_API_URL` = the Railway public URL.

## Left to the builder
Exact Dockerfile layout and caching, the Railway service/volume names, the health-check wiring in Railway, and
whether the first corpus build happens at boot (existing bootstrap) or at build time.
