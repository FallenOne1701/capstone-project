# Single-page autonomous support desk — design

Date: 2026-11-18 · Status: implemented in Plan 3b · Amends `2026-11-17-support-desk-design.md` (that spec stays binding wherever this one is silent).

## Intent

Graders open **one link**. That page must work by itself as an AI support desk for Groww / HDFC mutual funds:

- People ask a question (typed or spoken) and get a checked, cited answer **without a human approving it**.
- The same page shows the **weekly review picture**: themes from Play Store reviews, real quotes, repeated questions, and the fee explainer.
- The weekly loop **refreshes itself every week**. It pulls fresh reviews, rebuilds themes and the explainer, appends the pulse to the Google Doc and creates an **unsent** Gmail draft, all without a person.

Today these are split. There is a public `/ask` page with a separate `/t/<code>` status page, plus a password-protected `/console` where a human approves every reply and every Google write. This design merges the public pages into one, and replaces the human approver with an automatic one.

## Goals

- One public URL (`/`) that does everything: ask by voice or text, see the answer inline, listen to it, and see this week's pulse.
- No human step anywhere in normal operation, whether for an answer or for the weekly Google Doc and Gmail draft.
- Nothing unsafe is ever published. An answer that fails any automatic check is never shown. The person gets a fixed safe reply instead.
- The page shows how each answer was checked, so graders can see the agents at work.
- Everything stays recorded. Every automatic decision is in the audit log with actor `auto-reviewer`.

## Non-goals

- Actually sending email. The weekly email stays an **unsent Gmail draft**, and `gmail_send_email` stays denylisted.
- A staff or admin page. The console web pages are removed.
- Putting it online. That is Plan 4, which comes immediately after; this design must work there unchanged.

## Anti-goals (a failure even if it "works")

- An answer containing advice, return figures, personal data, a wrong or uncited fact, or a non-official link reaches the person.
- The page shows an unverified draft, even briefly.
- A Google write happens with content that failed validation.
- The weekly section silently goes stale, for example while showing last month's pulse as "this week".

## Constraints

- Keep the approval machinery (`Action`, `_claim`, `approve`, `retry`, audit log, executors). Approval becomes automatic, not removed (option 1, chosen by the user).
- DB changes are additive only (new tables are allowed; no new columns on existing tables).
- `USE_LLM=0` keeps every test offline.
- Grading weights from CLAUDE.md:
  - Voice UX 25%
  - MCP usage 20%
  - Grounding 15%
  - Evals 20%
  - Workflow automation 10%
  - Deployment and code quality 10%
- **Google OAuth refresh token expires every 7 days.** The OAuth app is stuck in Testing because of the restricted Gmail scope, so an unattended Monday run will fail once the token is older than 7 days. See *Open question 1*.

## Approaches considered

1. **Agents approve through the existing approval pipeline. Chosen by the user.** The reviewer agent's pass becomes the approval. Every action is still created, claimed, executed, audited and retryable. This keeps Link 2 (an approved explainer becomes canonical) and the evals' approval invariants, and it is the smallest change to tested code.
2. **Remove approvals; publish and write directly.** Less code, but it loses the audit trail, retries and the Link 2 trigger, and rewrites tested code. Rejected.
3. **Agents approve, plus a hidden staff page for overrides.** The user does not want a second page. Rejected.

## Design

### A. Automatic approval of replies

When the desk finishes a ticket (`process_ticket`), a new `auto_decide(db, draft)` step runs in the same job.

- **If every check passed**, it calls the existing `approve(db, action_id, actor="auto-reviewer")`. That executes `reply_publish`, so the ticket becomes `answered`. Passing means:
  - `draft.review_status == "pass"`;
  - the reply has its citation, or it is a fixed refusal or account template.
- **If the reviewer blocked the draft**, the original draft is kept for the record. It does not go out. Instead:
  - a new **fallback draft** is created from a fixed template (no LLM): "We couldn't confirm an answer to this from official sources. You can find {scheme}'s official details here: {scheme URL}". The scheme URL comes from the registry, or the generic Groww HDFC page when no scheme is known;
  - the fallback draft is reviewed;
  - it is auto-approved and published.

  Audit detail is `fallback: <first failure check>`.
- **If the desk crashes** (ticket `failed`), the worker retries the ticket once. If it fails again, the fallback reply is published so nobody waits forever.
- Hindi translations are unchanged: they are validated at draft time, and the Hindi text is published with the reply. A fallback reply has no Hindi text unless it is a fixed template with a stored Hindi version. *Builder may add fixed Hindi versions of the fallback/refusal templates.*
- Ticket status words stay **received → in review → answered**. "In review" now means the agents are checking, and it typically lasts seconds.

### B. Automatic weekly delivery

`run_weekly` already creates `doc_append` and `email_draft` pending actions. A new `auto_deliver(db, run_id)` step runs right after a successful run.

- It approves `doc_append` first, then `email_draft`, both with actor `auto-reviewer`. Approving `doc_append` still marks the explainer canonical (Link 2).
- It runs only if `validate_pulse` and `validate_explainer` passed. That is already true whenever actions exist, because the run fails otherwise.
- **On a failed action** (expired token, MCP down):
  - the scheduler calls `retry` + `approve` every hour, up to 6 times;
  - the page's weekly section shows "Google Doc update pending (retrying)" rather than hiding the failure.
