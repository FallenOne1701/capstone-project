# Plan 5 — Tab Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the one long page into a wide, tabbed desk (Ask | This week | Queue) that matches the user's Stitch design, with no backend changes.

**Architecture:** One client component `DeskTabs` keeps all three tab panels mounted and shows one; the tab lives in the URL (`?tab=week|queue`, Ask is the default; `?t=CODE` is the ticket). Pure rules (tab parsing, queue buckets, progress steps, weekly dot) live in `lib/` with vitest tests; layout behaviour is covered by Playwright.

**Tech Stack:** Next 16.4.2 (app router), React 19.3, Tailwind v4 tokens in `web/app/globals.css`, vitest 3, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-20-tab-layout-design.md`

## Global Constraints
- Tab order and names: **Ask** | **This week** | **Queue**. Build order: Ask, then This week, then Queue.
- Header copy: "Support Desk", tag "HDFC Mutual Funds", chip "A person approves every answer".
- Ask title "Ask about HDFC mutual funds"; subtitle keeps today's wording.
- Progress steps exactly: "Received", "Checked", "Waiting for a person" (or "Approving" when `approval === "auto"`), "Answered".
- Queue filters exactly: "Waiting", "Answered", "Closed"; default Waiting. Badge = Waiting count.
- Fee explainers and Sources start **open** (`<details open>`).
- No invented content: nothing from the mock's "Section 4.2", Slack card, fake recipient/filename, percentages, "Executive Summary".
- Same colours and fonts (existing tokens). Max content width `max-w-7xl` (1280px). No sideways scroll at 375px wide.
- Safety rules unchanged: Approve disabled until the reviewer passes; approve sends the reply text seen; weekly cards show exact text + destination.
- No API changes, no Next upgrade, no new runtime dependency except optionally `lucide-react` (builder's call; inline SVG is fine).
- Execution: Native (inline) + one fresh reviewer at the end (CLAUDE.md). TDD.

## Review Focus
1. **Text typed but not sent survives a tab switch** (Ask → Queue → Ask): box still holds it. Test in Task 2.
2. **Combined addresses**: `/?t=CODE&tab=queue` opens Queue and the Ask tab still holds that ticket; a junk `?tab=xyz` opens Ask. Tests in Task 1 (`parseTab`) and Task 2 (e2e).
3. **Phone width (375px)**: no sideways scroll on any tab; tab bar fits. Test in Task 5.
4. **Queue load fails** (API down): no badge number at all (never "0" or "NaN"); the Queue tab shows the error. Tests in Task 1 (`waitingCount(null)`) and Task 2 (e2e with routed 500).
5. **Approve in Queue while the Ask tab shows that ticket**: going back to Ask shows the answer without a reload. Test in Task 2 (rewritten desk e2e).

---

### Task 1: Pure rules in `lib/`

**Files:**
- Create: `web/lib/desk.ts`
- Modify: `web/lib/labels.ts` (add `progressSteps`, `EXAMPLE_QUESTIONS`)
- Test: `web/lib/desk.test.ts`, `web/lib/labels.test.ts`

**Interfaces:**
- Produces (`lib/desk.ts`):
  - `export type Tab = "ask" | "week" | "queue"`
  - `export function parseTab(v: string | string[] | null | undefined): Tab` — `"week"`/`"queue"` pass; anything else (incl. arrays → first item) → `"ask"`.
  - `export function deskHref(tab: Tab, code: string | null): string` — `"/"`, `"/?t=CODE"`, `"/?tab=queue"`, `"/?t=CODE&tab=week"` (t first; ask never written; code URI-encoded).
  - `export type QueueFilter = "waiting" | "answered" | "closed"`
  - `export function queueBucket(item: Pick<QueueItem, "status">): QueueFilter` — `answered`→answered, `closed`→closed, everything else→waiting.
  - `export function waitingCount(items: Pick<QueueItem, "status">[] | null): number | null` — null when items is null.
  - `export function weeklyNeedsYou(latest: Pick<WeeklyLatest, "actions"> | null): boolean` — true if any action with type `doc_append` or `email_draft` has status `pending` or `failed`.
- Produces (`lib/labels.ts`):
  - `export type StepState = "done" | "current" | "todo"`
  - `export function progressSteps(status: string, approval: "auto" | "person"): { label: string; state: StepState }[] | null` — null for `closed`/`failed`.
  - `export const EXAMPLE_QUESTIONS: readonly string[]` = `["What is the expense ratio of HDFC Mid Cap Fund?", "What is the minimum SIP amount for HDFC Small Cap Fund?", "How do I download my capital gains statement?"]`

- [ ] **Step 1: Write failing tests** in `lib/desk.test.ts`:
```ts
expect(parseTab("queue")).toBe("queue"); expect(parseTab("week")).toBe("week");
expect(parseTab("xyz")).toBe("ask"); expect(parseTab(undefined)).toBe("ask"); expect(parseTab(["week", "queue"])).toBe("week");
expect(deskHref("ask", null)).toBe("/"); expect(deskHref("ask", "GRW-ABC123")).toBe("/?t=GRW-ABC123");
expect(deskHref("queue", null)).toBe("/?tab=queue"); expect(deskHref("week", "GRW-ABC123")).toBe("/?t=GRW-ABC123&tab=week");
expect(queueBucket({ status: "in_review" })).toBe("waiting"); expect(queueBucket({ status: "failed" })).toBe("waiting");
expect(queueBucket({ status: "received" })).toBe("waiting"); expect(queueBucket({ status: "answered" })).toBe("answered");
expect(queueBucket({ status: "closed" })).toBe("closed");
expect(waitingCount(null)).toBeNull(); expect(waitingCount([])).toBe(0);
expect(waitingCount([{ status: "in_review" }, { status: "answered" }, { status: "failed" }])).toBe(2);
expect(weeklyNeedsYou(null)).toBe(false);
expect(weeklyNeedsYou({ actions: [{ type: "doc_append", status: "pending" } as Action] })).toBe(true);
expect(weeklyNeedsYou({ actions: [{ type: "email_draft", status: "executed" } as Action] })).toBe(false);
```
  and in `lib/labels.test.ts`:
```ts
expect(progressSteps("received", "person")!.map((s) => s.state)).toEqual(["current", "todo", "todo", "todo"]);
expect(progressSteps("in_review", "person")).toEqual([
  { label: "Received", state: "done" }, { label: "Checked", state: "done" },
  { label: "Waiting for a person", state: "current" }, { label: "Answered", state: "todo" }]);
