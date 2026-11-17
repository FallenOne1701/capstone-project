# The Support Desk — Design Spec

- **Date:** 2026-11-17
- **Due:** within one week (submission ~2026-11-24)
- **Product:** Groww — HDFC mutual fund schemes (same as Milestones 1–3)
- **Deploy target:** backend (api + Postgres) on Railway (new account); frontend (web) on Vercel

## 1. Goal and success criteria

One deployed web application that runs the support and product loop for Groww:

- **Weekly loop:** live Play Store reviews → ≤5 themes → top 3 → weekly pulse (≤250 words, quotes, 3 action ideas) + fee explainer (≤6 bullets, facts-only, 2 official links, "last checked" date) → human approval → Google Doc append + Gmail draft via MCP.
- **Response loop:** questions asked (voice or text) on a public page → three agents in parallel → orchestrator → reviewer → reply draft (≤3 sentences, one citation) + internal routing note → human approves / edits / rejects.
- **Link:** repeated questions (≥5 in 7 days) appear in the pulse; approved fee explainers become canonical answers the response loop reuses.
- **Scope enforcement in code:** facts-only, no advice, no buy/sell language, no return/performance figures, no PII anywhere (DB, logs, agent state, UI).

Success = all three required evaluations (plus intent/voice) pass on the deployed system, with recorded iteration history, and the live demo shows both links working.

### Grading rubric this design optimises for

| Criterion | Weight | Where it is addressed |
|---|---|---|
| Voice UX & intent handling | 25% | §5 |
| MCP usage & system design | 20% | §3, §7 |
| Grounding & RAG quality | 15% | §4 |
| AI evals & iteration depth | 20% | §9 |
| Workflow automation | 10% | §6 (scheduler, approvals) |
| Deployment & code quality | 10% | §10, §11 |

### Non-goals

- Sending email (drafts only; `gmail_send_email` is blocked in code).
- Reading user emails or any inbox.
- User accounts on the public page (tickets are anonymous, addressed by ticket code).
- Investment advice, recommendations, return figures — refused by design.

## 2. Inputs carried forward

| Source | Location | What is reused |
|---|---|---|
| M1 FAQ RAG | `~/OneDrive/Desktop/RAG Chat bot- Mutual Funds` (GitHub `Rag-Mutual-Funds`) | Corpus config (16 URLs), fetcher/parser/chunker, retriever, refusal + validator + PII logic |
| M2 Weekly pulse | `~/Groww-and-MCP` (GitHub `Groww-and-MCP`) | Play Store ingest + scrub, theme vocab, clustering/pulse prompts, validators, MCP bridge (stdio mode) |
| M2 MCP server | `~/MCP Server 1` (GitHub `MCP-Server-1`) | Vendored into the repo; tools `google_docs_append_content`, `gmail_create_draft` |
| M3 Agent desk | `~/multi agentic system/multi-agentic-system` (GitHub `Multi-Agentic-System`) | Facts/Pattern/Compliance agents, LangGraph orchestrator, reviewer + rewrite, contracts |

Code is **ported** (copied and adapted) into the new repo, not imported from old folders. The fee explainer did not survive in M2's code and is built new.

## 3. Architecture

Backend service + Postgres on Railway; Next.js frontend on Vercel.

```
web (Next.js)
  /ask              public · voice + text · ticket status + listen
  /console/*        shared password · queue, pulse, sources,
                    approvals, explainers, evals
        │ REST/JSON
api (FastAPI, Python 3.12)
  guard/       PII redactor, scope/output filter, caps, log filter
  voice/       Whisper STT, language detection
  intent/      rules-first intent classifier, LLM fallback
  corpus/      fetch → parse → chunk → fastembed (bge-small-en-v1.5) → Chroma
  desk/        Facts · Pattern · Compliance → orchestrator → reviewer
  weekly/      Play Store fetch → themes → pulse + fee explainer
  link/        question keys + frequency; canonical explainer lookup
  approvals/   pending actions, execute-one, audit log
  delivery/    MCP client → MCP Server 1 (stdio subprocess, Node)
  scheduler/   APScheduler: weekly loop, corpus refresh
  evals/       feasibility · edit isolation · grounding/compliance · intent/voice
        │                                  │
   Postgres                          Google Docs / Gmail (via MCP only)
```

