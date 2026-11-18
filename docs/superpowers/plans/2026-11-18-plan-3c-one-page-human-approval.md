# Plan 3c — One page, a person approves — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the human approval gate back onto the single public page: Ask → Queue → This week, with nothing published or written to Google until someone clicks.

**Architecture:** A new password-free router `app/api/desk.py` (`/api/desk/*`) reuses the existing approval service (`app/approvals/service.py`) with actor `page` and in-process rate limits. `AUTO_APPROVE` defaults to off. The web page gains a Queue section and a weekly approval list, built from the Plan 3 console components restored from git (`a51acef^`).

**Tech Stack:** FastAPI + SQLAlchemy (api, pytest), Next.js 16 + Tailwind (web, vitest, Playwright).

**Spec:** `docs/superpowers/specs/2026-11-18-one-page-human-approval-design.md` (amends `2026-11-18-single-page-autonomous-desk-design.md` and `2026-11-17-support-desk-design.md`).

## Global Constraints
- `AUTO_APPROVE` default **0**. Auto mode (`1`) keeps working exactly as in Plan 3b.
- Actor for every page click: `"page"`.
- Rate limits:
  - desk actions: 30 per 600 s per visitor (`client_key`);
  - weekly run: 1 per 3600 s for everyone (`"all"`).
  - Over the limit returns 429 with a plain message.
- Ticket status set: `received | in_review | answered | failed | closed`. `closed` is a new string value only, with no schema change. DB changes are additive only.
- Rejected copy, exact: **"We couldn't answer this one."** with button **"Ask again"**.
- Waiting copy (auto off), exact: **"Waiting for a person to approve this answer."**
- Approve is disabled unless `review_status == "pass"`. The server already refuses `blocked` with 409.
- The recipient is only ever shown masked (`recipient_label()`). `target_ref` is never returned by `/api/desk/*`.
- `USE_LLM=0` keeps tests offline. e2e never reaches Google (env already blanks the keys).
- `/api/console/*` stays unchanged and password-protected.
- `gmail_send_email` stays denylisted.

## Review Focus
1. **Double click / two visitors approving the same action.** The second call must get 409, not a second Google write. `_claim` already guarantees this; pin it on the desk route (Task 2).
2. **Reject on a reply whose ticket is already answered** (auto mode raced it). The ticket must stay `answered`, never flip to `closed` (Task 1).
3. **Edit text containing a PAN or phone number.** It must be redacted before saving (`edit_draft` already redacts); pin it on the desk route (Task 2).
4. **Weekly approval when Google isn't configured** (e2e, or an expired token). The action shows `failed`, the error appears in plain words, and Retry is shown. Nothing crashes (Task 6 e2e).
5. **The asker's page left open while someone rejects in another tab.** Polling must stop on `closed` and show the message plus "Ask again" (Task 3 test).

---

### Task 1: Human mode by default; rejecting a reply closes the ticket

**Files:**
- Modify: `api/app/config.py:61`: `auto_approve: bool = False`. Update the comment.
- Modify: `api/app/approvals/service.py` (`reject`).
- Modify: `api/app/scheduler.py` (`_delivery_retry_job`): return early unless `get_settings().auto_approve`.
- Modify: `api/app/api/public.py` (`ticket_status`): add `"approval": "auto" if get_settings().auto_approve else "person"`.
- Test: `api/tests/test_human_mode.py`

**Interfaces:**
- Produces:
  - ticket status `"closed"`;
  - `GET /api/tickets/{code}` gains `approval: "auto" | "person"`.

- [ ] **Step 1: Write failing tests** in `api/tests/test_human_mode.py`. Build tickets the way `tests/test_console_queue.py` does.
  - `test_auto_approve_defaults_off`: `Settings().auto_approve is False`. Construct it with the env var removed via `monkeypatch.delenv("AUTO_APPROVE")`.
  - `test_reject_reply_closes_ticket`: ticket `in_review` + pending `reply_publish` → `reject(db, a.id, "page")` → ticket status `"closed"`, action `"rejected"`, one audit row `(actor="page", verb="reject")`.
  - `test_reject_never_reopens_answered_ticket`: the ticket is `answered`. Rejecting a stale second pending action leaves it `answered`.
  - `test_retry_job_idle_in_human_mode`: a failed `doc_append` with `auto_approve=False` → `scheduler._delivery_retry_job()` → the action is still `failed`, with 0 `retry` audit rows. Monkeypatch `app.scheduler.SessionLocal` to return the test session.
  - `test_ticket_view_says_who_approves`: `GET /api/tickets/{code}` → `approval == "person"`. Set `auto_approve=True` → `"auto"`.