expect(progressSteps("in_review", "auto")![2].label).toBe("Approving");
expect(progressSteps("answered", "person")!.every((s) => s.state === "done")).toBe(true);
expect(progressSteps("closed", "person")).toBeNull(); expect(progressSteps("failed", "person")).toBeNull();
expect(EXAMPLE_QUESTIONS).toHaveLength(3);
```
- [ ] **Step 2: Run** `cd web && npx vitest run lib/desk.test.ts lib/labels.test.ts` — expect FAIL (missing exports).
- [ ] **Step 3: Implement** the exports above in `lib/desk.ts` and `lib/labels.ts`.
- [ ] **Step 4: Run** `npx vitest run` — expect all pass (48 + new).
- [ ] **Step 5: Before committing, check the third example question** gets a cited answer on the live API (`POST /api/ask/preview` then local run, or pick one from `docs/samples/sample_qa.md` / `api/evals/datasets/questions.yaml` with intent `how_to_process` that passed run 7). Replace it if not.
- [ ] **Step 6: Commit** `feat(web): tab, queue-bucket, progress and weekly-dot rules`.

### Task 2: Desk header + tabs (panels hold today's components)

**Files:**
- Create: `web/components/desk/DeskTabs.tsx`, `web/components/DeskHeader.tsx`
- Modify: `web/app/page.tsx`, `web/components/desk/QueueSection.tsx` (take data as props), `web/e2e/fixtures.ts`, all `web/e2e/*.spec.ts` that use the Queue / Weekly regions
- Delete: `web/components/PublicShell.tsx` (only `app/page.tsx` uses it)
- Test: `web/e2e/tabs.spec.ts` (new)

**Interfaces:**
- Consumes: Task 1 `Tab`, `parseTab`, `deskHref`, `waitingCount`, `weeklyNeedsYou`.
- Produces:
  - `DeskTabs({ initialTab, initialCode }: { initialTab: Tab; initialCode: string | null })` — client; owns `tab` state and URL sync via `router.replace(deskHref(tab, code), { scroll: false })`; one `usePoll(deskQueue, 5000)` shared by badge and Queue panel; `usePoll(weeklyLatest, 30000)` for the dot only.
  - `DeskHeader({ tab, onTab, waiting, weekDot }: { tab: Tab; onTab: (t: Tab) => void; waiting: number | null; weekDot: boolean })` — renders header + `role="tablist"` with three `role="tab"` buttons (`id="tab-ask"` etc., `aria-controls="panel-ask"` etc., `aria-selected`), Left/Right/Home/End keys move focus and select. Badge only when `waiting` is a number > 0; its accessible text e.g. "Queue, 2 waiting".
  - Panels: `<section role="tabpanel" id="panel-<tab>" aria-labelledby="tab-<tab>" hidden={tab !== x}>`. Panel names via the tab label: "Ask", "This week", "Queue".
  - `QueueSection({ data, error, reload }: { data: QueueItem[] | null; error: string | null; reload: () => void })`.
  - `AskFlow` gets `onCode?: (code: string | null) => void` so DeskTabs knows the ticket for the URL; AskFlow stops calling `router.replace` itself.
  - `app/page.tsx` reads `searchParams.t` and `searchParams.tab` → `<DeskTabs initialTab={parseTab(tab)} initialCode={code ?? null} />`; keeps the existing metadata.
  - e2e helper `openTab(page: Page, name: "Ask" | "This week" | "Queue"): Promise<void>` in `fixtures.ts` (clicks the tab, expects it selected).

- [ ] **Step 1: Write failing e2e tests** in `e2e/tabs.spec.ts`:
  - "tabs are Ask, This week, Queue in that order and Ask is open": `getByRole("tab")` texts start with `["Ask", "This week", "Queue"]`; Ask `aria-selected="true"`.
  - "a tab survives a reload": click Queue → URL `/?tab=queue` → reload → Queue selected.
  - "typed text survives switching tabs" (Review Focus 1): fill "Your question" with "exit load?", open Queue, open Ask → box still "exit load?".
  - "ticket and tab together" (Review Focus 2): create a ticket via `createTicket`; goto `/?t=CODE&tab=queue` → Queue selected; open Ask → text `Ticket CODE` / the ticket card visible. Goto `/?tab=xyz` → Ask selected.
  - "arrow keys move between tabs": focus Ask tab, press ArrowRight → This week selected.
  - "queue down shows no badge number" (Review Focus 4): `page.route("**/api/desk/queue", r => r.fulfill({ status: 500, json: { detail: "down" } }))` → Queue tab has no digit; open Queue → alert visible.
  - "badge counts waiting tickets": create a ticket, wait for `in_review` → Queue tab text contains a digit ≥ 1.
