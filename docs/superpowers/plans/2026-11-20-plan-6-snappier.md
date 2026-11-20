# Plan 6 — Snappier Desk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the real time from Send to a reviewable draft (classify once, Hindi off the critical path, fix the top no-AI cost, faster polling) and make every wait feel instant on the page.

**Architecture:** API: an in-memory intent cache shared by preview → ask → worker; the desk job moves the ticket to `in_review` before translating; the desk approve endpoint records which Hindi text the person saw; per-step timing logs. Web: faster polls, a "Checking…" placeholder, a live progress step, optimistic Approve/Reject.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite), pytest; Next 16.4.6 + React 19, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-20-snappier-design.md`

## Global Constraints
- No change to answer text, reviewer rules, compliance, caps (3 sentences / 250 words / 6 bullets) or the approval gate.
- No database schema change. No new LLM provider.
- Hindi reaches the asker **only if the approving person was shown exactly that Hindi text** (spec call 1). English approval is never refused because of Hindi.
- `AUTO_APPROVE=1` keeps today's order: translate, then decide (spec call 2).
- Timing logs carry step names, durations and the ticket id only — never question text or PII.
- Poll intervals: asker's ticket 1000 ms while `received`; Queue 2000 ms.
- Respect `prefers-reduced-motion` for any animation (`motion-safe:` classes).
- Latency script runs against live at most once before (done: spec baseline) and once after; no brokerage question; rejects its tickets.
- Execution: Native + one fresh reviewer at the end; TDD; deploy only with the user's OK.

## Review Focus
1. **Approve races the translation**: the card showed "Hindi translation coming…", the translation lands one poll later, the person clicks Approve → asker must get English only. Tests in Task 2.
2. **Translation fails validation or errors**: "coming…" must not show forever; the card shows no Hindi and approval works. Test in Task 2.
3. **Redeploy empties the intent cache** between Send and the worker → the worker classifies again and the answer is unchanged. Test in Task 1.
4. **Optimistic Approve gets a 409** ("the reply changed") → the card reverts to pending and shows the message. Test in Task 5.
5. **Same text, different chosen fund** (Mid Cap vs Small Cap answered at Send) → the cached intent never overrides the person's choice. Test in Task 1.

---

### Task 1: Classify once (intent cache)

**Files:**
- Create: `api/app/intent/cache.py`
- Modify: `api/app/tickets/service.py` (`preview`, `create_ticket`, `process_ticket` use the cache)
- Test: `api/tests/test_intent_cache.py`

**Interfaces:**
- Produces:
  - `class IntentCache: def __init__(self, ttl_s: float = 600, max_items: int = 500, clock: Callable[[], float] = time.monotonic)`; `get(text: str) -> IntentResult | None`; `put(text: str, intent: IntentResult) -> None`; `clear() -> None`. Oldest entry evicted past `max_items`.
  - Module-level `intent_cache = IntentCache()` and `async def classify_cached(redacted_text: str) -> IntentResult` (get → else `classify_intent` → put → return a copy).
- `service.py` calls `classify_cached` in all three places; `process_ticket` still applies `t.scheme_id` afterwards exactly as today.

- [ ] **Step 1: Write failing tests** in `tests/test_intent_cache.py` (monkeypatch `app.intent.cache.classify_intent` with a counting async fake returning a fixed `IntentResult`; `intent_cache.clear()` in a fixture):
  - `test_preview_ask_and_worker_classify_once`: `preview(text)`, `create_ticket(db, text)`, `process_ticket(db, t.id, retriever=…)` → fake called **1** time.
  - `test_different_text_classifies_again`: two texts → 2 calls.
  - `test_entry_expires`: `IntentCache(ttl_s=10, clock=fake)`; advance 11 s → `get` is `None`.
  - `test_bounded_size`: `max_items=2`, put 3 → first evicted.
  - `test_empty_cache_after_redeploy_gives_same_answer` (Review Focus 3): create ticket, `intent_cache.clear()`, process → draft identical to a run without clearing (same `reply`, `citation`).
  - `test_chosen_fund_wins_over_cached_intent` (Review Focus 5): text naming two funds, `create_ticket(..., scheme_id=<second>)`, process → `d.citation` ends with the second fund's slug.
- [ ] **Step 2: Run** `cd api && .venv/Scripts/python -m pytest -q tests/test_intent_cache.py` — expect FAIL (no module).
- [ ] **Step 3: Implement** `cache.py` and switch the three call sites.
- [ ] **Step 4: Run** `tests/test_intent_cache.py tests/test_canonical.py tests/test_intent.py` — PASS.
- [ ] **Step 5: Commit** `perf(api): classify a question once (preview → ask → worker share the result)`.

### Task 2: Hindi off the critical path, gated on what the approver saw

**Files:**
- Modify: `api/app/tickets/service.py` (`process_ticket`, `_add_translation`), `api/app/api/desk.py` (`ApproveIn`, `approve`), `api/app/api/public.py` (`_published_translation`), `api/app/api/console.py` (`_draft_out`: `translation_pending`)
- Test: `api/tests/test_translation_async.py`

**Interfaces:**
- `ApproveIn.translation: str | None = None` — the Hindi text the person was shown (absent/None = none shown).
- Desk approve: for `reply_publish`, after the existing English check, if a `DraftTranslation` exists for the draft and its `text != body.translation`, delete it and `audit(db, "page", "discard", "translation", draft_id, "not shown at approval")` before approving.
- `_add_translation(db, d)` writes the row only if the draft's `reply_publish` action is still `pending` (non-auto mode); always audits `translate` with `ok` / `discarded:<why>` / `late`.
- `_published_translation`: additionally requires `DraftTranslation.created_at <= Action.decided_at`.
- `_draft_out(...)["translation_pending"]: bool` — true when ticket language is `hi`/`hinglish`, review `pass`, no translation row, no `translate` audit row for the draft, and its action is `pending`.
- `process_ticket` order: non-auto → create draft + action, set `in_review`, **commit**, then translate (separate commit). Auto mode → translate before the action/decision (today's order).

- [ ] **Step 1: Write failing tests** (`USE_LLM=0`; monkeypatch `app.tickets.service.translate_reply` with an async fake; read ticket status inside the fake):
  - `test_ticket_is_in_review_before_translation`: inside the fake, a fresh session sees the ticket `in_review` → assert recorded status == `"in_review"`.
  - `test_pending_flag_until_translation_lands`: patch translate to block on an event; queue item shows `translation_pending: True`; release → `False` and `translation` set.
  - `test_failed_translation_clears_pending` (Review Focus 2): fake returns `None` → `translation_pending` False, no translation, approve works, asker gets English.
  - `test_approve_with_seen_hindi_publishes_hindi`: approve via `/api/desk/actions/{id}/approve` with `{reply, translation: <row text>}` → `/api/tickets/{code}` has `answer_local.text == row text`.
  - `test_approve_without_seen_hindi_gives_english_only` (Review Focus 1): row exists, approve with `{reply}` only → `answer_local is None`; audit has `discard`.
  - `test_translation_after_approval_never_published`: approve first (no row), then run `_add_translation` → no row written (audit `late`), `answer_local is None`; also a row inserted manually with `created_at` after `decided_at` → not published.
  - `test_auto_mode_translates_before_deciding`: `AUTO_APPROVE=1` → answered ticket has `answer_local`.
- [ ] **Step 2: Run** `pytest -q tests/test_translation_async.py` — expect FAIL.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** `pytest -q tests/test_translation_async.py tests/test_translate.py tests/test_auto_decide.py tests/test_desk_api*.py` — PASS (adjust only tests that encoded the old synchronous order, with a ledger ruling).
- [ ] **Step 5: Commit** `perf(api): drafts reach the Queue before the Hindi translation; Hindi published only if the approver saw it`.

### Task 3: Time each desk step and fix the top cost

**Files:**
- Create: `api/app/desk/timing.py`
- Modify: `api/app/tickets/service.py` (wrap steps), `api/app/deps.py` or the module that owns the top cost
- Test: `api/tests/test_timing.py` (+ a test for the fix)

**Interfaces:**
- `@contextmanager def step(name: str, ticket_id: int)` logs `INFO app.desk.timing: desk ticket=<id> step=<name> ms=<int>`.
- Steps: `classify`, `canonical`, `retrieve+agents` (run_desk), `review`, `translate`, `total`.

- [ ] **Step 1: Write failing test** `test_step_logs_name_and_duration_only`: process a ticket whose question contains `ABCDE1234F` → captured `app.desk.timing` records include each step name and `ms=`, and no record contains the question text, `ABCDE1234F` or `[PAN]`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** `timing.py` + wrap. **Step 4: Run** — PASS.
- [ ] **Step 5: Measure** locally: `USE_LLM=0`, real corpus index, process 5 clear questions in a fresh process; record per-step ms in the ledger. Then the same against Railway logs after Task 6 deploy if needed.
- [ ] **Step 6: Fix the top cost** if it is fixable without changing answers. Expected candidate: `deps.get_retriever()` builds a new `Retriever` (Chroma client) per ticket → make it a process-wide singleton. Test first: `test_retriever_is_built_once` (`deps.get_retriever() is deps.get_retriever()`); and the existing retrieval tests still pass. Other candidate: `latest_theme_stats` per ticket → 60 s cache with a test. Ledger the finding either way.
- [ ] **Step 7: Run** the full API suite `pytest -q` (~11 min) — all pass. **Commit** `perf(api): per-step desk timing; <the fix>`.

### Task 4: Faster updates (web)

**Files:**
- Modify: `web/lib/labels.ts` (`nextPollMs`), `web/components/desk/DeskTabs.tsx` (`QUEUE_POLL_MS`), `web/components/ticket/TicketStatus.tsx` (first retry uses `nextPollMs`)
- Test: `web/lib/labels.test.ts`

- [ ] **Step 1: Failing test**: `expect(nextPollMs("received")).toBe(1000)`; `in_review` stays `3000`; `failed` `15000`; answered/closed `null`.
- [ ] **Step 2: Run** `npx vitest run lib/labels.test.ts` — FAIL. **Step 3: Implement**; `QUEUE_POLL_MS = 2000`. **Step 4: Run** vitest — PASS. **Step 5: Commit** `perf(web): poll every second while a question is being checked; Queue every 2 s`.

### Task 5: Perceived speed (web)

**Files:**
- Modify: `web/components/ask/AskFlow.tsx` (placeholder), `web/lib/labels.ts` (`progressSteps` for `received`), `web/components/ticket/TicketStatus.tsx` (pulsing current step), `web/components/desk/ActionButtons.tsx` (optimistic + `seenTranslation`), `web/components/desk/QueueItem.tsx` (pass `seenTranslation`, "Hindi translation coming…"), `web/lib/api.ts` (`approve(id, reply?, translation?)`), `web/lib/types.ts` (`DraftView.translation_pending: boolean`)
- Test: `web/lib/labels.test.ts`, `web/e2e/ask.spec.ts`, `web/e2e/desk.spec.ts`

**Interfaces:**
- `approve(id: number, reply?: string, translation?: string | null)` → body `{ reply, translation }` when `reply` is given.
- `ActionButtons` new prop `seenTranslation?: string | null`; optimistic state: on Approve → badge `approved` and buttons hidden at once; on Reject → badge `rejected`; on error → back to the server status + the error message.
- `progressSteps("received", …)` → Received `done`, Checked `current`, rest `todo`.

- [ ] **Step 1: Failing tests:**
  - vitest: `progressSteps("received","person")!.map(s => s.state)` equals `["done","current","todo","todo"]` (replaces the old `received` expectation).
  - e2e ask: `"Continue shows a checking placeholder at once"` — route `**/api/ask/preview` with a 1.5 s delay → right after clicking Continue, `getByRole("status").filter({ hasText: "Checking your question…" })` is visible; then the confirm card appears.
  - e2e desk: `"Approve updates the card at once and reverts on a refusal"` (Review Focus 4) — route `**/api/desk/actions/*/approve` → wait 1 s then fulfil 409 `{detail:"This reply changed after you opened it — check it again."}`; click Approve → the card's badge shows `approved` within 300 ms; then badge `pending` again and the alert text visible.
  - e2e desk: `"a Hindi draft says its translation is coming"` — route the queue to set `draft.translation=null, translation_pending=true` on one item → card shows "Hindi translation coming…".
- [ ] **Step 2: Run** vitest + those e2e specs — FAIL.
- [ ] **Step 3: Implement**; the pulsing ring uses `motion-safe:animate-pulse`; QueueItem passes `seenTranslation={d.translation?.text ?? null}`.
- [ ] **Step 4: Run** `npx vitest run && npm run build && npm run e2e` — all pass. **Commit** `feat(web): instant feedback — checking placeholder, live progress step, optimistic approve/reject`.

### Task 6: Prove it, review, ship

**Files:**
- Create: `api/scripts/latency.py` (from `.superpowers/latency.py`: non-brokerage questions only; rejects its tickets; header says it runs against live sparingly)
- Modify: `api/EVALS.md` (a "Latency" section with before/after), `README.md` (one line + link), `CLAUDE.md`

- [ ] **Step 1:** Full suites: API `pytest -q`, web `npx vitest run && npm run build && npm run e2e`.
- [ ] **Step 2:** Fresh reviewer (most capable model) over the branch; fix Critical/Important test-first.
- [ ] **Step 3:** Ask the user, then push / PR / merge / `railway up` (API) / `vercel deploy --prod` (web).
- [ ] **Step 4:** Run `api/scripts/latency.py` once against live; write the before/after table (spec baseline vs now) to `api/EVALS.md`; commit as a docs PR for the user's OK.
