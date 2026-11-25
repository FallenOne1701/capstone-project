# Eval checklist — Groww Support Desk

Every requirement of the brief, how it is checked in this repo, and the latest result. Only checks that exist and have been run are listed; the run record at the end is filled in, not a template. Safety rules and the code behind them: [`SAFETY.md`](SAFETY.md). Full eval history (every failure, its cause, the fix and the re-run): [`api/EVALS.md`](../api/EVALS.md).

## How to run each check

| Check | Command | Takes |
|---|---|---|
| The three evals (real AI, throwaway local DB, Google stubbed) | `cd api && .venv/Scripts/python -m app.evals run all` (or `feasibility` · `isolation` · `grounding`) | ~2.5 min, ~30 Groq calls; saves `api/evals/results/run-<n>-<date>.json` |
| API tests (AI off) | `cd api && .venv/Scripts/python -m pytest -q` | ~12 min |
| Page unit tests | `cd web && npm test` | seconds |
| Browser tests (own API :8001 + page :3001, AI and Google off) | `cd web && npm run e2e` | ~2 min |
| Live latency (sparing: asks 3 non-brokerage questions, rejects its tickets) | `cd api && .venv/Scripts/python scripts/latency.py` | ~1 min |
| Weekly run verification page (read-only) | `cd api && .venv/Scripts/python scripts/verify_weekly.py --log ../.superpowers/server.log` | seconds |

## The brief, line by line

✅ = checked and passing at the latest run. Eval case ids are from `api/evals/datasets/` and the run file.

### 1. Weekly loop

| Requirement | How it is checked | Result |
|---|---|---|
| Reviews ingested, clustered into **at most five** themes, top three picked | `test_themes.py::test_build_themes_capped_ranked_traced` (1–5 themes, ranked); feasibility `weekly_completes` | ✅ |
| Every theme traces to **review ids**; every count states its **window** | feasibility `themes_have_ids_and_window`; same theme test (count = number of review ids, window dates) | ✅ |
| Pulse **≤ 250 words**, with supporting quotes and **three action ideas** | feasibility `pulse_le_250_words`; `test_pulse.py`; grounding `claim` cases (quotes must appear in the cited review) | ✅ |
| Fee explainer **≤ 6 bullets**, facts only, **two official links**, "last checked" | feasibility `explainer_le_6_bullets`; `test_fee_explainer.py::test_validate_catches_bad_drafts` (fewer than 2 distinct links, more than 6 bullets, advice → rejected) | ✅ |
| Both go through the approval gate before the Doc append and the email draft | isolation `approve_doc_append`, `reject_email_draft`; `test_executors_link2.py`; browser `desk.spec.ts` (weekly approvals say exactly where they write) | ✅ |
| Real delivery | Live: run 3 (2026-11-19) and run 5 (2026-11-20) appended to the Google Doc and created a Gmail draft after a person approved each — text in [`samples/weekly_delivery.md`](samples/weekly_delivery.md) | ✅ |

### 2. Response loop

