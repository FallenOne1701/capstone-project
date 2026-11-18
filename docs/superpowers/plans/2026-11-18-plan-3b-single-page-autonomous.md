# Plan 3b — Single-page autonomous desk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One public page (`/`) works by itself as the support desk.
- A question (typed or spoken) is answered inline and approved automatically by the reviewer agent. A blocked draft is replaced by a fixed safe reply.
- The same page shows this week's pulse.
- The weekly loop delivers to the Google Doc and an unsent Gmail draft with no person involved, and retries hourly on failure.

**Architecture:** The approval machinery stays as it is (`Action`, `_claim`, `approve`, `retry`, audit). A new `app/approvals/auto.py` calls `approve()` with actor `"auto-reviewer"`:
- right after the desk drafts a reply;
- right after a weekly run succeeds.

New public read-only endpoints feed the page:
- `GET /api/weekly/summary`;
- a `checks` block on `GET /api/tickets/{code}`.

An in-process rate limiter guards the public POST routes. In the web app, `/` merges the ask flow, the inline ticket view and a weekly section, and the console, `/ask` and `/t` pages are removed (`/t/<code>` and `/ask` redirect).

**Tech Stack:** Same as Plan 3: FastAPI, SQLAlchemy, APScheduler, pytest; Next.js 16.4.2, React 19.3.0, Tailwind 4, vitest, Playwright.

**Spec:**
- `docs/superpowers/specs/2026-11-18-single-page-autonomous-desk-design.md` (the amendment; binding where it speaks);
- `docs/superpowers/specs/2026-11-17-support-desk-design.md` (binding wherever the amendment is silent).

Branch: `plan-3-console-voice` (amendment §F). Ledger: `.superpowers/sdd/2026-11-18-plan-3b-single-page-autonomous/progress.md`.

## Global Constraints

**Approval and publishing**
- Nothing is published or written to Google except through `approve()` / `retry()`. The automatic actor is exactly `"auto-reviewer"`.
- A draft with `review_status != "pass"` is never published. The fixed fallback reply goes out instead.
- The fallback reply is a fixed template (no LLM): "We couldn't confirm an answer to this from official sources. You can find {name}'s official details here: {url}". With no known scheme, `{name}` is "HDFC mutual funds" and `{url}` is `https://groww.in/mutual-funds/amc/hdfc-mutual-funds`.
- The email stays an **unsent Gmail draft**. `gmail_send_email` stays denylisted.

**Weekly delivery**
- Hourly delivery retry runs up to **6** attempts per action. On failure the status words shown are:
  - "pending (retrying)";
  - after the last attempt, "failed — sign-in expired" when the error matches `invalid_grant|unauthenticated|unauthorized|401|token`, else "failed".
- The weekly section shows the **last successful** run, labelled "Week ending <date>". It never says "this week" for a run older than 7 days.

**Public endpoints and limits**
- Public endpoints never return PII, a recipient address, a Doc id or `CONSOLE_PASSWORD`.
- Rate limits:
  - 10 `POST /api/ask` per client per 10 min;
  - 30 `POST /api/ask/preview` per client per 10 min;
  - 3 `POST /api/voice/transcribe` per client per min;
  - 300 `POST /api/ask` per day for the whole server.
- A limit hit returns 429 with detail "You've asked a lot of questions quickly — please wait a few minutes."
- The client key is the socket IP, or the first `X-Forwarded-For` hop when `TRUST_PROXY=1`.

**Settings**
- New settings:
  - `auto_approve: bool = True`;
  - `trust_proxy: bool = False`.
- `conftest.py` sets `AUTO_APPROVE=0`, so existing Plan 1–3 tests keep their pending-action behaviour. New tests turn it on explicitly.

