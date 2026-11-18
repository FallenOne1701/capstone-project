# One page, a person approves — design (Plan 3c)

Date: 2026-11-18 · Status: approved for planning · Amends `2026-11-18-single-page-autonomous-desk-design.md`, which amends `2026-11-17-support-desk-design.md`. Both stay binding wherever this doc is silent.

## Intent

The assignment brief requires that **a human approves, edits or rejects each draft, and nothing is written or sent without a human approving that specific action**. Plan 3b replaced the human with an automatic approver, which breaks that rule. Plan 3c brings the human gate back, **on the same single public page**: graders still open one link, and the person approving is whoever is using that page. This copies the user's M3 app, where one workbench page holds the draft and an "Approve draft" button that stays disabled until the reviewer passes.

## Goals

- One URL (`/`) with three sections, in this order: **Ask**, **Queue**, **This week**.
- No reply is published and no Google write happens without a click on that page, unless the off-by-default auto mode is switched on.
- Every click is audited with actor `page`.
- The approval screen says exactly what will be written and where.

## Non-goals

- Login or a password. The brief doesn't require one (the user's decision).
- Sending email. It stays an **unsent Gmail draft**, and `gmail_send_email` stays denylisted.
- Deploying. That's Plan 4.

## Anti-goals (a failure even if it "works")

- A reply reaches the asker, or a Google write happens, without a human click while `AUTO_APPROVE=0`.
- Approve is clickable on a draft the reviewer blocked.
- A rejected ticket leaves the asker waiting forever ("in review" with nobody coming).
- The page shows personal data: unredacted questions, the full recipient email, or tokens.

## Approaches

1. **Chosen: new open endpoints `/api/desk/*` that call the existing approval service** (`approve`, `edit_draft`, `reject`, `retry`, reprocess, weekly run, queue, sources, explainers). They are audited as actor `page` and rate-limited. The password-protected `/api/console/*` stays unchanged for its existing tests and operators.
2. *Rejected:* removing the password from `/api/console/*`. It's less code, but "console" would mean two things, and about 40 tests that check the password is enforced would need rewriting.
3. *Rejected:* separate approval pages, or rebuilding approval in the web app. The user wants one page, and the service is already built and tested.

## Design

### Settings
- `AUTO_APPROVE` default becomes **0** (`config.py`). Auto mode keeps working when it's set to 1, and the README documents it as an optional design choice.
- With auto mode off, the scheduler still builds the weekly pulse every Monday, but the Doc and Gmail actions wait for a click. Hourly auto-retry only runs in auto mode.

### Ask section (as today, plus)
- Answers appear inline once someone approves them, with Listen and the "How this was checked" panel.
- While a reply waits, the asker sees "Waiting for a person to approve this answer" instead of a bare "in review".
- **Rejected:** the asker sees **"We couldn't answer this one."** plus an **"Ask again"** button (user's choice B).
  - On the same page visit, "Ask again" refills the box with exactly what they typed.
  - Arriving later via the ticket link, the box starts empty, because the server only holds the redacted text.
  - Resubmitting creates a new ticket.
- The ticket gets a new status `closed`, set when a reply action is rejected. It's a new string value only; there's no schema change.

### Queue section (restored Plan 3 console Queue)
- Each ticket in the queue shows:
  - the redacted question;
  - the draft reply (English, plus Hindi when present);
  - the citation and its last-checked date;
  - the reviewer's result and flags;
  - the routing note.
- Buttons:
  - **Approve**, disabled unless the reviewer passed;
  - **Edit**, which saves the new text and re-runs the reviewer;
  - **Reject**, which closes the ticket.
- **Re-run desk** for failed tickets.
- Pending items come first, then the most recent decisions.
- Reuse `QueueItem.tsx`, `ActionButtons.tsx` and `ActionCard.tsx` from `git show a51acef^:web/components/console/…`, pointed at `/api/desk/*`.

### This week section
- What the section shows today: themes with counts, the window and review ids, quotes, repeated questions, the fee explainer.
- Also shown:
  - the canonical explainers being reused;
  - sources with last-checked dates.
- An **approval list** where each row states the exact write:
  - "Append to the weekly pulse Google Doc (`<doc id>`)", with a preview of the text;
  - "Gmail draft to the product team (`d***@…`), not sent", with the subject and a preview of the body.

  Each row has **Approve / Reject**, plus **Retry** when it failed (the error is shown in plain words).
- **Run weekly now** button: at most once an hour, server-enforced. It shows "running…", then the new pulse.

### API
- `/api/desk/*`: the same operations as `/api/console/*`, no password, actor `page`.
- Rate limits: action endpoints 30 per 10 minutes per visitor; weekly run once an hour globally. They reuse `app/guard/ratelimit.py`.
- The recipient email is always masked in responses.

### Tests and evals to keep in mind
- With `AUTO_APPROVE=0`, nothing publishes and nothing writes until approve. One approve changes exactly the action, its target and one audit row (this feeds Plan 4's edit-isolation eval).
- Approve on a blocked draft is refused (HTTP 409).
- Reject → ticket `closed` → the asker sees the message and "Ask again".
- Playwright: ask → queue shows it → approve → the answer appears in the Ask section. Weekly approve uses fake executors, never real Google, in e2e.

## Calls made by Claude (user may override)
- Section order: Ask → Queue → This week.
- Rate limits and the once-an-hour weekly run.
- The new `closed` ticket status and the "Waiting for a person to approve" wording.
- `/api/console/*` kept, not removed.

## Left to the builder
- Exact component split and styling. Follow the existing Stitch tokens.
- Whether the Queue polls or refreshes after each click. Either is fine.
- Plan 3b's Important 3 ("in_review tickets never auto-decided") is moot with auto mode off. With auto mode on, it stays a known limit noted in the ledger.
