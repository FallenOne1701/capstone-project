# Groww Support Desk

One deployed web app for questions about **HDFC mutual funds on Groww**, with two linked loops. **Nothing is published,
written or sent without a person approving that exact action.**

**Live:** https://groww-support-desk.vercel.app  ·  API: https://api-production-c6d78bb8.up.railway.app/health

- **Response loop** — a question (typed or spoken, in English or Hinglish; replies can also be shown in Hindi) becomes a cited, compliance-checked
  draft reply. A person approves, edits or rejects it on the page; only then does the asker see it.
- **Weekly loop** — every Monday, public Play Store reviews become themes, a ≤250-word pulse and a fee explainer.
  A person approves the Google Doc append and the Gmail draft, each shown with exactly what will be written where.

## How it works

```
question ─► redact PII ─► intent (rules, AI for unclear wording) ─► desk agents
            (PAN, account, phone, email, card, Aadhaar…)          ├─ Facts: retrieval over 15 HDFC scheme pages + fee references
                                                                  ├─ Pattern: this week's review themes
                                                                  └─ Compliance: no advice, no return figures, ≤3 sentences, one citation
          ─► reviewer (blocks advice/returns/uncited facts) ─► queue ─► a person approves ─► asker sees answer

Play Store reviews ─► redact ─► themes (AI, with keyword fallback) ─► pulse + fee explainer
          ─► pending actions: Doc append, Gmail draft ─► a person approves ─► MCP Server 1 (stdio) ─► Google
```

- **The links between the loops:** the desk uses the week's review themes to route tickets, and an approved fee
  explainer becomes the canonical answer that later fee tickets reuse.
- **MCP:** the API runs our MCP server (`api/mcp_server/`, vendored from Milestone 3) as a stdio subprocess and calls
  only `google_docs_append_content` and `gmail_create_draft`; `gmail_send_email` is denylisted, so mail is only ever a
  draft. Each call runs only after a person approves that action; failures show in plain words with a Retry.
- **Grounding:** one section of a scheme page → one chunk, `bge-small-en-v1.5` embeddings in Chroma. A reply states
  one fact with its source URL and "Last checked" date, or says "not covered" and names what it searched.
- **Compliance:** advice and return/performance requests get fixed refusals; personal data is redacted before
  anything is stored, logged or sent to an AI model; a log filter redacts every log line again.
- **The approval gate** (`AUTO_APPROVE=0`): every reply and Google write is a pending action; approve / edit / reject
  are audited, and approve publishes only the exact text the person saw.

## Evals — latest run

Run 7 (2026-11-19), real AI, file [`api/evals/results/run-7-2026-11-19.json`](api/evals/results/run-7-2026-11-19.json):

| Eval | Score | What it checks |
|---|---|---|
| Feasibility | **44/45** | 41 questions each end with a cited answer, a not-covered naming what was searched, or the right refusal; the weekly run completes on its own with themes (review ids + window), pulse ≤250 words, explainer ≤6 bullets |
| Edit isolation | **5/5** | one edit / approve / reject changes exactly the expected rows across every table; approving the Doc never touches the email |
| Grounding & compliance | **55/55** | advice and return requests refused; synthetic PAN / account / phone numbers redacted in **both loops** (tickets and fake reviews); 15 sampled claims are found on the cited official page or in the cited review; nothing sensitive in logs, database or outbox |
| Intent (sub-score) | **41/41** | the question type the desk chose |

Iteration: run 1 scored 30/44 · 5/5 · 37/45; a code review then made the checks stricter; the fixes in between are in the history. The one remaining failure is a
question in Devanagari script (a known limitation).

Full history — every failure, its cause, the fix and the re-run: [`api/EVALS.md`](api/EVALS.md).
Run them: `cd api && .venv/Scripts/python -m app.evals run all`.

## Samples

- Reviews CSV (20 public Play Store reviews, redacted the way the weekly loop stores them): [`docs/samples/reviews_sample.csv`](docs/samples/reviews_sample.csv)
- 5 sample Q&As from the latest eval run: [`docs/samples/sample_qa.md`](docs/samples/sample_qa.md)
- Weekly delivery example (the appended Doc entry and the Gmail draft): [`docs/samples/weekly_delivery.md`](docs/samples/weekly_delivery.md)

### Weekly delivery example

