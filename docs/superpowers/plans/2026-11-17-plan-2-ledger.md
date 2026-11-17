# SDD ledger — plan: docs/superpowers/plans/2026-11-17-plan-2-weekly-loop-and-links.md
Spec: docs/superpowers/specs/2026-11-17-support-desk-design.md
Setup: branch plan-2-weekly-loop (off merged main 309e6e1), in place, no worktree.
Pre-flight:
- T1→T3,T4,T8,T11,T12: models Review/WeeklyRun/Theme/Explainer + settings — consistent.
- T2→T6,T12: load_reference/reference_sentences(topic) — consistent.
- T3→T8: ingest_reviews(db, today=, fetcher=) / fetcher(p,w,m) — consistent.
- T4→T7,T8: ThemeOut(theme_id,label,count,recent_count,review_ids,window_start,window_end,rank) — consistent.
- T5→T7,T8,T11,T12: RepeatedQuestion, repeated_questions(db, now=, threshold=, days=), label_for — consistent; FeeConfusion lives in fee_topics (T5 creates file used by T6/T7/T8) — consistent.
- T6→T8: build_explainer(db, topic) / validate / render — consistent.
- T8→T9: actions source_ref "weekly_run:<id>", Explainer.run_id — consistent.
- T9→T11: console approve → executors.call_tool patched in tests — consistent.
- T10 consumes find_canonical/reuse_reply + Plan 1 process_ticket — consistent.
Task 1: Ruling: added mcp>=1.2 dependency here with the other new deps instead of in Task 9 — one install step — cost if wrong: none.
Task 1: complete (commits a9691eb..f7c9526, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_models_p2.py tests/test_health.py' → 3 passed, 18 warnings in 1.87s)
Task 2: Ruling: Plan 1 test_refresh assumed only 15 sources and its failing-fetch test hit the real network for reference pages — now counts kind=scheme + asserts 4 references, and stubs reference._download — cost if wrong: none.
Task 2: complete (commits f7c9526..8972849, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_reference.py tests/test_refresh.py' → 8 passed, 19 warnings in 50.43s)
Task 3: added test_review_ids_never_look_like_pii (2000 ids, no PII hits) beyond the plan's tests.
Task 3: complete (commits 8972849..05b332c, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_reviews.py' → 5 passed, 17 warnings in 0.15s)
Task 4: complete (commits 05b332c..2705faf, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_themes.py' → 4 passed, 17 warnings in 0.14s)
Task 5: complete (commits 2705faf..6f9d39d, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_question_keys.py tests/test_tickets_api.py' → 19 passed, 18 warnings in 12.50s)
Task 6: complete (commits 6f9d39d..9d6f0ed, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_fee_explainer.py' → 6 passed, 19 warnings in 94.41s (0:01:34))
Task 7: Ruling: pulse failed PII validation because guard/pii allowed newlines inside digit runs ('2026-11-17' + newline + '4' = 9-digit 'account') — separators now [ \t-] only; 2 clean multi-line cases added to test_pii RED→GREEN — cost if wrong: a PII number split across lines is not redacted.
Task 7: complete (commits 9d6f0ed..798459a, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_pulse.py tests/test_pii.py' → 37 passed, 17 warnings in 0.13s)
Task 8: complete (commits 47dcb2f..5454b6b, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_weekly_run.py' → 4 passed, 19 warnings in 64.71s (0:01:04))
Task 9: complete (commits 5454b6b..fee8f06, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_executors_link2.py tests/test_approvals.py tests/test_review_fixes.py tests/test_tickets_api.py' → 62 passed, 18 warnings in 19.51s)
Task 9: stdio handshake with vendored server OK (3 tools listed) using env-provided refresh token; no Google write performed.
Task 10: complete (commits fee8f06..7f27008, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_canonical.py tests/test_tickets_api.py tests/test_orchestrator.py' → 25 passed, 18 warnings in 26.25s)
Task 11: Ruling: new console endpoints appended at the end of api/console.py with their own (noqa E402) imports rather than reorganising the module — keeps Plan 1 code untouched — cost if wrong: style only. Added test_scheduler_disabled_by_default.
Task 11: complete (commits 7f27008..654cdac, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_weekly_api.py' → 6 passed, 19 warnings in 51.17s)
Task 12: Ruling: report's 'Caps & scope' runs check_output on the pulse excluding quoted review lines (same rule as validate_pulse) — user quotes may say 'sell'; they are evidence, not our advice — cost if wrong: none (quotes are separately screened in select_quotes).
Task 12: complete (commits 654cdac..4555680, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q tests/test_verify_report.py' → 4 passed, 19 warnings in 67.09s (0:01:07))
Task 13: live run 1 (3000 real reviews, 22s, 5 LLM calls) exposed 3 quality issues → fixed RED→GREEN in tests/test_live_quality.py + test_weekly_run window assert:
Task 13: Ruling: stated window = actual earliest review date (cap of 3000 covers ~10 days, not 8 weeks) — brief requires counts to state the window they cover — cost if wrong: none.
Task 13: Ruling: reviews with zero theme keywords and no LLM label are left unthemed (pulse states "N matched a theme") instead of M2's default-to-app_reliability — 2659/3000 was praise/noise — cost if wrong: smaller theme counts; plan tests test_assign/test_build_themes/test_llm_labels adjusted accordingly.
Task 13: Ruling: quotes ranked by theme keyword hits, 6–80 words, then recency — 'Angel one is good app worst' was chosen before — cost if wrong: none.
Task 13: run 3 via console API (link 1 demo: 5 phrasings of mid-cap exit-load → key surfaced in pulse, 1 one-off excluded). verify_weekly.py → 0 flags (DB + server.log PII sweep clean). CHECKPOINT: waiting for user's manual check + their approval of actions 16 (doc_append) / 17 (email_draft).
Task 13: user approved 16 (doc_append) + 17 (email_draft) → both executed; stale 6–9 rejected on user's say-so. Explainer #3 (brokerage) now canonical.
Task 13: Link 2 live: /api/ask "What is brokerage on HDFC mutual fund investments?" → GRW-MQ6WYZ draft reused_explainer_id=3, searched=['explainer:3'], cites bullet-1 URL, review pass; server.log PII grep = 0.
Task 13: Ruling: Link 2 exposed bullet 1 = page chrome + title question ("Customer Support Help and Support En हि What fees does Groww charge?") → reference_sentences drops sentences ending in '?' (RED→GREEN test_questions_and_page_chrome_are_not_fact_sentences); only brokerage page affected — cost if wrong: a fact phrased as a question is skipped. Stored explainer #3 / Doc section keep the old bullet (not rewritten); next weekly run produces a clean one.
Task 13: full suite 273 passed, 5 skipped. Remaining: user's Doc/Gmail check, fresh-context final review, fix pass, copy ledger to docs, PR.
Task 13: run 4 (after server restart onto 9de6bb8): 3007 reviews, 443 themed, 5 LLM calls, ~20s; explainer #4 bullets clean; verify_weekly → 0 flags. User approved 19 (doc_append) + 20 (email_draft) → executed.
Task 13: Doc + Gmail draft checked read-only via Google API (user asked): run 4 section at end of Doc, draft has DRAFT label only (not sent), content identical to pulse + explainer. Link 2 re-ask → GRW-E7GLEH reused explainer #4 (clean bullet). User sign-off: "you can go ahead".
Task 13: Ruling: pluralised counts ('1 question', '1 review') + doc_append label drops hard-coded 'Groww Weekly Pulse' (real Doc title is 'Weekly Groww Report'; never claim a title we didn't read) — RED→GREEN tests in test_pulse/test_weekly_run — cost if wrong: none.
Task 13: Known limit (not fixed, out of Plan 2 scope): vendored MCP google_docs_append_content is plain-text only, so markdown '#'/'##' show literally in the Doc. Candidate for Plan 3/4.
Task 13: full suite 275 passed, 5 skipped. Next: fresh-context final review.
Final review (fresh-context reviewer, 309e6e1..087e48f): verdict "with fixes" — 0 Critical, 4 Important, 11 Minor.
Final review: fixed Important 1–4 RED→GREEN in tests/test_final_review_p2.py:
- I1 older run's doc_append no longer replaces a newer canonical explainer (it becomes 'superseded').
- I2 run row inserted before the thread (POST /weekly/run returns run_id; second click → 409); 'running' rows failed as interrupted at startup; scheduler skips while one is running.
- I3 doc_append executes against action.target_ref (the Doc shown); email checks recipient hash == shown; label shows masked recipient (t***@domain), address never stored.
- I4 POST /actions/{id}/retry: failed → approved → executor, explicit click only, audited 'retry'.
Final review: fixed Minor 5 (claim committed before external call; run commits before LLM awaits), 6 (Link 2 strict topic: bare charge/fee ignored), 8 (regenerate pulse once with default actions), 10 (verify report with no runs; NOT the 7-day window part), 12 (.gitattributes *.py eol=lf + renormalise), 13 (scheduler test pinned), 14 (PII separators = horizontal whitespace incl. NBSP, never newline).
Final review: Ruling: deferred Minor 7 (ticket ids per repeated key in pulse — word cap; plan gap), 9 (keyword-anchored explainer bullets), 10b (verify repeated-questions window), 11 (run status 'done'), 15 (scraper naive time, review retention) — cost if wrong: cosmetic/quality, none touch the approval gate or PII; candidates for Plan 3/4.
Final review: Rulings on 'declined to judge': Link 2 reuse skips Pattern agent → accepted (spec §6 makes canonical reuse an alternative to the desk; still human-approved). LLM action-idea text reaching the Doc → accepted (check_output + human approval). Multiple uvicorn workers → Plan 4 deploys single worker. Names in review text → spec §8 list excludes names.
Final review: added .gitignore for api/mcp_server/.tokens/ (MCP server's Google token cache appeared after live approvals; never committed).
Final review: full suite 290 passed, 5 skipped.