**Unchanged rules from Plan 3**
- Additive DB only.
- `USE_LLM=0` keeps tests offline.
- Next 16.4.2, where page `params`/`searchParams` are Promises.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A blocked draft's Hindi translation leaks out with the fallback.** `answer_local` must come only from the *executed* draft, and the fallback has none. → Task 1, `test_fallback_publishes_no_hindi_from_blocked_draft`.
2. **Double publish when auto-decide runs twice** (worker recover plus retry, or two submits). `_claim` must make the second call a no-op. → Task 1, `test_auto_decide_is_idempotent`.
3. **A stale or failed run shown as current.** The latest run failed or is >7 days old, but the page must label the last good run by its real date. → Task 3, `test_summary_uses_last_successful_run` and `test_summary_marks_stale_week`.
4. **Behind Railway's proxy every visitor shares one IP**, so one person's limit would block everybody. → Task 4, `test_forwarded_for_used_only_when_trusted`.
5. **Weekly retries hammer an expired token forever, or retry a non-weekly action.** The retry must cap at 6 attempts and touch only `doc_append`/`email_draft`. → Task 2, `test_retry_caps_at_six_attempts` and `test_retry_ignores_reply_actions`.

---

### Task 1: Automatic reply decision with fixed fallback

**Files:**
- Create: `api/app/approvals/auto.py`
- Modify:
  - `api/app/desk/templates.py` (fallback);
  - `api/app/tickets/service.py` (call after the draft commit);
  - `api/app/tickets/worker.py` (retry once, then fallback);
  - `api/app/config.py`;
  - `api/tests/conftest.py`;
  - `api/app/approvals/service.py` (`retry` docstring).
- Test: `api/tests/test_auto_decide.py`

**Interfaces:**
- Produces:
  - `templates.fallback_reply(scheme_id: str | None) -> tuple[str, str]`, returning `(reply, citation_url)`;
  - `auto.AUTO_ACTOR = "auto-reviewer"`;
  - `auto.auto_decide(db, ticket_id: int) -> Action | None`. It takes the ticket's latest draft and its pending `reply_publish`:
    - if the review passed → `approve(..., AUTO_ACTOR)`;
    - else → create a fallback `Draft` (disposition `"fallback"`, `routing_why` "Fallback: <first failure check>"), review it with `review_draft`, create its `reply_publish`, mark the blocked draft's action `rejected` via `reject(..., AUTO_ACTOR)`, and approve the fallback's action.

    It returns the executed action, or `None` when there is nothing pending.
  - `auto.publish_fallback(db, ticket_id: int, reason: str) -> Action`, for tickets with no draft (desk crashed twice).
- Hook:
  - when `get_settings().auto_approve` is set, `process_ticket` calls `auto_decide(db, t.id)` after its commit;
  - `worker._job` re-runs a `failed` ticket once (status back to `received`); if that fails again it calls `publish_fallback(db, id, "desk error")`.

- [ ] **Step 1: Failing tests** (all set `monkeypatch.setattr(get_settings(), "auto_approve", True)`; use the fixture retriever like `test_tickets_api.py`)

```python
def test_passing_draft_is_published_automatically(wired, db_session)   # /api/ask fee question → ticket "answered", action executed, audit actor "auto-reviewer"
def test_blocked_draft_gets_fallback_not_published(wired, db_session, monkeypatch)  # run_desk returns review blocked → answer starts "We couldn't confirm an answer", contains the scheme URL; blocked draft's action "rejected"
def test_fallback_publishes_no_hindi_from_blocked_draft(...)          # Hinglish + translation stored on blocked draft → public answer_local is None
def test_auto_decide_is_idempotent(db_session, ...)                   # call auto_decide twice → one executed action, one "approve" audit row
def test_desk_crash_retried_once_then_fallback(db_session, monkeypatch)  # process_ticket raising twice → ticket "answered" with fallback reply, audit detail "fallback: desk error"
def test_auto_approve_off_keeps_pending(wired, db_session)            # default conftest → action stays "pending" (Plan 1–3 behaviour)
def test_refusal_is_published_automatically(wired, db_session, ...)   # "Should I buy HDFC Defence Fund?" → answered with the ADVICE_REFUSAL text
```