- [ ] **Step 2:** `cd api && .venv/Scripts/python -m pytest -q tests/test_human_mode.py` → 5 FAIL.
- [ ] **Step 3: Implement.** In `reject`, when `a.type == "reply_publish"`, load the ticket by `Ticket.code == a.target_ref`. Set `status="closed"` only if it is `received`/`in_review`, in the same commit. Then make the config, scheduler and public edits listed above.
- [ ] **Step 4:** rerun the file → 5 passed. Also run `tests/test_approvals.py tests/test_auto_decide.py tests/test_auto_deliver.py tests/test_tickets_api.py` → all pass. The auto tests set `auto_approve=True` themselves.
- [ ] **Step 5: Commit** `feat(api): a person approves by default; rejecting a reply closes the ticket`.

### Task 2: Open desk API for the page (`/api/desk/*`)

**Files:**
- Create: `api/app/api/desk.py`
- Modify: `api/app/api/console.py`: extract `reprocess_ticket(db, code: str, actor: str) -> dict` so both routers share it. Console keeps actor `"console"`.
- Modify: `api/app/guard/ratelimit.py`: add `_desk = RateLimiter(30, 600)` and `_weekly = RateLimiter(1, 3600)` to `_fresh()`/`reset_limits()`. Add `limit_desk(request)` (per `client_key`) and `limit_weekly_run(request)` (key `"all"`). Weekly-run message: `"The weekly pulse was run in the last hour — please try again later."`
- Modify: `api/app/main.py`: `include_router(desk_router)`.
- Test: `api/tests/test_desk_api.py`

**Interfaces:**
- Consumes:
  - `ap.approve/reject/retry(db, id, actor)`, `ap.edit_draft(db, id, reply, actor)`;
  - from `console.py`: `_guard`, `_draft_out`, `_action_out`, `_explainer_out`, `_run_in_background`, `reprocess_ticket`, `queue`, `sources`, `explainers`, `weekly_latest`. The GET handlers are plain functions of `db`, so call them directly.
- Produces (prefix `/api/desk`, no key):
  - `GET  /queue`: queue items. Same item shape as console, but pending actions first, then newest, **max 30**.
  - `POST /actions/{id}/approve|reject|retry` → `{id, status, error?}`. 404/409 as in console.
  - `POST /drafts/{id}/edit` body `{reply}` → draft view.
  - `POST /tickets/{code}/reprocess` → `{code, status}`.
  - `POST /weekly/run` (202) → `{status, run_id}`.
  - `GET  /weekly/latest`, `GET /sources`, `GET /explainers`: same bodies as console.
  - Every POST has `Depends(limit_desk)`. `/weekly/run` also has `Depends(limit_weekly_run)`.

- [ ] **Step 1: Write failing tests** in `api/tests/test_desk_api.py`:
  - `test_desk_needs_no_key`: `GET /api/desk/queue` → 200 with no header. `GET /api/console/queue` with no header → 401 (unchanged).
  - `test_page_approve_publishes_and_audits_as_page`: a pending pass draft → approve → ticket `answered`. The audit has `actor="page"`, verbs `approve` and `execute`.
  - `test_second_approve_is_409`: approve twice → the 2nd is 409. `executed` audit count stays 1.
  - `test_blocked_draft_approve_is_409`.
  - `test_page_edit_redacts_pii`: edit to `"Your PAN ABCDE1234F … Expense ratio is 0.77% (source)"` → the saved reply does not contain `ABCDE1234F`.
  - `test_page_reject_closes_ticket`.
  - `test_queue_lists_pending_first_and_caps_30`: 35 tickets with one pending among older ones → `len == 30`, `[0]` is the pending one.
  - `test_weekly_latest_never_leaks_recipient`: the response JSON contains no `target_ref` key and not the raw `pulse_draft_recipient`.
  - `test_desk_action_rate_limit`: the 31st POST within the window → 429.
  - `test_weekly_run_once_an_hour`: monkeypatch `desk._run_in_background` to a no-op. 1st → 202; 2nd → 429 with the message above.
- [ ] **Step 2:** `.venv/Scripts/python -m pytest -q tests/test_desk_api.py` → FAIL (404s).
- [ ] **Step 3: Implement** `desk.py`, the console `reprocess_ticket` extraction, the limiters and the router include.
- [ ] **Step 4:** rerun → all pass. Also run `tests/test_console_queue.py tests/test_ratelimit.py tests/test_weekly_api.py` → pass.
- [ ] **Step 5: Commit** `feat(api): open desk endpoints for the page, audited as page, rate-limited`.

### Task 3: Asker side: waiting wording, closed state, "Ask again"