From the live site on 2026-11-20 (weekly run 5): 3,042 Play Store reviews (28 Oct – 20 Nov) → 3 themes, 3 verbatim quotes with review ids, the questions asked repeatedly on the desk, 3 action ideas and a brokerage & charges explainer citing Groww's help pages. A person approved both writes on the page; the Doc append and the Gmail draft (to the product team, **not sent**) then ran through MCP. Full text, exactly as written: [`docs/samples/weekly_delivery.md`](docs/samples/weekly_delivery.md).

### The link in action

Shown on the live site on 2026-11-20. Both directions of the link between the two loops:

**Weekly loop → response loop: the explainer becomes the canonical answer.** The weekly run found brokerage & charges to be the fee users were most confused about, drafted a facts-only explainer from Groww's help pages, and a person approved it (with the Doc append), which made it canonical. Five differently worded questions then came in:

| Ticket | Question |
|---|---|
| GRW-F8CC2W | What brokerage does Groww charge? |
| GRW-TJNBTW | How much brokerage does Groww take on a trade? |
| GRW-T7Q98D | Is there a brokerage fee on Groww? |
| GRW-7PUZJH | what are groww brokerage charges |
| GRW-YJ62U4 | Brokerage on Groww for equity delivery? |

Each draft was built from the approved explainer instead of being written fresh. Its routing note reads *"Reused canonical explainer #4 (brokerage)."*; each passed the reviewer and a person approved it. The page's **Fee explainers** section shows that explainer reused in 5 replies.

**Response loop → weekly loop: a question asked 5 times shows up in the pulse.** The five questions share one key (*Fee question · Brokerage & charges*), so the next weekly run (run 5) carried them into the pulse that was appended to the Doc and drafted to the product team:

```
## Asked repeatedly (2026-11-13 to 2026-11-20)
- Fee question · Brokerage & charges: 5 questions

## Fee confusion
- Brokerage & charges: 71 reviews and 5 questions → explainer below.
```

The run before it (no repeated questions yet) said "0 questions". Product now sees *which* fee is confusing, how often support is asked about it, and the exact answer support gives.

**Iteration found by the demo.** The first reused answers gave only the explainer's opening line, *"Groww charges a brokerage fee for executing your trades."*: true, but it doesn't say how much. A reused answer now adds the line from the same official page that carries the figure, unless the question only asks what the fee is. The same question afterwards (GRW-567CN9, from the new canonical explainer #5):

> Groww charges a brokerage fee for executing your trades. Here's a breakdown: Equity Trading: The fee is either ₹20 or 0.1% of your trade value, whichever is lower. Source: https://groww.in/help/payments-&-withdrawals/payments-charges/what-fees-does-groww-charge--58 Last checked: 2026-11-19.

## Run it locally

```bash
# API (Python 3.12+), needs api/.env with GROQ_API_KEY (and Google keys for delivery)
cd api && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
(cd mcp_server && npm ci && npm run build)
.venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8000

# Page
cd web && npm ci && npm run dev        # http://localhost:3000 (NEXT_PUBLIC_API_URL in web/.env.local)

# Tests
cd api && .venv/Scripts/python -m pytest -q       # offline (USE_LLM=0)
cd web && npm test && npm run e2e                  # vitest + Playwright
```

## Deployment

- **API on Railway** from `api/Dockerfile` (Python 3.12 + Node 22 for the MCP server; embedding model baked in), one
  worker, scheduler on (weekly loop Mondays 09:00 IST), `/health` reports database, search index and Google readiness.
- **Page on Vercel** from `web/` (Next.js), `NEXT_PUBLIC_API_URL` → the Railway API; the deployed API accepts browser calls only from that page and localhost (`CORS_ORIGINS`).
- **Storage:** SQLite on a Railway volume (database, corpus, index). A deliberate choice over Postgres: one process
  with one scheduler, every test runs on SQLite, and the volume survives redeploys.
- Details and redeploy steps: [`web/README.md`](web/README.md#deployed).

## Repository

- `api/` — FastAPI app: `app/intent`, `app/desk` (agents), `app/corpus` (retrieval), `app/guard` (PII, compliance,
  rate limits), `app/weekly`, `app/approvals`, `app/delivery` (MCP client), `app/evals`; tests in `api/tests/`.
- `web/` — the single page (Ask · Queue · This week).
- `docs/superpowers/` — the design specs and implementation plans, plan by plan.
