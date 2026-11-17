# Plan 2 — Manual Data Verification (user requirement)

The user will manually check and verify the Plan 2 data before it is accepted. Plan 2 must include a task that
produces the material below, and execution must pause for the user's check after the live smoke run.

## Deliverable: `api/scripts/verify_weekly.py`

Run: `cd api && .venv/Scripts/python scripts/verify_weekly.py [--run-id N]` (default: latest weekly run).
Writes `api/data/verify/weekly-run-<id>.md` (git-ignored) — one readable page, no DB tool needed.
Read-only: never writes to the DB, never calls an LLM or the network.

Sections, each pairing a claim with its evidence:

1. **Run summary** — run id, status, review window (start–end), reviews fetched/kept, LLM-labelled count.
2. **Themes** — for each theme (≤5): label, count, 7-day count, window, and the full list of review ids;
   the script recounts the ids from the `reviews` table and prints `count OK` / `count MISMATCH`.
3. **Quotes** — each pulse quote next to the full redacted text of the review id it cites, with
   `verbatim OK` / `NOT FOUND` (quote, minus a trailing `…`, must be a substring of that review).
4. **Repeated questions (Link 1)** — each key shown in the pulse with its count, window, and the ticket
   codes + redacted questions behind it; plus every key at 3–4 occurrences (near misses) to confirm
   they were correctly excluded.
5. **Fee confusion** — chosen topic, matching review ids and ticket codes.
6. **Explainer** — each bullet next to its cited URL, the source's `last_checked`, and the exact sentence
   from the stored source text it came from (`source OK` / `NOT IN SOURCE`); distinct official URL count
   (must be ≥2); bullet count (≤6).
7. **Caps & scope** — pulse word count (≤250), explainer bullets (≤6), and `check_output` results.
8. **Pending actions** — for each `doc_append` / `email_draft` action: id, status, target, and the exact
   content that would be written.
9. **PII sweep** — scans every text column of `reviews`, `tickets`, `drafts`, `themes`, `explainers`,
   `actions`, `audit_log` and `api/data/*.log` / server log with `find_pii`; lists any hit (expected: none).

## Manual checklist (printed at the end of the report)

- [ ] Open 3 quotes' review ids and confirm the text matches.
- [ ] Spot-check 2 themes: count equals the number of listed ids; window is stated.
- [ ] Open each explainer URL in a browser; confirm the bullet's sentence is on the page and the date is today's check.
- [ ] Confirm a key with ≥5 questions in 7 days is in the pulse and a key with 4 is not.
- [ ] Confirm no names, phone numbers, PANs or emails appear anywhere in the report.
- [ ] Read the pending Doc/Gmail content — it is exactly what you'd approve.

## Tests (TDD, in the same task)

- Report flags `count MISMATCH` when a theme's stored count ≠ its id list.
- Report flags `NOT FOUND` for a quote that isn't a substring of its review.
- Report flags `NOT IN SOURCE` for an explainer bullet absent from its source text.
- PII sweep reports a planted PAN in a test row, and reports none on clean data.

## Execution checkpoint

After Plan 2's live smoke run, generate the report and stop for the user's manual verification before
opening the Plan 2 PR. Any issue the user finds becomes a RED→GREEN fix before the PR.