- [ ] **Step 2: Update existing e2e** for tabs: `desk.spec.ts` tests open the Queue tab before using `region "Queue"` → now `getByRole("tabpanel", { name: "Queue" })`; open "This week" before the weekly region (`tabpanel "This week"`); `weekly.spec.ts` likewise. Rewrite "ask, then a person approves it in the queue" to: ask on Ask → open Queue → Approve → open Ask → answer region shows "Last checked" (Review Focus 5). "Ask another question" assertions move to Task 3 (button is removed there).
- [ ] **Step 3: Run** `npm run e2e -- tabs.spec.ts` — expect FAIL (no tablist).
- [ ] **Step 4: Implement** `DeskHeader`, `DeskTabs`, the `QueueSection` props change, `AskFlow` `onCode`, `page.tsx`; delete `PublicShell`. Main width `max-w-7xl px-4 sm:px-8`. Header styling per Stitch (`code.html` lines 85-120): white bar, bottom border, active tab = primary colour text + 2px primary underline.
- [ ] **Step 5: Run** `npx vitest run && npm run build && npm run e2e` — expect all pass.
- [ ] **Step 6: Commit** `feat(web): tabbed desk shell — Ask | This week | Queue with live badge`.

### Task 3: Ask tab — two columns, How it works, 4-step progress