**Files:**
- Modify: `web/lib/types.ts`:
  - `TicketStatus` gains `"closed"`;
  - `TicketView` gains `approval: "auto" | "person"`.
- Modify: `web/lib/labels.ts`: `StatusWord` gains `"closed"`; `statusLabel("closed") → "closed"`.
- Modify: `web/components/ticket/TicketStatus.tsx`:
  - stop polling on `closed`;
  - `in_review` text: when `approval === "person"`, "Waiting for a person to approve this answer.", otherwise the current agents text;
  - on `closed`, render the rejected copy and an "Ask again" button calling `onAskAgain`. Hide `Progress` on `closed`.
- Modify: `web/components/ask/AskFlow.tsx`: remember the submitted text in `lastAsked` state. Pass `onAskAgain` to `TicketStatus`. It clears `code`, sets the box to `lastAsked ?? ""`, sets phase `compose`, and removes `?t=` from the URL (`history.replaceState`).
- Test: `web/lib/labels.test.ts`; `web/components/ticket/TicketStatus.test.tsx` (new, vitest + Testing Library, mocking `@/lib/api`). If Testing Library isn't installed, put this behaviour in Task 6's Playwright spec instead and say so in the ledger.

**Interfaces:**
- Produces: `TicketStatus({ code, onAskAgain? }: { code: string; onAskAgain?: () => void })`.

- [ ] **Step 1: Failing tests:**
  - `statusLabel("closed") === "closed"`.
  - TicketStatus with mocked `ticket()` returning `{status:"closed"}` shows "We couldn't answer this one." and an "Ask again" button. Clicking it calls `onAskAgain`.
  - With `{status:"in_review", approval:"person"}` it shows "Waiting for a person to approve this answer."
- [ ] **Step 2:** `cd web && npx vitest run` → new tests FAIL.
- [ ] **Step 3: Implement** as listed.
- [ ] **Step 4:** `npx vitest run` → all pass.
- [ ] **Step 5: Commit** `feat(web): waiting-for-a-person wording, closed tickets and Ask again`.

### Task 4: Queue section on the page

**Files:**
- Create from git (`git show a51acef^:web/components/console/<f>`), into `web/components/desk/`: `QueueItem.tsx`, `ActionButtons.tsx`, `ActionCard.tsx`. Drop all console-key/session code.
- Create: `web/components/desk/QueueSection.tsx`. It polls `deskQueue()` every 5 s (refresh right after any click via `onChange`), with heading "Queue — drafts waiting for a person". The empty state is "Nothing waiting right now."
- Modify: `web/lib/api.ts`. Add `deskQueue`, `approve`, `reject`, `retry`, `editDraft`, `reprocess`, `weeklyLatest`, `weeklyRun`, `sources`, `explainers`, all on `/api/desk/*`, with signatures as in the old file at `a51acef^` lines 70-82 (no `C` option).
- Modify: `web/lib/types.ts`. Restore `ReviewFailure`, `DraftView`, `ActionStatus`, `QueueItem`, `Action`, `Bullet`, `Explainer`, `WeeklyLatest`, `Source` from `a51acef^`.
- Modify: `web/app/page.tsx`. Insert `<QueueSection />` between the Ask section and `<WeeklySection />`.
- Test: `web/lib/api.test.ts`

**Interfaces:**
- Produces: `approve/reject/retry(id: number)`, `editDraft(id, reply)`, `reprocess(code)`, `deskQueue(): Promise<QueueItem[]>`, `weeklyLatest(): Promise<WeeklyLatest>`, `weeklyRun()`, `sources()`, `explainers()`; `ActionCard({a, onDone})`.

- [ ] **Step 1: Failing tests** in `api.test.ts` (existing fetch-mock style):
  - `approve(7)` POSTs `/api/desk/actions/7/approve` with no `X-Console-Key` header;
  - `editDraft(3,"x")` POSTs JSON `{reply:"x"}` to `/api/desk/drafts/3/edit`;
  - `deskQueue()` GETs `/api/desk/queue`.
- [ ] **Step 2:** `npx vitest run lib/api.test.ts` → FAIL.
- [ ] **Step 3: Implement** the files above. In QueueItem, keep Approve disabled with the reason "Edit it first — the reviewer blocked this draft" when `review_status !== "pass"`.
- [ ] **Step 4:** `npx vitest run` → pass. `npm run build` → ok.
- [ ] **Step 5: Commit** `feat(web): queue section — approve, edit, reject, re-run on the page`.

### Task 5: This week, plus the approval list, sources, explainers and Run weekly now

