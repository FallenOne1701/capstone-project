# Plan 6 — Snappier desk (real speed + perceived speed)

Date: 2026-11-20. Branch `plan-6-snappier`. Approach **B** chosen by the user: cut the waste (A) *and* make waits feel shorter.

## Intent and why
The user wants the desk to feel **snappier** in both phases: while someone asks (Continue → Send) and until the draft reaches the Queue for a person to approve. It matters for the demo and for the graded "Voice UX & intent" (25%). The user offered to add LLMs; measurement showed most questions use none, so extra models are not the lever (approach C rejected for now).

### Baseline (live, 2026-11-20, one run each; `.superpowers/latency.py`)
| Question | Continue (preview) | Send (ask) | Send → draft ready (`in_review`) |
|---|---|---|---|
| Clear fee question (rules only, no AI) | 0.93 s | 0.76 s | 3.63 s |
| Unclear wording ("how much yearly charge for hdfc small cap", 1 AI call) | 6.18 s | 4.26 s | 9.24 s |
| Hinglish ("HDFC Mid Cap Fund ka exit load kitna hai?", translation) | 1.25 s | 1.45 s | 10.34 s |

Plus the page's own wait: the asker's ticket polls every 3 s (`TicketStatus` `POLL_MS`/`nextPollMs`), the Queue every 5 s (`DeskTabs` `QUEUE_POLL_MS`).

### Causes found in the code
1. `classify_intent` runs **three times** per question: `preview()`, `create_ticket()` and `process_ticket()` (`api/app/tickets/service.py:61,73,98`). On unclear wording each run is a Groq call.
2. Hindi/Hinglish drafts call `translate_reply` (the large model) **before** the ticket moves to `in_review` (`service.py` ~line 128).
3. ~3.6 s on a clear question with no AI: unmeasured server work (retrieval embeddings on Railway CPU, LangGraph run, themes provider, reviewer…).
4. Polling intervals add up to 3 s (ticket) / 5 s (Queue) on top.

## Goals
**Real speed (server):**
- G1. **Classify once.** The intent from Continue (`preview`) is reused by Send (`create_ticket`) and the worker (`process_ticket`) for the same redacted text. The worker rebuilds the `IntentResult` from the ticket's stored fields (`intent`, `scheme_id`→`scheme_ids`, `fact_key`, `language`) instead of classifying again. Send reuses the preview's result through a small in-memory cache keyed by the redacted text (single process on Railway; short TTL, e.g. 10 min, bounded size). A cache miss just classifies as today.
- G2. **Hindi translation off the critical path.** The ticket moves to `in_review` (draft in the Queue) as soon as the English draft and its review exist; the Hindi translation is produced right after in the same job and attached when ready. The Queue shows "Hindi translation coming…" until then.
- G3. **Measure, then fix the top cost** of the no-AI path. Add per-step timing to the desk job (log lines with durations only — no question text, no PII) and fix whatever dominates the ~3.6 s, if it can be fixed without changing answers (e.g. keep the embedding model/Chroma client warm, cache the themes provider for a short time). Record the finding.
- G4. **Faster updates.** Asker's ticket polls every **1 s** while `received` (then as today); the Queue polls every **2 s**.

**Perceived speed (page):**
- G5. **Continue / Send respond instantly**: the button shows a working state at once and the confirm card area shows a placeholder ("Checking your question…") until the preview arrives.
- G6. **Live progress**: while the ticket is `received`, the "Checked" step shows as in progress (animated), not a frozen ring; steps fill as status changes.
- G7. **Optimistic Queue actions**: Approve / Reject update the card at once (it shows the new state and moves to its filter), the server call runs, and the queue reloads; on an error the card goes back and shows the error. Edit keeps today's behaviour (the reviewer must re-run).

**Proof:**
- G8. A small latency script in the repo (from `.superpowers/latency.py`, cleaning up its own test tickets by rejecting them) and a before/after table in `api/EVALS.md` or the README.
- Target after: clear question draft ready ≤ ~2 s, unclear/Hinglish ≤ ~5 s (targets, not hard gates).