- [ ] **Step 2:** `cd api && .venv/Scripts/python -m pytest -q tests/test_auto_decide.py` → fail (no module `app.approvals.auto`).
- [ ] **Step 3:** Implement. Change the `retry` docstring to say retries come from a person or the auto-reviewer's capped weekly job.
- [ ] **Step 4:** The tests pass. Run the full suite, which must have no regressions: `.venv/Scripts/python -m pytest -q`.
- [ ] **Step 5: Commit** `feat(approvals): reviewer agent auto-approves passing replies; blocked drafts get a fixed fallback`.

---

### Task 1b: Never answer advice or off-topic (banking etc.) questions

The user asked for this on 2026-11-18: "asking for suggestions on advice on banking and stuff… we don't want any questions like that to be answered."

**Files:**
- Modify:
  - `api/app/intent/classifier.py` (advice phrasings);
  - `api/app/desk/templates.py` (`OUT_OF_SCOPE_REPLY`);
  - `api/app/desk/orchestrator.py` (an `out_of_scope` intent → disposition `"refuse"` with `OUT_OF_SCOPE_REPLY`);
  - `api/app/api/public.py` (`notice` for `out_of_scope` too);
  - `web/lib/labels.ts` + `web/components/ask/ScopeNotice.tsx` (the notice text per intent).
- Test: `api/tests/test_off_topic.py`, `web/lib/labels.test.ts`

**Interfaces:**
- `templates.OUT_OF_SCOPE_REPLY` = "We only answer factual questions about HDFC mutual funds on Groww. We can't help with banking, loans, cards, insurance or other products, and we never give advice."
- `classify_intent` maps these phrasings to `advice_request`, before any scheme or fee rule:
  - "is it a good idea";
  - "is it worth";
  - "which … should I";
  - "best … (fund|bank|card|fd|loan|plan|scheme|investment)";
  - "recommend";
  - "where should I invest";
  - "what should I (buy|invest|do)".
- Questions about banks, loans, credit cards, insurance, tax filing, stocks or crypto, with no HDFC mutual fund scheme named, are `out_of_scope`.
- `labels.scopeNotice(intent)` returns the advice/performance notice (Plan 3 copy) or `OUT_OF_SCOPE_NOTICE` (the same text as `OUT_OF_SCOPE_REPLY`) for `out_of_scope`. It is shown immediately on the confirm card.

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.parametrize("q", ["Which bank gives the best FD rate?", "Should I take a personal loan from HDFC Bank?",
    "Is it a good idea to open a savings account in HDFC Bank or SBI?", "Which credit card should I get?",
    "Where should I invest 1 lakh?", "Is HDFC Mid Cap worth it?", "Recommend a good tax saving plan"])