**Files:**
- Create: `web/components/ask/HowItWorks.tsx`
- Modify: `web/components/ask/AskFlow.tsx`, `web/components/ask/ConfirmCard.tsx` (styling), `web/components/ticket/TicketStatus.tsx` (`Progress` → `progressSteps`; `onAskAgain` passes the question)
- Test: `web/e2e/ask.spec.ts`, `web/e2e/desk.spec.ts`, `web/e2e/ticket.spec.ts`, `web/e2e/listen.spec.ts`

**Interfaces:**
- Consumes: `progressSteps`, `EXAMPLE_QUESTIONS` (Task 1); `AskFlow`'s `onCode` (Task 2).
- Produces:
  - `HowItWorks({ onPick }: { onPick: (q: string) => void })` — `<section aria-label="How it works">`: the 4 step names with one line each; "Answers come only from official HDFC Mutual Fund, AMFI and SEBI pages."; "A person approves every answer before you see it."; the 3 example questions as buttons.
  - `TicketStatus({ code, onAskAgain }: { code: string; onAskAgain?: (question: string) => void })`.
  - AskFlow layout: `grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]` (stacks below `lg`). Left = question card (label "Your question", textarea with mic button inside its bottom-right, counter, Continue) and, below it when previewed, the ConfirmCard. Right = `HowItWorks` when no code, else `TicketStatus` in a card headed "Ticket CODE".
  - Behaviour (spec call 2): Send → right shows the new ticket, left box and confirm card clear; editing after Continue hides the confirm card; `onPick` fills the box and clears any preview (does not submit); Ask again → box = that question, right back to How it works, code null; the "Ask another question" button is removed.

- [ ] **Step 1: Write/adjust failing e2e tests:**
  - ask.spec "typed question is answered…": after Send expect "Your question" box to have value `""`; drop the "Ask another question" assertion; expect `getByRole("list", { name: "Ticket progress" })` to contain "Waiting for a person" while `in_review`.
  - new "example question fills the box": click the first example → box value equals `EXAMPLE_QUESTIONS[0]`; the confirm card is not shown.
  - new "the confirm card sits under the box and goes when the text changes": Continue → "Send question" visible and box still visible; type one more character → "Send question" hidden.
  - new "How it works shows before any question": `region "How it works"` visible on `/`; hidden on `/?t=CODE`.
  - desk.spec "reject … Ask again": after Ask again expect box value = the original question and `region "How it works"` visible.
  - ticket.spec and listen.spec: keep passing in the new layout (selectors only).
- [ ] **Step 2: Run** `npm run e2e -- ask.spec.ts desk.spec.ts ticket.spec.ts listen.spec.ts` — expect the new ones FAIL.
- [ ] **Step 3: Implement** HowItWorks, the AskFlow layout + behaviour, TicketStatus progress (circles with ✓ for done, ring for current, grey for todo, connecting lines; `aria-current="step"` on current), answer card styled per `code.html` lines 256-277 (source link + "Last checked" from our data only), closed card per lines 278-305 with our `CLOSED_TEXT` and `ASK_AGAIN`.
- [ ] **Step 4: Run** `npx vitest run && npm run build && npm run e2e` — all pass.
- [ ] **Step 5: Commit** `feat(web): Ask tab — two columns, How it works, 4-step progress`.

### Task 4: This week tab

**Files:**
- Create: `web/components/weekly/RunWeeklyButton.tsx` (the run + wait logic moved out of `WeeklyApprovals`)
- Modify: `web/components/weekly/WeeklySection.tsx`, `web/components/desk/WeeklyApprovals.tsx`, `web/components/desk/ActionCard.tsx` (styling), `web/components/desk/ExplainersList.tsx`, `web/components/desk/SourcesList.tsx`
- Test: `web/e2e/weekly.spec.ts`, `web/e2e/desk.spec.ts`