### Repo layout

```
support-desk/
  api/
    app/            (modules above, one package each)
    mcp_server/     (vendored MCP-Server-1, built in Docker image)
    data/corpus/    (fetched pages + Chroma index; rebuilt on refresh)
    evals/datasets/ (questions, adversarial set, voice clips, labels)
    tests/
    Dockerfile
  web/
  docs/
  EVALS.md
```

### LLM providers

- **Groq** `openai/gpt-oss-120b` (generation), `openai/gpt-oss-20b` (fast classification), `whisper-large-v3-turbo` (STT; free tier verified, 2000 req/day).
- **Gemini** as fallback for generation (M2/M3 already support it).
- Existing Groq free-tier rate limiter from M2 is reused.

## 4. Corpus and grounding

- **Corpus:** all 16 M1 URLs — 15 HDFC scheme pages on groww.in plus `groww.in/p/mutual-funds`.
- **Fee pages (conditional):** if the general page does not explain exit load and expense ratio as concepts, add 2–3 public official pages (Groww charges/pricing page; AMFI and/or SEBI investor-education pages on exit load / expense ratio). Never third-party blogs. Decided during build after inspecting the general page.
- **Freshness:** scheduled refresh (weekly) + manual "Refresh" button. Each source stores `url`, `title`, `fetched_at` (= last checked), `content_hash`, `status`. Index is rebuilt when any hash changes.
- **Retrieval:** same chunking as M1 (one section → one chunk, split >400 tokens), `bge-small-en-v1.5` via fastembed (ONNX, no PyTorch), Chroma persisted in the api container. Scheme filter from the question, top-k 3.
- **Citations:** every factual sentence in a reply, explainer bullet or pulse fact carries exactly one corpus URL; pulse quotes and counts carry review ids. Enforced by validators, not prompts.
- **Not covered:** when retrieval confidence is below threshold or no section matches, the reply is "Not covered — searched: <scheme pages / sections searched>".
- **M3 Facts agent** is rewired to query this corpus instead of its own 5-scheme dataset.

## 5. Voice and intent handling

### Public `/ask` page

1. **Speak or type.** Mic button records up to 60 s in the browser (MediaRecorder). Audio is POSTed to `api`, transcribed by Whisper, and discarded — held in memory only, never written to disk, logs or DB.
2. **Confirm.** The redacted transcript and detected intent are shown, e.g. *"What is the exit load on HDFC mid cap?" → Fee question · HDFC Mid Cap*. The user can edit, re-record or submit. Ambiguous scheme → one clarifying question ("HDFC Mid Cap or HDFC Small Cap?").
3. **Ticket.** On submit the user gets a ticket code and a status page. Status: *received → in review → answered*. For advice/performance intents the page immediately shows a static scope notice (fixed UI copy, not a reply: "We share facts only and can't advise on buying, selling or returns"); the ticket's refusal reply still goes through approval like any other.
4. **Listen.** Once approved, the status page shows the reply with a 🔊 button using browser `speechSynthesis`, voice `en-IN` or `hi-IN` matching the question language. Hindi/Hinglish questions get Hindi replies; facts and citations unchanged.
5. **Fallbacks.** Typing always available; mic-permission-denied guidance; STT failure → "Couldn't hear that — try again or type"; clips under ~1 s or silent are rejected.

### Intent taxonomy (rules first, LLM for the gray zone)

| Intent | Handling |
|---|---|
| `fee_question` | Canonical explainer check → else agent desk |
| `fund_fact` | Agent desk, cited answer |
| `how_to_process` | Agent desk; not covered if outside corpus |
| `advice_request` | Refused: facts-only template + link to scheme facts |
| `performance_request` | Refused: no figures, points to official scheme page |
| `account_issue` | Routing note to support; user told to use official support channels |
| `out_of_scope` | Not covered — searched: … |

Refusal replies are fixed templates (no LLM), but like every reply they are published to the ticket only after a human approves them.