| Requirement | How it is checked | Result |
|---|---|---|
| Each question ends with a cited answer, a not-covered that **names what it searched**, or the right refusal | feasibility: 41 questions (`f` fund facts ×14, `e` fees ×8, `h` how-to ×5 — 4 answered from Groww Help pages, 1 not covered, `n` not covered ×6, `u` unclear wording ×4, `l` Hinglish/Hindi ×4) | 44/45 (only `l04`, Devanagari, fails) |
| The question type the desk chose | intent sub-score over the same 41 questions | 41/41 |
| Reply draft carries its **citation** and an internal **routing note** | `test_orchestrator.py` (cited reply, not-covered names searched, off-topic refused); live link demo: every draft's routing note visible in the Queue | ✅ |
| A person **approves, edits or rejects** each draft, and each changes exactly what it should | isolation `edit_draft`, `approve_reply`, `reject_reply` (every table snapshotted before/after); browser `desk.spec.ts` (approve → answer shows; reject → closed + Ask again; blocked draft can't be approved; optimistic approve reverts on 409) | 5/5 ✅ |

### 3. The connection between the loops

| Requirement | How it is checked | Result |
|---|---|---|
| Same question **five times in a week** → in the weekly pulse | `test_question_keys.py` (threshold and 7-day window, boundary day inside); live 2026-11-20: five brokerage questions → pulse run 5 "Fee question · Brokerage & charges: 5 questions" | ✅ shown live |
| The fee explainer becomes the **canonical answer** the response loop reuses | `test_canonical.py` (concept and scheme questions reuse it; superseded never reused; figure line added); live 2026-11-20: 5 drafts with routing note "Reused canonical explainer #4 (brokerage)" | ✅ shown live |

Write-up of the live demo: README → [The link in action](../README.md#the-link-in-action).

### 4. Scope and privacy

| Requirement | How it is checked | Result |
|---|---|---|
| No advice / buy-sell language | grounding `adv` ×8 (4 attacks, each sent twice), `pulse_no_advice_or_returns` | ✅ |
| No return or performance figures | grounding `perf` ×6 | ✅ |
| No PII anywhere — tickets, reviews, logs, database, outbox | grounding `pan` ×6, `acc` ×6, `ph` ×6 (tickets), 4 fake Play Store reviews with PII, then `no_leaks`: the log file, every text column in the database and the outbox searched for the original strings (also with spaces/dashes/other case) | ✅ |
| Every factual claim has one official source; public sources only | grounding `claim` ×15 (sampled from replies, pulse quotes and explainer bullets: found on the cited official page or in the cited review); feasibility checks every citation is on an allowed domain | ✅ |
| Corpus doesn't cover it → says so and names what it searched | grounding `out_of_corpus` ×2; feasibility `n` questions | ✅ |

### 5. Interface

| Requirement | How it is checked | Result |
|---|---|---|
| Queue with drafts, citations, reviewer flags | browser `desk.spec.ts`, `tabs.spec.ts` (filters, badge, queue failure) | ✅ |
| Weekly pulse view with themes, quotes and counts | browser `weekly.spec.ts` (seeded pulse, theme list, quotes, links) | ✅ |
| Sources panel with last-checked dates | browser `weekly.spec.ts` (sources open, links visible) | ✅ |
| Approval screen listing exactly what will be written and where | browser `weekly.spec.ts` (exact text shown without a click), `desk.spec.ts` | ✅ |
| Canonical explainers being reused | browser `weekly.spec.ts` (fee explainers section open) | ✅ |
| Voice: speak a question, listen to the answer | browser `ask.spec.ts` (voice reaches confirm, too-short clip never uploaded, voice service down → typing), `listen.spec.ts` | ✅ (see flaky note below) |

## Run record

| Field | Value |
|---|---|
| Evals | **Run 9, 2026-11-25, real AI, final code** (with the how-to pages) — feasibility **44/45**, edit isolation **5/5**, grounding & compliance **55/55**, intent **41/41** · file `api/evals/results/run-9-2026-11-25.json` (runs 7 and 8 scored the same) |
| Eval history | Run 1: 30/44 · 5/5 · 37/45 → runs 7 and 8 above; every failure and fix in [`api/EVALS.md`](../api/EVALS.md) |
| API tests | **539 passed, 5 skipped** (2026-11-25, with the how-to pages) |
| Page unit tests | **67/67** (2026-11-22) |
| Browser tests | **40** (2026-11-22): 39 on the full run + `voice question reaches confirm` passed on re-run (known flake on this PC; also on pre-Plan-5 code) |
| Weekly delivery (live) | Run 3 (2026-11-19 15:47 UTC) and run 5 (2026-11-20 14:14 UTC): Doc append + Gmail draft executed after approval. Run 6 ran automatically on Monday 2026-11-23 (3,176 reviews; pulse carried "Brokerage & charges: 6 questions") and waits for approval |
| Link demo (live) | 2026-11-20: tickets GRW-F8CC2W, GRW-TJNBTW, GRW-T7Q98D, GRW-7PUZJH, GRW-YJ62U4 reused explainer #4; pulse run 5 shows them |
| Latency (live) | 2026-11-22: draft ready — clear 3.1 s, unclear 1.1 s, Hinglish 2.4 s ([table](../api/EVALS.md#latency-plan-6-live-site)) |

### Known gaps (not hidden)

- `l04` — a question in **Devanagari script** is answered "not covered" (it does name what it searched); Hinglish in Latin script works.
- **How-to questions** are answered only when one of the 13 Groww Help how-to pages covers them; others (e.g. a capital gains statement) get "not covered".
- The evals' weekly part uses a fixed reviews set; theme quality on live reviews is checked with `scripts/verify_weekly.py`, not by an eval.
- The grounding suite sends each attack twice (`repeat: 2`), so its 55 cases are about 39 distinct checks.
- The **first question after a deploy** took ~8 s on 2026-11-22 (later ones ~1–3 s); cause not found yet.
