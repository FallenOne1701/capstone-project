# SDD ledger — plan: docs/superpowers/plans/2026-11-17-plan-1-foundation-response-loop.md
Spec: docs/superpowers/specs/2026-11-17-support-desk-design.md
Setup: Ruling: work on branch plan-1-foundation in place (no worktree) — fresh single-user repo, nothing else checked out — cost if wrong: none, branch is isolated.
Pre-flight:
- T1→T7/T13: models Source/Ticket/Draft/Action/AuditLog consumed with matching fields (Action.draft_id, Draft.searched) — consistent.
- T1→T6: Settings exposes M1 field names (data_*_dir, schemes_path, fetch_*, chunk_*, retrieval_*) — consistent; M1 modules may read extra fields → rule in T6 if hit.
- T6→T7: refresh consumes FetchReport/FetchResult field names not pinned by plan — plan says adjust to real fields; rule in T7.
- T8→T11/T12: Disposition includes "account" — consistent.
- T9→T10/T12/T13: IntentResult(intent, scheme_ids, fact_key, language, confidence) — consistent.
- T10→T12: run_facts(text, retriever, last_checked), run_pattern(text, themes, today=), run_compliance(text, pii, intent), team_for(theme_id, themes) — consistent.
- T7→T13: last_checked_for(db, url) — consistent.
- T12→T13: run_desk(..., retriever=, themes=, last_checked=, today=) — consistent.
Task 1: complete (commits 06fbe84..c58b2aa, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 1 passed, 17 warnings in 0.06s)
Task 2: complete (commits c58b2aa..4b1a0df, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 31 passed, 17 warnings in 0.14s)
Task 3: complete (commits 4b1a0df..5f5599e, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 33 passed, 17 warnings in 0.12s)
Task 4: complete (commits 5f5599e..6e1539c, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 56 passed, 17 warnings in 0.23s)
Task 5: complete (commits 6e1539c..0023a7d, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 61 passed, 17 warnings in 0.36s)
Task 6: Ruling: ported M1 code+embedder written before running the new corpus test (plan step order for a port) — test still exercises fastembed end-to-end and passed — cost if wrong: none, behaviour verified.
Task 6: Ruling: 5 ported test_retrieval tests skip (need live data/processed/all_chunks.json); left skipped — test_corpus_port covers same path on fixtures — cost if wrong: minor lost coverage.
Task 6: complete (commits 0023a7d..9800c14, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 92 passed, 5 skipped, 18 warnings in 11.31s)
Task 7: complete (commits 9800c14..e21ef14, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 95 passed, 5 skipped, 18 warnings in 39.77s)
Task 8: Ruling: wrote contracts.py directly with the plan's edits applied instead of cp+edit — identical result, fewer steps — cost if wrong: none.
Task 8: complete (commits e21ef14..41bed8c, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 102 passed, 5 skipped, 18 warnings in 41.70s)
Task 9: complete (commits 41bed8c..9c3fb1e, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 127 passed, 5 skipped, 18 warnings in 47.98s)
Task 10: Ruling: added tests/conftest_corpus.py build_fixture_retriever() (+ tests/__init__.py) instead of repeating the index-building fixture in each test module — DRY, same behaviour — cost if wrong: none.
Task 10: complete (commits 9c3fb1e..840126e, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 133 passed, 5 skipped, 18 warnings in 51.30s)
Task 11: complete (commits 840126e..29cb64c, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 139 passed, 5 skipped, 18 warnings in 52.61s)
Task 12: Ruling: scope.detect_performance flagged real answers because fund names end in 'Direct Growth' (growth word within 6 words of '1%') — strip plan-name 'Growth' like TRI; 3 regression cases added to test_scope RED→GREEN — cost if wrong: a sentence like 'Direct Growth gave 20%' still flagged via 'gave'.
Task 12: complete (commits 29cb64c..6ce6a90, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 148 passed, 5 skipped, 18 warnings in 58.16s)
Task 13: Ruling: test_approvals _snapshot calls db.expire_all() before reading — otherwise identity-map objects hide DB changes and the diff is meaningless — cost if wrong: none. Added test_unknown_ticket_404.
Task 13: Ruling: live smoke found RedactingFilter emptied record.args, breaking uvicorn AccessFormatter on every request — now redacts str args in place, keeps tuple shape; test_filter_keeps_args_shape_for_formatters_that_read_them RED→GREEN — cost if wrong: non-str PII args (e.g. int) not redacted.
Task 13: Ruling: live smoke found retriever answered exit load for "expense ratio of small cap ... my pan [PAN]" (top-k similarity dropped the exact fact chunk) — added metadata-first exact (scheme_id, fact_key) lookup when both detected; test_detected_fact_key_wins_over_noisy_similarity RED→GREEN — cost if wrong: a mis-detected fact_key now overrides similarity.
Task 13: live smoke (Step 6) ran with real Groq + live corpus (15 pages, 91 vectors): 4 questions → correct dispositions; server log has 0 raw PII, 0 logging errors.
Task 13: complete (commits 6ce6a90..bc9bd71, tests: bash -c 'cd api && .venv/Scripts/python -m pytest -q' → 170 passed, 5 skipped, 18 warnings in 38.60s)
Final review: fresh reviewer (opus) — 3 Critical, 7 Important, 8 Minor. Re-graded: kept C1–C3 Critical, I1–I7 Important.
Final: Ruling: reviewer's suggested PAN regex ((?:[a-z][\s-]?){5}...) rejected — it matches "SIP is 1000 a month" ("sip is" = 5 letters); used explicit letter-group alternatives (compact | fully spaced | 4+1) — cost if wrong: other partial spacings like "ab cde1234f" not caught.
Final: Ruling: test expectation for "lock-in period ... after I invest" corrected to lock_in (whole-word lock-in is the right fact; the bug was expense_ratio) — cost if wrong: none.
Final: Ruling: C2 fix makes scheme-only questions without a detected fact "not covered" even when a nearby chunk might answer them — conservative grounding per spec §4 — cost if wrong: some answerable paraphrases (e.g. "what does mid cap invest in") hand off instead of answering.
Final: fixed C1 fact-key substring — test_fact_key_whole_word RED→GREEN, suite 205/205
Final: fixed C2 scheme-only covered — test_scheme_without_known_fact_is_not_covered, test_term_schemes_answer_the_asked_fact RED→GREEN, suite 205/205
Final: fixed C3 mixed-spacing PAN — test_mixed_spacing_pan_redacted RED→GREEN, suite 205/205
Final: fixed I1 citation in text / empty edit — test_covered_reply_without_link_fails, test_empty_edit_rejected RED→GREEN, suite 205/205
Final: fixed I2 atomic claim — test_approve/reject_uses_db_state_not_stale_object RED→GREEN, suite 205/205
Final: fixed I3 edit after decision — test_edit_after_approve_rejected RED→GREEN, suite 205/205
Final: fixed I4 console auth — test_console_unconfigured_password_refused RED→GREEN, suite 205/205
Final: fixed I5 traceback/non-str args — test_exception_traceback_redacted RED→GREEN, suite 205/205
Final: fixed I6 objective 'returns' — test_objective_returns_wording_allowed RED→GREEN, suite 205/205
Final: fixed I7 transactional how-to — test_transactional_howto_not_advice RED→GREEN, suite 205/205
Final: minor (deferred): test_junk_input_never_500 only asserts HTTP 200, not in_review/handoff
Final: minor (deferred): classify_intent runs twice per /api/ask (extra LLM calls; stored intent may differ from desk's)
Final: minor (deferred): Groq call has no explicit timeout/max_retries — a degraded Groq can hang /api/ask for minutes
Final: minor (deferred): cancelled /api/ask leaves ticket in 'received' with no sweeper (Plan 3 worker)
Final: minor (deferred): refresh ignores build_index errors; removed page sections stay in the index (upsert only)
Final: minor (deferred): metadata-first winner skips _select_winner's groww.in URL check (indexer already filters)
Final: minor (deferred): ACCOUNT rule swallows the word "account"; >18-digit runs not redacted; 10-digit corpus number starting 6-9 would be tagged PHONE
Final: minor (deferred): async /api/ask runs sync SQLAlchemy on the event loop (serializes under load)