## 6. The two loops and the link

### Weekly loop (scheduler, weekly; or "Run now")

1. **Fetch** last 8 weeks of reviews from the public Play Store listing (`google-play-scraper`). Drop author name, avatar, reply fields at fetch time; run PII redactor on text. Stored: `review_id, rating, date, text_redacted, app_version`.
2. **Theme** into ≤5 themes using M2 vocab + LLM labelling. Each theme: `id, label, count, review_ids[], window_start, window_end`. Top 3 by count.
3. **Merge** response-loop data: question keys with ≥5 occurrences in the last 7 days.
4. **Generate**
   - **Pulse:** ≤250 words — top 3 themes with counts + windows, supporting quotes (each with review id), "Asked repeatedly this week" section, 3 action ideas.
   - **Fee explainer:** for the most frequent fee/charge confusion found in reviews and questions — ≤6 bullets, each citing one corpus URL, at least two distinct official URLs overall, "Last checked: <date>".
5. **Validate** caps, citations, scope filter. On failure regenerate once; then mark run `failed` with reasons.
6. **Queue** two pending actions: `doc_append` (pulse + explainer) and `email_draft`. Run status `awaiting_approval`.

### Response loop (per ticket)

1. Ingress: redact → intent → (refusal template | canonical check | desk).
2. **Canonical check:** if intent is `fee_question` and an approved canonical explainer exists for the topic, compose the reply from its bullets (≤3 sentences, its citation) and label it `reused: explainer #N`.
3. **Desk:** Facts (corpus), Pattern (theme/frequency signal), Compliance run in parallel (LangGraph) → orchestrator merges → reviewer checks advice / performance / PII / citation / shape → one rewrite if needed.
4. Output: reply draft + citation + routing note (team, priority, why). Draft enters the console queue as a pending `reply_publish` action.

### Link 1 — repeated questions → pulse

Each ticket gets a **question key**: `<intent>:<topic>[:<scheme>]`, e.g. `fee_question:exit_load:hdfc_mid_cap`, built from intent + corpus section match + scheme match (deterministic, no LLM). The pulse includes every key with ≥5 tickets in the trailing 7-day window, with count, window and ticket ids.

### Link 2 — approved explainer → canonical answer

Approving a fee explainer's `doc_append` action marks the explainer `canonical` for its topic (e.g. `exit_load`), superseding any previous canonical for that topic. The response loop reuses it as above; reuse is still reviewed and still needs approval. Console shows each explainer's reuse count.

## 7. Approvals and MCP delivery

- **Pending action** record: `id, type (doc_append | email_draft | reply_publish), status (pending | approved | rejected | executed | failed), target (human-readable + id), content (exact, redacted), source_ref, created_at, decided_at`.
- **Approve** executes exactly that action and nothing else. **Edit** (reply drafts) replaces that draft's content only, re-runs the reviewer on the edited text, and logs the edit. **Reject** changes only that action's status.
- **Audit log** (append-only): every create / edit / approve / reject / execute / fail, with actor and timestamp.
- **MCP client** (ported from M2 `mcp_bridge`, stdio mode) spawns the vendored MCP Server 1 (`node dist/server.js`) with `DOTENV_CONFIG_QUIET=true`. Tools used: `google_docs_append_content`, `gmail_create_draft`. `gmail_send_email` is denylisted in code.
- **Failure:** action → `failed` with error text; console offers Retry. No silent retries.
- **Google auth:** refresh token supplied via env var on Railway; OAuth app must be in "In production" status to avoid 7-day expiry.

## 8. Scope enforcement (`guard/`)

- **Input redactor** on every ingress (typed question, transcript, review text, console edit) before storage, logging or agent calls. Patterns with validation: PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), Aadhaar (12 digits, Verhoeff), bank account (9–18 digits in account context), IFSC, Indian phone (+91 / 10-digit starting 6–9), email, UPI ID. Replaced with `[PAN]`, `[ACCOUNT]`, `[PHONE]`, etc. Raw text is never persisted.
- **Log filter** on the root logger applies the same redaction to every record (defence in depth).
- **Output filter** on every reply, pulse and explainer: advice / buy-sell language, return or performance figures (percent near return words, CAGR, "gave/returned X%", forecasts), residual PII. Fee percentages (exit load, expense ratio, stamp duty) are allowed — distinguished by surrounding vocabulary. Failure → one rewrite → else `blocked` with reason, visible in console.
- **Hard caps:** reply ≤3 sentences; pulse ≤250 words; explainer ≤6 bullets; each factual sentence has one citation.
- **Agent state:** LangGraph state only ever receives redacted text; checkpointing disabled or stored redacted.

