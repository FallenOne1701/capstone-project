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

- **How the two loops connect** (shown working on the live site — see [The link in action](#the-link-in-action)):
  1. **Response → weekly:** every ticket gets a question key (intent · fee topic · fund). A key asked **5 or more times
     in 7 days** appears under "Asked repeatedly" in the next pulse, and the fee line counts those questions next to
     the reviews (e.g. "Brokerage & charges: 81 reviews and 6 questions").
  2. **Weekly → response:** when a person approves the weekly Doc append, that week's fee explainer becomes
     **canonical**; later fee questions are answered from it instead of being drafted fresh (routing note
     "Reused canonical explainer #N").
  3. The desk also uses the week's review themes to label and route each ticket.
- **MCP:** the API runs our MCP server (`api/mcp_server/`, vendored from Milestone 2) as a stdio subprocess and calls
  only `google_docs_append_content` and `gmail_create_draft`; `gmail_send_email` is denylisted, so mail is only ever a
  draft. Each call runs only after a person approves that action; failures show in plain words with a Retry.
- **Grounding:** one section of a scheme page → one chunk, `bge-small-en-v1.5` embeddings in Chroma. A reply states
  one fact with its source URL and "Last checked" date, or says "not covered" and names what it searched.
- **Safety design** (every rule, where it is enforced in code, and the test that proves it): [`docs/SAFETY.md`](docs/SAFETY.md).
- **Compliance:** advice and return/performance requests get fixed refusals; personal data is redacted before
  anything is stored, logged or sent to an AI model; a log filter redacts every log line again.
- **The approval gate** (`AUTO_APPROVE=0`): every reply and Google write is a pending action; approve / edit / reject
  are audited, and approve publishes only the exact text the person saw.

## Sources

Only public, official pages (fetching and citing are limited in code to `groww.in`, `amfiindia.com`, `sebi.gov.in`).
Each page is re-fetched weekly (Sundays 21:00 IST) and every answer shows its "Last checked" date; the live list with
dates is the **Sources** section of the *This week* tab.

- **15 HDFC scheme pages on Groww** (one fact per section: expense ratio, exit load, minimum SIP, benchmark,
  riskometer, lock-in…): Mid Cap · Small Cap · Large Cap · Focused · ELSS Tax Saver · Defence · Pharma and Healthcare ·
  Innovation · Banking & Financial Services · MNC · Gilt · Ultra Short to Short Term · Medium to Long Term · Arbitrage ·
  Gold ETF Fund of Fund — all at `https://groww.in/mutual-funds/<scheme>-direct-growth` (list in
  [`api/app/corpus/sources.yaml`](api/app/corpus/sources.yaml)).
- **4 fee reference pages:** [What is exit load? — Groww Help](https://groww.in/help/mutual-funds/order/what-is-exit-load--71) ·
  [What are the charges applicable for redeeming? — Groww Help](https://groww.in/help/mutual-funds/order/what-are-the-charges-applicable-for-redeeming--53) ·
  [What fees does Groww charge? — Groww Help](https://groww.in/help/payments-&-withdrawals/payments-charges/what-fees-does-groww-charge--58) ·
  [Expense Ratio — AMFI Investor Corner](https://www.amfiindia.com/investor/knowledge-center-info?zoneName=expenseRatio).
- **Reviews:** public Google Play reviews of the Groww app (`com.nextbillion.groww`), fetched every Monday, personal
  data redacted on the way in. Sample: [`docs/samples/reviews_sample.csv`](docs/samples/reviews_sample.csv).

## What the reviews told us — the fee issue

Weekly run 6 (automatic, Monday 2026-11-23): **3,176 Play Store reviews** (29 Oct – 23 Nov), 470 matched a theme.
Top themes: **Trading & order execution** (202), **Fees, charges & funding** (101), **App reliability & updates** (94),
then Customer support (56) and Charts & holdings data (17).

The recurring fee confusion is **brokerage & charges** — users asking what Groww charges per trade and about charges
they didn't expect ("hidden charges on brokerage, DP charge not shown before selling"). It is the top fee topic in
**81 reviews**, and **6 support questions** about it that week. The weekly loop turned it into a facts-only explainer
from Groww's help pages (equity trades: ₹20 or 0.1% of trade value, whichever is lower; minimum ₹5; zero fees for
redeeming mutual funds), which a person approved and which now answers brokerage questions on the desk.

## Evals — latest run

Run 8 (2026-11-25, on the final code), real AI, file [`api/evals/results/run-8-2026-11-25.json`](api/evals/results/run-8-2026-11-25.json) — the same scores as run 7 (2026-11-19), so the later layout and speed changes broke nothing:

| Eval | Score | What it checks |
|---|---|---|
| Feasibility | **44/45** | 41 questions each end with a cited answer, a not-covered naming what was searched, or the right refusal; the weekly run completes on its own with themes (review ids + window), pulse ≤250 words, explainer ≤6 bullets |
| Edit isolation | **5/5** | one edit / approve / reject changes exactly the expected rows across every table; approving the Doc never touches the email |
| Grounding & compliance | **55/55** | advice and return requests refused; synthetic PAN / account / phone numbers redacted in **both loops** (tickets and fake reviews); 15 sampled claims are found on the cited official page or in the cited review; nothing sensitive in logs, database or outbox |
| Intent (sub-score) | **41/41** | the question type the desk chose |

Iteration: run 1 scored 30/44 · 5/5 · 37/45; a code review then made the checks stricter; the fixes in between are in the history. The one remaining failure is a
question in Devanagari script (a known limitation).

**Evals report** (golden dataset, adversarial tests, scores): [`docs/EVALS_REPORT.md`](docs/EVALS_REPORT.md). Every requirement of the brief, how it is checked and the latest result: [`docs/EVAL_CHECKLIST.md`](docs/EVAL_CHECKLIST.md). Full history — every failure, its cause, the fix and the re-run: [`api/EVALS.md`](api/EVALS.md). Live latency before/after Plan 6 (e.g. Hinglish draft 10.3 s → 2.4 s): [`api/EVALS.md` → Latency](api/EVALS.md#latency-plan-6-live-site).
**How to run the evals:** `cd api && .venv/Scripts/python -m app.evals run all` (or `feasibility` · `isolation` · `grounding`). They use the real AI (Groq, Gemini as fallback) against a throwaway local database with Google stubbed, so they never touch the live Queue or Google; ~2.5 min, ~30 AI calls; each run prints a score card and saves every case to `api/evals/results/run-<n>-<date>.json`.

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

## Known limits

- **Questions written in Devanagari script** get "not covered" (it names what it searched); Hinglish in Latin script
  works. This is the one failing eval case (`l04`).
- **How-to questions** ("how do I start a SIP?") get an honest "not covered": the corpus is scheme pages and fee
  reference pages only.
- **Personal-data masking is pattern-based** (PAN, Aadhaar, phone, email, UPI, card, account, IFSC, OTP); an unusual
  format may slip through.
- **The page has no password** (a deliberate choice): anyone on it can approve. Google writes are limited to a Doc
  append and a Gmail *draft*, and approvals are rate-limited.
- **The first question after a redeploy is slow** (~8 s; later ones ~1–3 s); the cause isn't found yet.
- **The Google sign-in is in testing mode**, so it must be renewed every 7 days (last renewed 2026-11-25).
- The evals' weekly part uses a fixed set of reviews; theme quality on live reviews is checked with
  `api/scripts/verify_weekly.py`.

More: [`docs/SAFETY.md`](docs/SAFETY.md) (safety limits) · [`api/EVALS.md`](api/EVALS.md) (eval limits).

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
- `web/` — the single page (tabs: Ask · This week · Queue).
- `docs/superpowers/` — the design specs and implementation plans, plan by plan.