**Files:**
- Create: `web/components/desk/WeeklyApprovals.tsx`.
  - Heading "Waiting for your approval — exactly what gets written".
  - Uses `weeklyLatest()`. Renders an `ActionCard` for each `actions[]` entry, with `target_label` as the title ("Append to the weekly pulse Google Doc (…)", "Gmail draft to the product team (d***@…)" plus the suffix **", not sent"** for `email_draft`) and the content preview.
  - **Run weekly now** button: calls `weeklyRun()` and shows "Running…" while it polls `weeklyLatest()` every 5 s until `run.id` changes and its status is not `running` (stop after 10 min). A 429 or 409 shows the API's `detail`.
- Create: `web/components/desk/SourcesList.tsx` (title, kind, status, last checked) and `web/components/desk/ExplainersList.tsx` (canonical first; title, status, reuse_count, bullets with links). Logic can be restored from `a51acef^:web/app/console/sources/page.tsx` and `…/explainers/page.tsx`.
- Modify: `web/components/weekly/WeeklySection.tsx`. Under the existing pulse, render `WeeklyApprovals`, `ExplainersList` and `SourcesList` as three sub-sections. The delivery line keeps working from the summary.

**Interfaces:**
- Consumes: Task 4's api functions, `ActionCard`.

- [ ] **Step 1: Failing test** (vitest, pure helper): `actionTitle({type:"email_draft", target_label:"Gmail draft to the product team (d***@x.com)"})` → `"Gmail draft to the product team (d***@x.com), not sent"`. `doc_append` returns `target_label` unchanged. Put the helper in `web/lib/labels.ts`.
- [ ] **Step 2:** `npx vitest run lib/labels.test.ts` → FAIL.
- [ ] **Step 3: Implement** the helper and the three components, and wire them into WeeklySection.
- [ ] **Step 4:** `npx vitest run` → pass. `npm run build` → ok.
- [ ] **Step 5: Commit** `feat(web): weekly approval list, sources, explainers and run-now on the page`.

### Task 6: End-to-end in human mode, docs, full verification

**Files:**
- Modify: `web/playwright.config.ts`: `AUTO_APPROVE: "0"`.
- Modify: `web/e2e/fixtures.ts`: add `approveTicket(request, code)`, which finds the code's pending action in `GET ${API}/api/desk/queue` and POSTs approve. Remove `CONSOLE_HEADERS` if nothing uses it.
- Modify: `web/e2e/ask.spec.ts`, `ticket.spec.ts`, `listen.spec.ts`. Wherever they waited for an automatic `answered`, call `approveTicket` first. Refusal templates also need approval now.
- Create: `web/e2e/desk.spec.ts`.
- Modify: `README.md` / `CLAUDE.md` run notes: `AUTO_APPROVE` default 0; `/api/desk/*` open; auto mode as an optional design choice.

- [ ] **Step 1: Write `desk.spec.ts`:**
  - `ask then approve on the queue`: type a fee question → submit → the asker sees "Waiting for a person to approve this answer." → in the Queue section, the card with that code → click Approve → the Ask section shows the answer.
  - `reject then ask again`: ask → Reject on its card → "We couldn't answer this one." → click "Ask again" → the textbox holds the submitted text.
  - `blocked draft cannot be approved`: seed or force a blocked draft through the API if the e2e seed allows it. Otherwise assert that for any card with `review: blocked` the Approve button is disabled. Ledger Ruling if seeding isn't possible.
  - `weekly approval shows exactly where and fails safely without Google`: the weekly approval list shows the "Append to the weekly pulse Google Doc" title and the Gmail row ending in ", not sent" → Approve on the Doc row (accept the confirm dialog) → status `failed` with the plain error and a Retry button. Google is blanked in e2e.
- [ ] **Step 2:** stop any `npm run dev`. Run `npm run e2e` → the new spec fails before the fixture and spec updates are complete. Fix the old specs until everything passes.
- [ ] **Step 3: Full verification.** Run:
  - `cd api && .venv/Scripts/python -m pytest -q` → all pass (~8 min);
  - `cd web && npm test && npm run build && npm run e2e` → all pass.

  Record the counts in the ledger.
- [ ] **Step 4: Live check** (real API :8000 + web :3000, `AUTO_APPROVE` unset).
  - Ask an English fee question, approve it on the page, and the answer appears.
  - Reject a second one → closed + Ask again.
  - Do **not** approve any Google action without the user's explicit say-so.
- [ ] **Step 5: Commit** `test(e2e): human approval on the page; docs for Plan 3c`.
- [ ] **Step 6:** One fresh reviewer on the whole branch diff since `5a8a3b9`. Apply its fixes TDD-style and record them in the ledger.