## Non-goals
- No new LLM providers or racing (approach C). No model changes for answers.
- No change to what answers say, the reviewer rules, compliance, or the approval gate.
- No server push (SSE/websockets) — faster polling is enough.

## Anti-goals (failure even if faster)
- **An unapproved Hindi text reaching the asker** (rule: see call 1 below). Today `_published_translation` (`api/app/api/public.py` ~line 82) returns *any* translation of the executed draft. With G2 a translation could be written after the person approved. Rule: the asker sees the Hindi version **only if it existed when the person approved** (translation `created_at` ≤ the reply action's `decided_at`). Otherwise the asker sees English only. The approver must have been able to see the Hindi text they approved.
- Reusing an intent for a **different** text (cache must key on the exact redacted text; a choice of fund at Send — `scheme_id` — still overrides as today).
- Optimistic UI that **hides a failed approval** (e.g. 409 "the reply changed") — the card must revert and show the error.
- Logging question text or PII in the new timing lines.
- Breaking any existing test, the evals' behaviour, or the 3-sentence/250-word/6-bullet caps.

## Constraints
- FastAPI app, single Railway process (in-memory cache is fine; it may be empty after a redeploy).
- TDD; API suite (484 passed today) and web (vitest 65, Playwright 37) stay green; Playwright runs with `USE_LLM=0`, so AI-path timing is checked with API unit tests and the live latency script.
- Deploy: API on Railway (`railway up --detach --service api` from `api/`) and page on Vercel (`npx vercel deploy --prod` from `web/`), only after the user approves.

## Approaches considered
- **A. Cut the waste only** — real time drops, but the page still looks frozen during waits.
- **B. A + perceived speed (chosen)** — real time drops and the page responds instantly to every click.
- **C. A + racing Groq and Gemini** — helps only the remaining rare AI calls; doubles their cost. Deferred.

## Decided
- B, with G1–G8 above. Hindi becomes asynchronous (G2) with the "only if present at approval" rule, rather than switching translation to the fast model (keeps translation quality as it is).
- Poll intervals: ticket 1 s while `received`; Queue 2 s.

## Calls made after the builder check (Claude's calls, for the user to check)
1. **Hindi gate = proof the approver saw it, not a timestamp.** Approve sends the Hindi text the person was shown (or nothing if the card said "Hindi translation coming…"), the same way it already sends the English reply it showed. The asker gets the Hindi version only if it matches what was sent with the approval; otherwise the asker gets English only. The English approval itself is never refused because of the Hindi (no 409 for that). Replaces the `created_at ≤ decided_at` wording above.
2. **Auto mode (`AUTO_APPROVE=1`) keeps translation synchronous** (today's order: translate, then decide), so auto-approved Hindi tickets still get Hindi. The live site runs `AUTO_APPROVE=0`; G2's speed-up applies there.
3. **No database change for G1.** The in-memory cache holds the full classification for the exact redacted text: `preview` fills it, `create_ticket` reads it (or classifies and fills it), and the worker reads it (or classifies on a miss, e.g. after a redeploy). The worker still applies the fund chosen at Send (`t.scheme_id`) as today. This keeps multi-fund questions exactly as now.
4. **Latency script runs against the live site, sparingly.** Before/after = one run each. It asks a few questions with different keys and **no brokerage question** (so the demo's "Asked repeatedly: Brokerage & charges" and explainer reuse counts are untouched), stays far below the 5-asks threshold, and rejects its tickets afterwards. The script says so at the top.

## Left to the builder
- Cache shape/TTL/size for G1; where the timing helper lives (G3); which top cost to fix once measured, and whether it is fixable within the plan (if not, record it and move on).
- Exact placeholder/animation styling (existing tokens; respect `prefers-reduced-motion`).
- How the "Hindi translation coming…" state is represented in the queue item (e.g. a `translation_pending` flag).