**Interfaces:**
- Produces:
  - `RunWeeklyButton({ onRunDone }: { onRunDone: () => void })` — same behaviour/messages as today's run button ("Run weekly now" / "Running…", 5s polling, 10-minute give-up, failure text).
  - `WeeklyApprovals({ version }: { version: number })` — reloads when `version` changes; no run button inside. Heading "Waiting for your approval".
  - `WeeklySection` order: header row (h1 "This week" + `weekHeading(...)` line + `RunWeeklyButton` right-aligned) → pulse card (review count + date range line; Top themes as a responsive grid of cards: label + count; "What users said" quote list; "Asked repeatedly"; this week's explainer with source links + last checked) → `WeeklyApprovals` (two action cards side by side on `lg`, stacked below) → `<details open>` "Fee explainers" (`ExplainersList`) → `<details open>` "Sources" (`SourcesList`). The "Google Doc: … · Gmail draft: …" status line stays.

- [ ] **Step 1: Write/adjust failing e2e tests** in `weekly.spec.ts`:
  - "weekly tab shows the seeded pulse": open This week → theme cards (`list "Top themes"` items) count ≥ 1, "Asked repeatedly" visible, "Run weekly now" button visible above the pulse.
  - new "explainers and sources are open": `getByRole("group")`/`details` "Fee explainers" and "Sources" have `open`; at least one source link visible without clicking.
  - "no pulse yet": still shows "The first weekly pulse hasn't run yet." on the This week tab.
  - desk.spec weekly approvals test passes unchanged apart from the tab.
- [ ] **Step 2: Run** `npm run e2e -- weekly.spec.ts desk.spec.ts` — new ones FAIL.
- [ ] **Step 3: Implement** the split and layout. Action cards per `code.html` lines 600-660: "Google Docs" / "Gmail Draft" tag, our existing title, destination, exact text box (mono), Reject + Approve buttons. No invented recipients or filenames: show `target_label` from the API.
- [ ] **Step 4: Run** `npx vitest run && npm run build && npm run e2e` — all pass.
- [ ] **Step 5: Commit** `feat(web): This week tab — pulse cards, approvals, explainers and sources open`.

### Task 5: Queue tab filters + phone width

**Files:**
- Modify: `web/components/desk/QueueSection.tsx`, `web/components/desk/QueueItem.tsx` (styling only), `web/components/desk/ActionButtons.tsx` (styling only)
- Test: `web/e2e/desk.spec.ts`, `web/e2e/tabs.spec.ts`

**Interfaces:**
- Consumes: `queueBucket`, `QueueFilter` (Task 1).
- Produces: QueueSection header (h1 "Queue" + line "Nothing is published until someone here approves it.") + `role="radiogroup" aria-label="Show"` chips Waiting / Answered / Closed each with its count; filter state local (default `waiting`). Empty text per filter: "Nothing waiting right now." / "No answered questions yet." / "No closed questions."

- [ ] **Step 1: Write failing e2e tests:**
  - desk.spec new "filters split the queue": create two tickets; reject one (wait for `closed`), approve the other (wait for `answered`) → Waiting chip shows neither; Answered chip shows the approved code's article; Closed chip shows the rejected one.
  - tabs.spec new "phone width has no sideways scroll" (Review Focus 3): `page.setViewportSize({ width: 375, height: 800 })`; for each tab, `expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)`; all three tabs visible.
- [ ] **Step 2: Run** `npm run e2e -- desk.spec.ts tabs.spec.ts` — new ones FAIL.
- [ ] **Step 3: Implement** filters and card restyle per `code.html` lines 310-475 (review pass/blocked badge, question, draft, Approve/Edit/Reject; inline edit unchanged in behaviour). Fix any overflow found at 375px (long codes/URLs: `break-words`/`min-w-0`).
- [ ] **Step 4: Run** `npx vitest run && npm run build && npm run e2e` — all pass.
- [ ] **Step 5: Commit** `feat(web): Queue tab filters; phone width fits`.

### Task 6: Wrap-up, review, deploy

**Files:**
- Modify: `web/README.md` (layout section), `CLAUDE.md` (status)

- [ ] **Step 1:** Look at each tab at 1280px and 375px in a real browser (Playwright screenshot to the scratchpad) next to `screen.png`; fix visual gaps that don't add invented content.
- [ ] **Step 2: Run** the full web suite: `npx vitest run && npm run build && npm run e2e` (stop any `npm run dev` first). Record counts.
- [ ] **Step 3:** Update `web/README.md` and `CLAUDE.md`; commit `docs: Plan 5 tab layout`.
- [ ] **Step 4:** One fresh reviewer (most capable model) over `main..plan-5-tabs` against the spec; fix findings (TDD), commit.
- [ ] **Step 5:** Ask the user before push / PR / merge / Vercel redeploy (steps in `web/README.md` → "Deployed"). After deploy, check the live page's three tabs and `?tab=queue`.