## 9. Evaluations (`api/evals/`)

Runnable via CLI (`python -m app.evals run [suite]`) and a console button. Each run stored in `eval_runs` with code version, per-case results and summary.

1. **Feasibility** — ~40-question set (covered, uncovered, fee, Hinglish): each yields a draft or explicit not-covered. Every theme has review ids + window. Pulse ≤250 words; explainer ≤6 bullets. A triggered weekly run completes with no manual step.
2. **Edit isolation** — snapshot DB → perform one operation (edit draft, approve action, reject draft) → snapshot → diff. Pass only if exactly the expected rows changed (target row + one audit row; approve-doc does not create/execute the email action, etc.).
3. **Grounding & compliance** — sample 15 claims across replies, pulse and explainer; each must trace to a corpus URL or review id. Out-of-corpus questions must return not-covered naming what was searched. Adversarial set run through **both loops** (as tickets, including voice clips; and as injected fake reviews): advice requests, return-figure requests, messages containing a PAN, an account number and a phone number — rephrased and repeated. Every case refused or redacted. Then grep logs, DB dump and agent state for the original sensitive strings; any hit fails.
4. **Intent & voice** — intent accuracy on a labelled set; transcription spot-check on a few recorded English and Hinglish clips.

**Iteration:** every run is versioned; console Evals page shows history (e.g. v1 31/40 → v3 40/40). `EVALS.md` records each failure found, the fix, and the re-run result.

## 10. Deployment

- **api:** Dockerfile — Python 3.12 + Node 22 (for MCP subprocess); builds vendored MCP server; fastembed model downloaded at build time.
- **web:** Next.js on **Vercel** (env `NEXT_PUBLIC_API_URL` = Railway api URL; api CORS allows the Vercel domain).
- **Postgres:** Railway plugin.
- **Secrets** only as Railway variables: `GROQ_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `PULSE_DOC_ID`, `PULSE_DRAFT_RECIPIENT`, `CONSOLE_PASSWORD`, `DATABASE_URL`.
- **Health:** `/health` checks DB, Chroma index loaded, MCP handshake.
- Chroma index and corpus are rebuilt on boot if missing (container disk is ephemeral).

## 11. Testing

- pytest unit tests, written test-first, for `guard/` (each PII type, fee-vs-return percentages), intent rules, caps, question keys, canonical lookup, approval state transitions.
- Evals double as integration tests against a test database.
- Playwright smoke tests: `/ask` text submit → ticket; console approve → ticket shows answer.

## 12. Error handling

- LLM provider errors: retry with backoff (existing M2 helper), then fall back Groq → Gemini; if both fail the ticket/run is marked `failed` and shown in console.
- Play Store fetch failure: weekly run fails visibly; previous run's results remain.
- Corpus fetch failure for a page: keep previous version, mark source `stale` with its old last-checked date.
- MCP failure: action `failed` + Retry (§7).

## 13. Timeline

| Day | Work |
|---|---|
| 1 | Repo scaffold, `guard/`, corpus port + refresh, Postgres schema |
| 2 | Desk port (agents rewired to corpus), response loop, intents |
| 3 | Weekly loop, fee explainer, link 1 + link 2 |
| 4 | Approvals, MCP delivery, console UI |
| 5 | Voice + `/ask`, Railway deployment |
| 6 | Evals, iterate to green, `EVALS.md`, README, demo script |

## 14. Open decisions (resolved during build)

- Whether to add the 2–3 fee pages (§4) — decided after inspecting `groww.in/p/mutual-funds`.
- New Railway account login — user runs `railway login` with the new account before Day 5.
