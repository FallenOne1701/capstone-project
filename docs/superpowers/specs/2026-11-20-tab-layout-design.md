# Plan 5 — Tab layout from the Stitch design

Date: 2026-11-20. Branch `plan-5-tabs`. Builds on the single page from Plans 3b/3c (`web/app/page.tsx`).

## Intent and why
The live page (https://groww-support-desk.vercel.app) is one narrow column (`max-w-2xl`) with three stacked blocks: Ask, Queue, Weekly pulse. The user wants it to **look professional and neat**, and wants a **grader to find every required screen in one click** (graded on Voice UX & intent 25%, and the brief requires: queue view, weekly pulse view, sources panel, approval screen showing exactly what is written where, canonical explainers view).

The look comes from the user's Google Stitch design: `C:/Users/dhruv/Downloads/stitch_hdfc_mutual_funds_support_desk/` (`screen.png` = Ask tab; `code.html` = all three tabs, Tailwind + Lucide). It is a **re-layout**: almost every card in the design already exists as a component.

## Goals
- Header: "Support Desk" + "HDFC Mutual Funds" tag (left); green chip "● A person approves every answer" (right). Below it a tab bar: **Ask** | **Queue** (count badge) | **This week** (dot when a weekly approval is waiting).
- Wide layout (max width ~1280px, as in the design) with the design's spacing, card style, borders and rounded corners.
- **Ask tab**: page title "Ask about HDFC mutual funds" + subtitle. Two columns on desktop:
  - Left: the question box (textarea, mic inside it, char counter, Continue) and, after Continue, the confirm card ("Review & Privacy Guard": masked question, Edit question / Send question).
  - Right: before any question, a **"How it works"** card (the 4 steps; answers come only from official HDFC / AMFI / SEBI pages; a person approves every answer) plus **3 example questions** that fill the question box when clicked. After sending: the ticket card (code, status pill, **4-step progress**, answer card with source link and "last checked" date), or the "We couldn't answer this one." card with Ask again.
- **Queue tab**: title + filter chips **Waiting / Answered / Closed** (default Waiting), then the existing queue cards (review pass/blocked badge, question, draft, Approve / Edit / Reject, inline edit), restyled to the design. Empty state card per filter.
- **This week tab**: title + "Run weekly now" button; the pulse card (see call 1 below); "Waiting for your approval" with the two action cards (Doc append, Gmail draft — exactly what is written where); error state with Retry; then **Fee explainers** and **Sources** as foldable sections, open by default.
- 4-step progress on the ticket: **Received → Checked → Waiting for a person → Answered**.
  - `received` → step 1 current.
  - `in_review` → steps 1-2 done, step 3 current ("Waiting for a person"; when the ticket's `approval` is `auto`, step 3 reads "Approving").
  - `answered` → all done.
  - `closed` / `failed` → no progress bar (as today).

## Non-goals
- No API or backend changes. The queue endpoint already returns waiting tickets first, then the newest decided ones (limit `QUEUE_SIZE`), so the filters work in the browser.
- No new behaviour beyond: tabs, filters, How-it-works + example questions, the 4th progress step.
- No password, no change to approval rules (anyone on the page can approve; Google writes only append / draft).
- No Next.js upgrade.

## Anti-goals (a failure even if it works)
- **Copying invented content from the mock**: "Section 4.2", the Slack "#wealth-ops" failure card, the fake recipient `mf-product-ops@internal.platform`, the fake Doc filename, "32% of tickets", "Executive Summary (188 words)", PAN/Folio examples that we don't actually mask that way. Everything shown must come from our real data and existing labels.
- Losing state when switching tabs (typed question, open ticket, open edit box).
- Breaking the safety rules: Approve still disabled until the reviewer passes; approve still sends the reply text seen (409 otherwise); weekly cards still show the exact text and destination.
- Breaking phone use: no sideways scrolling at phone width.

## Constraints
- Next 16.4.2 + Tailwind v4 tokens in `web/app/globals.css` (Inter body, Geist headlines, JetBrains Mono codes; primary `#006c4f`). Same colours and fonts as now; the design uses the same fonts.
- Icons: the design uses Lucide. Use `lucide-react` only if it is cheap to add; otherwise small inline SVGs. (Builder's call.)
- TDD; vitest (48 today) and Playwright (20 today) must pass; e2e specs that scroll the stacked page get updated to click tabs.
- Deployed page is Vercel (`fallenone1701`, team `bomba8`); a redeploy is needed at the end (steps in `web/README.md` → "Deployed").

## Approaches considered
- **A. Tabs inside one page (chosen by the user).** All three tab panels stay mounted; only the visible one is shown. The address carries the tab (`/?tab=queue`, `/?tab=week`; Ask is the default and `/?t=CODE` opens Ask with that ticket). Switching never loses state; the Queue badge stays live from any tab. Cost: all three load at once — fine at our size.
- **B. Three separate pages** sharing a header. Clean addresses, but every tab click reloads, a half-typed question is lost, and the live badge needs extra work.
- **C. Keep the long page + a tab bar that scrolls.** Cheapest, but still the long scroll the user wants gone.

## Decided
- Approach A; tab in the URL via `router.replace` (no scroll jump); a reload keeps the tab.
- 4-step progress as above.
- Ask tab right column empty state = How it works + 3 clickable example questions (they fill the box; the person still presses Continue).
- Queue filters Waiting / Answered / Closed, done in the browser (Waiting defined in call 3).
- On phones: columns stack (left then right), tab bar stays at the top and fits without sideways scroll.

- **Fee explainers and Sources start open** (user, 2026-11-20): both are required screens and the grader should see them in one click. They sit at the bottom of the This week tab, below the pulse and approval cards; each can still be folded.

## Calls made after the builder check (Claude's calls, for the user to check)
1. **This week content = everything the pulse shows today, restyled.** Keep: week heading with review count and date range, Top themes (as cards with count), What users said (quotes listed on their own, not forced one-per-theme), Asked repeatedly, this week's fee explainer with source links and "last checked", and the "Google Doc: … · Gmail draft: …" status line. "Asked repeatedly" and the explainer are where the two loops visibly link, so they stay. **No separate "summary" block** is invented; the design's "Executive Summary" is dropped. Data sources stay as today.
2. **Ask tab, left vs right:**
   - The confirm card appears **below** the question box (as in the mock). Editing the box after Continue hides the confirm card again until Continue is pressed (today's rule: changed text must be checked again).
   - After Send, the right column shows the ticket and the left column **clears to an empty box**, ready for another question. The URL gets `?t=CODE`.
   - Sending a new question replaces the ticket on the right once the new ticket code comes back.
   - Arriving by `/?t=CODE`: empty box on the left, that ticket on the right.
   - "Ask again" (on a closed ticket) puts that ticket's question back in the box and clears the right column to How it works. The separate "Ask another question" button is removed: the empty box is always there.
3. **Queue badge = the Waiting count.** Waiting = everything that is not `answered` and not `closed` (pending approval, `received`, `failed`, and any `in_review` ticket whose action is no longer pending). So no ticket can drop out of every filter.

## Left to the builder
- Component split (e.g. a `DeskTabs` shell; reuse `AskFlow`, `ConfirmCard`, `TicketStatus`, `QueueItem`, `WeeklySection`, `WeeklyApprovals`, `ExplainersList`, `SourcesList`). `AskFlow` currently renders the ticket in place of the form; it needs to place the ticket in the right column instead.
- Where the Queue count comes from (one shared poll used by both badge and Queue tab is preferred over two polls).
- What the "This week" dot keys off (a weekly action pending approval).
- Exact accessible markup for tabs (`role="tablist"`/`tab`/`tabpanel`, arrow keys).
- Which 3 example questions — must be ones the live desk answers well (e.g. from `docs/samples/sample_qa.md`: expense ratio of HDFC Mid Cap Fund; minimum SIP for HDFC Small Cap Fund; plus one how-to).
- Old `/ask` and `/t/[code]` redirects keep working.