- Schedule is unchanged:
  - weekly loop, Monday 09:00 IST;
  - corpus refresh, Sunday 21:00 IST;
  - the scheduler is on whenever the server runs (`SCHEDULER_ENABLED=1` in deploy).
- If the weekly run itself fails, the page keeps showing the last successful week, labelled with its real date ("Week ending 2026-11-17"), never as "this week".

### C. The single page (`/`)

```
┌──────────────────────────────────────────────┐
│ Groww Support Desk · facts only, no advice   │
│ [🎤 Speak]  [ type your question…      ]     │
│ → We understood: Fee question · HDFC Mid Cap │
│   (one clarifying question if two funds)     │
│ → Answer (inline, polls until answered)      │
│   🔊 Listen · Show English/Hindi             │
│   ▸ How this was checked                     │
├──────────────────────────────────────────────┤
│ This week · week ending <date>               │
│  Top 3 themes (counts) · 3 real quotes       │
│  Asked repeatedly (≥5 in 7 days)             │
│  Fee explainer (≤6 bullets, official links)  │
│  ▸ Delivered: Google Doc ✓ · Gmail draft ✓   │
└──────────────────────────────────────────────┘
```

- **Ask flow.** It reuses the current compose → confirm → clarify → submit flow, voice capture and Listen. After submitting, the answer appears **inline** on the same page; there is no navigation to `/t/<code>`. The ticket code is shown small, for reference.
- **"How this was checked"** is a collapsed panel showing:
  - which agents ran (facts, pattern, compliance, reviewer);
  - the review result and the checks it ran;
  - the citation and its last-checked date;
  - whether an explainer was reused;
  - whether the fallback was used, and why, in plain words.

  It never shows PII, and the question shown is the redacted one.
- **Weekly section** data comes from a new public, read-only `GET /api/weekly/summary`. It returns only public-safe fields:
  - week ending and window;
  - review count;
  - top 3 themes with counts;
  - the quotes, already PII-safe as selected by `select_quotes`;
  - repeated questions;
  - the current canonical or latest explainer;
  - the delivery status of the doc/email actions (status words only, no recipient, no Doc id).
- **Removed:**
  - the `/console/*` pages;
  - the `/t/[code]` page;
  - the console gate and session code in the web app.

  The `/api/console/*` endpoints stay, password-protected and unlinked, because tests and operators use them. *Builder's call whether to keep `/t/<code>` as a redirect to `/`.*
- The scope notice for advice/performance questions still shows immediately, and the refusal reply still auto-publishes.

### D. What changes in the original spec and plans

- In spec §1/§3/§5/§7/§11, "human approves" becomes "the reviewer agent approves automatically. A failed review publishes a fixed safe reply instead."
- Console routes are gone. Plan 4's Evals page goes away too; eval results move to the repo and README (*builder's call*).
- **Evals (Plan 4).** The approval-isolation eval becomes "auto-approval isolation": one auto-approve changes exactly the action, its target row and one audit row. Add an eval: blocked drafts are never published (fallback instead).
- Smoke tests (§11):
  - `/` typed question → answer appears inline;
  - voice → confirm;
  - weekly section renders.

### E. Abuse limits (my call: a public, unattended page now triggers LLM calls)

- **Per-browser/IP limit:** 10 questions per 10 minutes, and 3 voice clips per minute.
- **Server-wide cap:** 300 questions per day.
- **When a limit is hit:** the page says "You've asked a lot of questions quickly — please wait a few minutes." and typing stays available. A grader trying it normally never hits these limits.
- **Built in-process**, with no new service, so it works unchanged on Plan 4's single-instance deploy.

### F. Where the work goes (my call)

- **Branch:** the same branch, `plan-3-console-voice`, as the next plan ("Plan 3b"). Plan 3 has not been pushed or merged, and this work deletes Plan 3's console pages, so one PR containing the final single-page product is cleaner than merging pages only to delete them.
- **Files:** Plan 3b gets its own plan file and ledger.

### G. Builder's other calls

- **Fallback that fails review:** it is a fixed template, so a failure is a bug. The ticket stays `failed`, it is logged, and the page shows "Something went wrong — please try again."
- **Fallback draft:** it belongs to the same ticket as a second draft, and its `reply_publish` action is the one executed.

## Left to the builder

- Exact fallback wording (fixed template, facts-only), and whether to add Hindi versions.
- The hourly retry mechanism (an APScheduler job, or a loop in the weekly job).
- Visual layout within the sketch, reusing the Stitch tokens.
- Whether `/t/<code>` redirects or 404s.

## Decided: the 7-day Google token (user, 2026-11-18)

- **(a) + (c).** The user re-runs `npm run auth` (MCP Server 1) before demos and Mondays when possible. The page shows the delivery status honestly:
  - "Google Doc update pending (retrying)" while the hourly retry runs;
  - "Google Doc update failed — sign-in expired" after the last retry, when the error indicates an auth failure.
- **(b) is a stretch goal, only if time is left after Plan 4:** a Google service account for the Doc append. It is not part of Plan 3b.