def test_advice_or_off_topic_never_answered(wired, db_session, q)   # draft.disposition == "refuse"; reply is ADVICE_REFUSAL/PERFORMANCE_REFUSAL/OUT_OF_SCOPE_REPLY exactly; no citation to a scheme fact
def test_off_topic_gets_immediate_notice(wired)                       # /api/ask "Which bank gives the best FD rate?" → notice == OUT_OF_SCOPE_REPLY
def test_fund_fact_questions_still_answered(wired, db_session)        # "What is the exit load of HDFC Mid Cap?" → disposition "reply"
```

  Plus vitest: `scopeNotice("out_of_scope")` and `scopeNotice("advice_request")`.
- [ ] **Steps 2–4:** fail → implement → pass. Run the full API suite: existing intent tests must stay green, and any that change are a ruling in the ledger.
- [ ] **Step 5: Commit** `feat(desk): refuse advice and off-topic (banking, loans, cards…) questions with fixed replies`.

---

### Task 2: Automatic weekly delivery with capped hourly retry

**Files:**
- Modify:
  - `api/app/approvals/auto.py`;
  - `api/app/scheduler.py`;
  - `api/app/api/console.py` (`_run_in_background` delivers too).
- Test: `api/tests/test_auto_deliver.py`

**Interfaces:**
- Produces:
  - `auto.auto_deliver(db, run_id: int) -> list[Action]`. It approves the run's `doc_append` and then its `email_draft` (both `pending`) with `AUTO_ACTOR`, and returns them. It runs only when the run's status is `awaiting_approval`.
  - `auto.retry_failed_deliveries(db, *, max_attempts: int = 6) -> int`. For each `failed` action of type `doc_append`/`email_draft` whose number of `retry` audit rows by `AUTO_ACTOR` is below `max_attempts`, it calls `retry(db, id, AUTO_ACTOR)`. It returns the number retried.
  - `auto.weekly_and_deliver(db, now) -> WeeklyRun`, which is `start_run` + `run_weekly` + `auto_deliver` when `auto_approve` is set.
- Scheduler:
  - `_weekly_job` uses `weekly_and_deliver`;
  - new job `delivery_retry`, `CronTrigger(minute=5)`, hourly.
- Console `POST /weekly/run` background thread delivers too.

- [ ] **Step 1: Failing tests** (fake executors via `monkeypatch.setitem(EXECUTORS, "doc_append", ...)`, never real MCP)

```python
def test_successful_run_delivers_doc_then_email(corpus, monkeypatch)   # order of executor calls == ["doc_append", "email_draft"]; explainer becomes canonical
def test_failed_run_delivers_nothing(corpus, monkeypatch)
def test_retry_caps_at_six_attempts(db_session, monkeypatch)           # always-failing executor: 8 calls of retry_failed_deliveries → executor called 6 times
def test_retry_ignores_reply_actions(db_session, monkeypatch)          # a failed reply_publish is not touched
def test_scheduler_registers_hourly_retry(monkeypatch)                 # scheduler_enabled → job ids include "delivery_retry"
```

- [ ] **Steps 2–4:** fail → implement → pass, plus the full suite.
- [ ] **Step 5: Commit** `feat(weekly): deliver the pulse automatically and retry failed Google writes hourly (max 6)`.

---

### Task 3: Public weekly summary and answer checks

**Files:**
- Modify: `api/app/api/public.py`
- Test: `api/tests/test_public_summary.py`

**Interfaces:**
- `GET /api/weekly/summary` returns `404 {"detail": "no weekly pulse yet"}` when there's no successful run, else:

```json
{"week_ending": "2026-11-17", "window_start": "...", "window_end": "...", "stale": false,
 "review_count": 3007, "themes": [{"label": "...", "count": 12, "recent_count": 3}],
 "quotes": [{"text": "...", "theme": "..."}], "repeated": [{"label": "...", "count": 6}],
 "explainer": {"title": "...", "bullets": [{"text": "...", "url": "..."}], "last_checked": "..."} | null,
 "delivery": {"doc": "delivered|pending (retrying)|failed — sign-in expired|failed|not started",
              "email_draft": "<same words>"}}
```

  - **Which run:** the latest run whose status is not `failed` or `running`. Today that is `awaiting_approval`, because the run status does not change after delivery.
  - **Stale:** `stale` is true when `week_ending` is more than 7 days before today.
  - **Quotes:** parsed from `pulse_text` lines `- "<text>" (rv_…)`. The id is dropped.
  - **Explainer:** the current canonical explainer for the run's fee topic, else the run's own.
- `GET /api/tickets/{code}` gains a `"checks"` block, filled only when answered, else `null`:

```json
{"agents": ["facts","pattern","compliance","reviewer"], "review": "pass", "checks": ["citation","scope","pii","length"],
 "citation": "...", "last_checked": "...", "reused_explainer": 4 | null, "fallback": null | "<plain reason>"}
```

  These are read from the **executed** draft. The checks list is the reviewer's check names, and `fallback` comes from `routing_why` when the disposition is `fallback`.

- [ ] **Step 1: Failing tests**

```python
def test_summary_404_without_runs(client)
def test_summary_uses_last_successful_run(client, db_session)   # run A delivered, run B failed later → week_ending of A
def test_summary_marks_stale_week(client, db_session)           # week_ending 10 days ago → stale True
def test_summary_has_no_private_fields(client, db_session)      # no "rv_", no "@", no PULSE_DOC_ID value, no "recipient" key anywhere in the JSON text
def test_delivery_words(client, db_session)                     # executed→"delivered"; failed with 2 auto retries→"pending (retrying)"; failed after 6 with "invalid_grant"→"failed — sign-in expired"
def test_ticket_checks_only_when_answered(client, db_session)   # in_review → checks None; answered → review "pass", citation set
def test_ticket_checks_show_fallback_reason(client, db_session)
```

- [ ] **Steps 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** `feat(api): public weekly summary and per-answer checks`.

---

### Task 4: Rate limits on the public routes

**Files:**
- Create: `api/app/guard/ratelimit.py`
- Modify: `api/app/api/public.py`, `api/app/config.py`
- Test: `api/tests/test_ratelimit.py`

**Interfaces:**
- `class RateLimiter(limit: int, window_s: float, clock=time.monotonic)` with `.hit(key: str) -> bool`, a sliding window held in memory.
- `client_key(request) -> str`. It returns the first `X-Forwarded-For` hop when `trust_proxy`, else `request.client.host`.
- FastAPI dependencies `limit_ask`, `limit_preview` and `limit_voice` raise `HTTPException(429, RATE_MSG)`. `limit_ask` also applies the daily server-wide 300 cap.
- Limiters live at module level, and `reset_limits()` is provided for tests. An autouse conftest fixture calls `reset_limits()`.

- [ ] **Step 1: Failing tests**

```python
def test_eleventh_question_in_ten_minutes_is_429(client)           # 10 OK, 11th 429 with RATE_MSG
def test_window_slides(monkeypatch)                                # fake clock: after 600 s the key is allowed again
def test_forwarded_for_used_only_when_trusted(client, monkeypatch) # trust off: two XFF values share a limit; trust on: separate limits
def test_daily_cap_applies_across_clients(monkeypatch)
def test_voice_limit_three_per_minute(client, monkeypatch)
```

- [ ] **Steps 2–4:** fail → implement → pass, plus the full suite (the autouse reset keeps the other tests green).
- [ ] **Step 5: Commit** `feat(guard): rate-limit public question, preview and voice routes`.

---

### Task 5: Web — one page with inline answers

**Files:**
- Create: `web/components/ticket/ChecksPanel.tsx`
- Modify:
  - `web/app/page.tsx` (the single page; it reads `searchParams.t`);
  - `web/components/ask/AskFlow.tsx` (on submit it shows `<TicketStatus code>` inline instead of `router.push`; "Ask another question" resets);
  - `web/components/ticket/TicketStatus.tsx` (renders `ChecksPanel`);
  - `web/lib/api.ts`, `web/lib/types.ts` (`TicketView.checks`; console helpers removed).
- Replace:
  - `web/app/ask/page.tsx` → `redirect("/")`;
  - `web/app/t/[code]/page.tsx` → `redirect("/?t=" + code)`.
- Delete:
  - `web/app/console/**`, `web/components/console/**`;
  - `web/lib/session.ts`;
  - `web/e2e/console.spec.ts`;
  - the console cases in `web/lib/api.test.ts`.
- Modify `web/playwright.config.ts`: API env `AUTO_APPROVE=1`.
- Tests:
  - `web/e2e/ask.spec.ts` (paths → `/`);
  - `web/e2e/ticket.spec.ts` (`/?t=`);
  - `web/e2e/listen.spec.ts` (`/?t=GRW-HINDI1`).

**Interfaces:**
- `ChecksPanel({checks}: {checks: Checks})` is a `<details>` labelled "How this was checked". It lists the agents, "Review: passed", the checks, a source link with its last-checked date, "Reused fee explainer #N", or the plain fallback reason.
- `Checks` type mirrors the Task 3 JSON.

- [ ] **Step 1: Failing Playwright tests:**
  - `ask.spec.ts::typed question is answered on the same page`: type, Continue, Send, then the URL stays `/` (or `/?t=…`) and the "Answer" region contains "Last checked" within 45 s;
  - `ticket.spec.ts::how this was checked`: expand it and see "Review: passed" and a source link;
  - `ask.spec.ts::rate limit message`: route-mock `/api/ask` with 429 + RATE_MSG and see the message, with the textbox still editable;
  - `/console` returns 404.
- [ ] **Steps 2–4:** fail → implement → pass. Run `npx vitest run`, `npm run build` and `npx eslint lib components app e2e` clean.
- [ ] **Step 5: Commit** `feat(web): single page — ask, inline checked answer, listen; console pages removed`.

---

### Task 6: Web — weekly section

**Files:**
- Create: `web/components/weekly/WeeklySection.tsx`
- Modify: `web/app/page.tsx`, `web/lib/api.ts` (`weeklySummary()`), `web/lib/types.ts` (`WeeklySummary`)
- Test: `web/e2e/weekly.spec.ts`, `web/lib/labels.test.ts` (`weekHeading`)

**Interfaces:**
- `labels.weekHeading(weekEnding: string, stale: boolean): string` returns "This week · week ending 17 Nov 2026" when not stale, else "Latest pulse · week ending 3 Nov 2026".
- `WeeklySection` loads once on mount. It renders:
  - top 3 themes with counts;
  - quotes;
  - "Asked repeatedly";
  - the fee explainer with official links and "last checked";
  - a delivery line ("Google Doc: delivered · Gmail draft: delivered", or the Task 3 status words).

  A 404 shows "The first weekly pulse hasn't run yet."

- [ ] **Step 1: Failing tests:**
  - vitest `weekHeading` (both forms);
  - Playwright `weekly.spec.ts::weekly section shows the seeded pulse`: ≥1 theme, ≥1 quote, explainer bullets with links, delivery line present;
  - `weekly.spec.ts::no pulse yet`: route-mock 404 and see the message.
- [ ] **Steps 2–4:** fail → implement → pass, plus build.
- [ ] **Step 5: Commit** `feat(web): weekly pulse section on the main page`.

---

### Task 7: Regression, docs, live check

**Files:**
- Modify:
  - `web/README.md` (one page; no console);
  - `CLAUDE.md` (Status and Run it: auto-approval, `AUTO_APPROVE`, `TRUST_PROXY`, token renewal before Mondays);
  - the amendment spec's status line ("implemented in Plan 3b").

- [ ] **Step 1:** Full API suite, `npx vitest run`, `npm run build`, `npx playwright test`. All must be green.
- [ ] **Step 2: Live check** (real `.env`, API :8000, `npm run dev` :3000):
  1. Typed English: answered inline with no human step; "How this was checked" shows the review and source.
  2. Hinglish: the Hindi answer shows inline.
  3. "Should I buy…": scope notice, then the refusal published.
  4. Spoken clip (SAPI wav via curl) → preview.
  5. `curl POST /api/console/weekly/run` with the key → after the run, the weekly section shows the new week. Delivery is "delivered" if the Google token is valid, otherwise "pending (retrying)".
  6. The log grep for the test PAN and phone returns 0.
- [ ] **Step 3: Commit** `docs: single-page autonomous desk — how to run`.
- [ ] **Step 4: CHECKPOINT:** the user tries `http://localhost:3000/` themselves and signs off.

---

## Not in this plan

- Deploy to Railway + Vercel, evals, `/health` MCP handshake: Plan 4.
- Google service account for the Doc (design option (b)): stretch goal, after Plan 4.
- Plan 3 deferred minors (Plan 3 ledger).

## Self-Review Notes

**Spec coverage:**

| Design section | Task |
|---|---|
| §A auto replies + fallback + crash retry | 1 |
| §B auto weekly delivery + hourly retry | 2 |
| §C page, inline answer, checks panel | 3, 5 |
| §C weekly section and delivery status | 3, 6 |
| §C removal of console and `/t` | 5 |
| §E rate limits | 4 |
| Decided (a)+(c): token status words | 2, 3, 6 |
| §D spec/plan text changes | 7 |

**Type consistency:**
- `AUTO_ACTOR` is defined in T1 and used in T2.
- Task 3's `checks` JSON is the `Checks` type in T5.
- Task 3's summary JSON is the `WeeklySummary` type in T6.
- The rate-limit message is the same string in T4 (`RATE_MSG`) and the T5 e2e test.
