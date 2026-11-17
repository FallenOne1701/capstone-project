# Plan 3 — Console UI + Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Next.js web app with a public `/ask` page (speak or type → confirm → ticket → status → listen, in English or Hindi) and a password-protected `/console` (queue, pulse, approvals, explainers, sources) driving the existing API. The API gains voice transcription, clarification, background ticket processing and Hindi replies.

**Architecture:** API additions stay in the existing FastAPI app. `app/voice/` holds the Whisper call (audio is kept in memory only). `app/tickets/worker.py` moves the desk off the request path. `app/desk/translate.py` adds a validated Hindi version to each draft, stored in a new additive table. The web app is a new `web/` Next.js 16 App Router project, styled with M3's "Groww Ops Precision" Stitch tokens. It talks to the API over REST: the console sends `X-Console-Key`, and the public page sends nothing. Pure browser logic (labels, recorder state, voice choice) lives in `web/lib/` with vitest unit tests. Pages are covered by Playwright smoke tests.

**Tech Stack:** API: Python 3.14, FastAPI, Groq SDK (`whisper-large-v3-turbo`, `openai/gpt-oss-120b`), pytest. Web: Next.js **16.4.2**, React **19.3.0**, Tailwind 4, TypeScript 5, vitest, @playwright/test. Browser APIs: MediaRecorder, `speechSynthesis`.

**Spec:** `docs/superpowers/specs/2026-11-17-support-desk-design.md`. This plan covers §3 (web routes `/ask`, `/console/*` except Evals), §5 (all of voice and intent UX), §6.3 (the response loop off the request path), §7 (console approve/edit/reject/Retry), §11 (Playwright smoke tests) and §12 (failed tickets shown in the console). Plan 4 covers the Evals page, evals, `/health` MCP handshake, and Railway + Vercel deploy.

## Global Constraints

- Audio is **held in memory only, never written to disk, logs or DB**. Max recording **60 s**. Clips **under ~1 s or silent are rejected**.
- STT failure copy, verbatim: **"Couldn't hear that — try again or type"**.
- Mic-permission-denied guidance must be shown, and **typing is always available**.
- Confirm step shows the **redacted** transcript and the detected intent in the form **"Fee question · HDFC Mid Cap"**. Ambiguous scheme gets **one** clarifying question in the form **"HDFC Mid Cap or HDFC Small Cap?"**.
- Ticket status words: **received → in review → answered**.
- Advice/performance intents immediately show, verbatim: **"We share facts only and can't advise on buying, selling or returns"** (`SCOPE_NOTICE` in `app/tickets/service.py`). The refusal reply still needs approval.
- Listen: `speechSynthesis`, voice **`en-IN` or `hi-IN`** matching the question language. **Hindi/Hinglish questions get Hindi replies**, with facts and citations unchanged.
- Nothing reaches a ticket without an approved `reply_publish`. This includes the Hindi text, which the approver sees before approving.
- The console is protected by the shared password (`CONSOLE_PASSWORD`), sent as header `X-Console-Key`. The public page never sends it.
- `USE_LLM=0`: every API test runs offline. Voice then answers **503** with the typed-fallback message, and translation is skipped (English is published).
- Next.js is pinned **16.4.2** and React **19.3.0**, the versions M3 runs. Before writing web code, read `web/node_modules/next/dist/docs/`: this Next version has breaking changes, and page `params` is a Promise.
- Only additive DB changes: new tables are fine (`create_all`), but no new columns on existing tables, because local SQLite and the demo DB have no migrations.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Whisper invents text from silence or noise** (e.g. "Thank you."). The user must get "Couldn't hear that — try again or type", not a ticket. → Task 1, `test_silence_hallucination_rejected`.
2. **Hindi speech transcribed in Urdu script.** It must be re-transcribed with `language="hi"` so the confirm step shows Devanagari. → Task 1, `test_urdu_script_retried_as_hindi`.
3. **Translation changes a fact** (a different %, a dropped or altered URL, a new number). The Hindi text must be discarded and English published. → Task 4, `test_translation_that_changes_numbers_or_links_is_discarded`.
4. **No Hindi voice on the device, or voices load late** (Chrome fills `getVoices()` asynchronously). Listen must still work and say it's reading in English. → Task 8, `pickVoice` tests.
5. **Safari/iOS has no `audio/webm`**, and a non-secure page has no `mediaDevices`. The recorder must pick `audio/mp4`, or else hide the mic with typed-fallback guidance. → Task 7, `pickMimeType` / `voiceSupport` tests.

---

### Task 1: Voice transcription endpoint

**Files:**
- Create: `api/app/voice/__init__.py`, `api/app/voice/stt.py`
- Modify: `api/app/api/public.py` (new route), `api/app/config.py` (settings), `api/app/tickets/service.py` (`PreviewOut.scheme_names`)
- Test: `api/tests/test_voice.py`

**Interfaces:**
- Produces: `class Transcript(BaseModel): text: str; language: str  # whisper language name, e.g. "english", "hindi"`.
- Produces: `async def transcribe(audio: bytes, filename: str) -> Transcript`. It raises `NoSpeech` (the clip is silent, empty or a hallucination) or `VoiceUnavailable` (LLM disabled, no key, or provider error).
- Produces: `POST /api/voice/transcribe`, multipart fields `audio` (file) and `duration_ms` (int). Returns `PreviewOut` (the same JSON as `/api/ask/preview`). Errors: `422 {"detail": "Couldn't hear that — try again or type"}` for too short/long/small/silent; `413` over the size cap; `503 {"detail": "Voice is unavailable right now — please type your question."}`.
- Produces: `PreviewOut.scheme_names: list[str]` with short names (`"HDFC Mid Cap"` = scheme_name cut before `" Fund"`), one per `scheme_ids`, for every preview, not only ambiguous ones.
- Settings: `groq_stt_model="whisper-large-v3-turbo"`, `voice_max_bytes=5_000_000`, `voice_min_ms=1000`, `voice_max_ms=61000`.

- [ ] **Step 1: Write the failing tests** in `api/tests/test_voice.py`. Patch `app.voice.stt._whisper` (async `(audio, filename, language|None) -> dict`, the verbose_json payload) so no network is used.

```python
def test_transcribe_returns_redacted_preview(client, monkeypatch)        # whisper text "my pan is ABCDE1234F what is the exit load of HDFC mid cap"
    # → 200, redacted_text contains "[PAN]", intent == "fee_question", scheme_names == ["HDFC Mid Cap"]
    # → "ABCDE1234F" appears in no captured log record (caplog at DEBUG)
def test_too_short_clip_rejected(client)                                  # duration_ms=600 → 422, detail == "Couldn't hear that — try again or type"; _whisper never called
def test_too_long_clip_rejected(client)                                   # duration_ms=61001 → 422
def test_oversize_upload_rejected(client)                                 # 5_000_001 bytes → 413
def test_silence_hallucination_rejected(client, monkeypatch)              # text "Thank you.", every segment no_speech_prob 0.9 → 422 same detail
def test_empty_text_rejected(client, monkeypatch)                         # text "  " → 422
def test_urdu_script_retried_as_hindi(client, monkeypatch)                # 1st call language "urdu" → 2nd call made with language="hi"; Devanagari text returned; language == "hi"
def test_voice_unavailable_without_llm(client, monkeypatch)               # use_llm False → 503, detail == "Voice is unavailable right now — please type your question."
def test_audio_never_written_to_disk(client, monkeypatch, tmp_path)       # monkeypatch builtins.open + tempfile.* to fail if called during the request → still 200
```

- [ ] **Step 2: Run, verify they fail.** `cd api && .venv/Scripts/python -m pytest -q tests/test_voice.py` → errors (no module `app.voice`).

- [ ] **Step 3: Implement `app/voice/stt.py`.**
  - `_whisper` calls `AsyncGroq(...).audio.transcriptions.create(file=(filename, audio), model=s.groq_stt_model, response_format="verbose_json", temperature=0, prompt="Question about HDFC mutual funds on Groww, in English, Hindi or Hinglish.", language=language)` (omit `language` when None) and returns `.model_dump()`.
  - No-speech rule: empty text, or the mean `no_speech_prob` over segments ≥ 0.6 → `NoSpeech`.
  - Urdu rule: `language == "urdu"` → call once more with `language="hi"`.
  - Never log the transcript or audio. Log only `"stt ok lang=%s chars=%d"`.
  - The route reads `await audio.read()` into a local, checks size/duration before calling Whisper, `del`s the bytes in `finally`, then returns `await ts.preview(transcript.text)`.
  - Whisper's language overrides `detect_language` only when the text has no Devanagari and Whisper says `hindi` → `"hinglish"`.

- [ ] **Step 4: Run the tests**: they pass. Run `tests/test_tickets_api.py` too, since `PreviewOut` gained a field.

- [ ] **Step 5: Commit** `feat(voice): in-memory Whisper transcription endpoint with silence and Urdu-script guards`.

---

### Task 2: Clarification answer and channel on `/api/ask`

**Files:**
- Modify: `api/app/api/public.py` (`AskIn`), `api/app/tickets/service.py` (`create_ticket`, `process_ticket`)
- Test: `api/tests/test_clarify.py`

**Interfaces:**
- Produces: `AskIn{text: str, scheme_id: str | None = None, channel: Literal["text","voice"] = "text"}`.
- Produces: `create_ticket(db, text, *, channel="text", scheme_id=None)`. A `scheme_id` is honoured **only if** it is in the classified `intent.scheme_ids`; any other value is ignored (no 422, ticket stays ambiguous). `process_ticket` narrows `intent.scheme_ids` to `[t.scheme_id]` when the ticket has one.

- [ ] **Step 1: Failing tests**

```python
def test_clarified_scheme_is_answered(client, db_session)       # "exit load of HDFC mid cap and small cap" + scheme_id="hdfc-mid-cap-fund-direct-growth"
    # → ticket.scheme_id == that id; draft.citation is the mid-cap source URL
def test_scheme_id_not_in_question_is_ignored(client, db_session)  # scheme_id="hdfc-gilt-fund-direct-growth" → ticket.scheme_id is None
def test_voice_channel_recorded(client, db_session)              # channel="voice" → ticket.channel == "voice"
def test_unknown_channel_rejected(client)                        # channel="fax" → 422
```

- [ ] **Step 2: Run, verify they fail.** **Step 3: Implement.** **Step 4: Run** `tests/test_clarify.py tests/test_tickets_api.py`: they pass.
- [ ] **Step 5: Commit** `feat(tickets): clarification answer and voice channel on /api/ask`.

---

### Task 3: Background ticket worker, startup recovery, console re-run

**Files:**
- Create: `api/app/tickets/worker.py`
- Modify: `api/app/api/public.py`, `api/app/api/console.py`, `api/app/main.py`, `api/app/config.py`, `api/tests/conftest.py`
- Test: `api/tests/test_worker.py`

**Interfaces:**
- Produces: `worker.submit(ticket_id: int) -> None`. It runs `process_ticket` in a `ThreadPoolExecutor(max_workers=2)`, each job with its own `SessionLocal()` (read via `app.db` at call time) and `asyncio.run`.
- Produces: `worker.recover(db) -> list[int]`. At startup it resubmits every ticket still `received` (orphaned by a restart or a cancelled request); it is called from `create_app` after `_recover_runs`.
- Produces: `POST /api/console/tickets/{code}/reprocess`. It is allowed only for status `failed` or `received` (else 409), sets `received`, writes audit verb `reprocess`, submits, and returns `{"code", "status": "received"}`.
- Setting `ticket_worker_inline: bool = False`. `conftest.py` sets env `TICKET_WORKER_INLINE=1`, so existing tests keep their synchronous behaviour. When inline, `/api/ask` awaits processing in-request as today.
- `/api/ask` (not inline) returns at once with `status == "received"`.

- [ ] **Step 1: Failing tests**

```python
def test_ask_returns_before_processing(client, monkeypatch)       # inline False, worker.submit patched to record → status "received", submit called with the ticket id
def test_recover_resubmits_received_tickets(db_session, monkeypatch)  # 1 received + 1 in_review → returns [received.id] only
def test_reprocess_failed_ticket(client, db_session, monkeypatch)  # failed → 200, status "received", audit row verb "reprocess"
def test_reprocess_rejects_answered(client, db_session)            # answered → 409
def test_worker_job_uses_its_own_session(db_session, monkeypatch)  # run the job body directly → ticket ends "in_review"
```

- [ ] **Steps 2–4:** run (fail) → implement → run `tests/test_worker.py` plus the full suite (pass; must still be 290+ passing).
- [ ] **Step 5: Commit** `feat(tickets): process tickets off the request path; recover orphans at startup; console re-run`.

---

### Task 4: Validated Hindi replies

**Files:**
- Create: `api/app/desk/translate.py`
- Modify: `api/app/models.py` (new table), `api/app/tickets/service.py` (after the draft is built), `api/app/approvals/service.py` (`edit_draft` drops the translation), `api/app/api/console.py` (`_draft_out`), `api/app/api/public.py` (`ticket_status`)
- Test: `api/tests/test_translate.py`

**Interfaces:**
- Produces model `DraftTranslation(id, draft_id FK unique, language="hi", text, created_at)`, table `draft_translations` (additive).
- Produces: `async def translate_reply(reply: str) -> str | None` (Hindi, Devanagari; `None` if the LLM is off or fails). Uses `complete_json` with JSON `{"text": ...}`. The prompt keeps URLs, numbers, dates, scheme names and the literal "Source:" / "Last checked:" labels unchanged.
- Produces: `def validate_translation(src: str, out: str) -> list[str]`, with these problems:
  - the sets of URLs differ;
  - the multisets of digit runs (`\d+(?:[.,]\d+)*`) differ;
  - `find_pii(out)` is non-empty;
  - the text has no Devanagari;
  - `len(out) > 3 * len(src)`.
- Hook: in `process_ticket`, if `t.language in ("hi", "hinglish")` and `review.status == "pass"`, translate and validate, then store the translation only if there are no problems. Either way, audit `translate` with `ok` or `discarded:<first problem>`.
- `edit_draft` deletes that draft's translation: the edited English is what gets published, and the console says so.
- Console `_draft_out` gains `"translation": {"language": "hi", "text": ...} | None`.
- Public `GET /api/tickets/{code}` gains `"answer_local": {"language": "hi", "text": ...} | None`, from the executed draft's translation, only when `answered`.

- [ ] **Step 1: Failing tests**

```python
def test_hindi_question_gets_hindi_translation_stored(db_session, monkeypatch)   # complete_json patched → valid Devanagari keeping URL + "1%" + date → row stored
def test_translation_that_changes_numbers_or_links_is_discarded()               # validate_translation: "1%"→"2%" problem; URL removed problem; extra URL problem
def test_english_question_not_translated(db_session, monkeypatch)                # complete_json must not be called
def test_blocked_draft_not_translated(db_session, monkeypatch)
def test_edit_drops_translation(db_session, monkeypatch)
def test_public_ticket_shows_hindi_only_after_approval(client, db_session, monkeypatch)  # before approve: answer_local None; after: Hindi text
def test_llm_off_publishes_english(client, db_session)                           # USE_LLM=0 → answer_local None, answer English
```

- [ ] **Steps 2–4:** fail → implement → pass (`tests/test_translate.py`, `tests/test_tickets_api.py`, `tests/test_approvals.py`).
- [ ] **Step 5: Commit** `feat(desk): validated Hindi replies for Hindi/Hinglish tickets, approved with the draft`.

---

### Task 5: Web scaffold, design tokens, API client

**Files:**
- Create: `web/` (Next 16.4.2 app). Copy from M3 `C:/Users/dhruv/multi agentic system/multi-agentic-system/web/`: `package.json` deps, `tsconfig.json`, `next.config.ts`, `eslint.config.mjs`, `app/globals.css` (Stitch tokens), and the font setup in `app/layout.tsx`. Not copied: M3 pages/components.
- Create: `web/lib/api.ts`, `web/lib/types.ts`, `web/lib/labels.ts`, `web/app/page.tsx` (redirect to `/ask`), `web/.env.example` (`NEXT_PUBLIC_API_URL=http://localhost:8000`), `web/vitest.config.ts`
- Test: `web/lib/labels.test.ts`, `web/lib/api.test.ts`

**Interfaces:**
- `types.ts` mirrors the API JSON: `Preview` (= PreviewOut incl. `scheme_names`), `AskResult{code,status,notice}`, `TicketView{code,status,question,answer,answer_local,answered_at,language}`, `QueueItem`, `Action`, `WeeklyLatest`, `Explainer`, `Source`.
- `labels.ts`:
  - `intentLabel(p: Preview): string` → `"Fee question · HDFC Mid Cap"`; intent only when there's no single scheme.
  - `clarifyQuestion(names: string[]): string` → `"HDFC Mid Cap or HDFC Small Cap?"` (3+ names joined `", "` with the last pair joined `" or "`).
  - `statusLabel(s): "received" | "in review" | "answered" | "failed"`.
  - `INTENT_LABELS` for all 7 intents (`fee_question` → "Fee question", `fund_fact` → "Fund fact", `how_to_process` → "How-to", `advice_request` → "Advice request", `performance_request` → "Returns request", `account_issue` → "Account issue", `out_of_scope` → "Out of scope").
- `api.ts`:
  - `api<T>(path, init?, opts?: {console?: boolean}): Promise<T>`. It prefixes `NEXT_PUBLIC_API_URL` and adds `X-Console-Key` from `sessionStorage["consoleKey"]` only when `opts.console`. On a non-2xx response it throws `ApiError{status, detail}`, where `detail` is FastAPI's `detail`.
  - Typed helpers: `preview`, `ask`, `transcribe(blob, durationMs)`, `ticket(code)`, and console `queue`, `approve`, `reject`, `retry`, `editDraft`, `reprocess`, `actions(status?)`, `weeklyLatest`, `weeklyRun`, `explainers`, `sources`, `refreshSources`, `checkKey(key)` (GET `/api/console/actions?status=pending`; 401 → false).

- [ ] **Step 1: Failing vitest tests** for `intentLabel`, `clarifyQuestion` (2 and 3 names), `statusLabel("in_review") === "in review"`, `api()` sending the key only for console calls and mapping `{detail}` into `ApiError` (mock `fetch`).
- [ ] **Step 2:** `cd web && npm ci && npx vitest run` → fail. **Step 3:** implement. **Step 4:** `npx vitest run` passes, and `npm run build` succeeds.
- [ ] **Step 5: Commit** `feat(web): Next.js scaffold with Groww Ops tokens, typed API client and labels`.

---

### Task 6: `/ask` — type, confirm, clarify, submit

**Files:**
- Create: `web/app/ask/page.tsx`, `web/components/ask/AskFlow.tsx` (client), `web/components/ask/ConfirmCard.tsx`, `web/components/ask/ScopeNotice.tsx`
- Create (Playwright harness, used by every later e2e): `web/playwright.config.ts`, `web/e2e/fixtures.ts`; modify `web/package.json` (`"e2e": "playwright test"`)

**Harness interfaces:**
- `playwright.config.ts` has two `webServer` entries:
  1. The API: `.venv/Scripts/python -m uvicorn --factory app.main:create_app --port 8001`, cwd `../api`, with env `DATABASE_URL=sqlite:///./data/e2e/e2e.db`, `USE_LLM=0`, `CONSOLE_PASSWORD=e2e-pass-123`, `E2E_SEED=1` and `TICKET_WORKER_INLINE=0`. It reuses the local corpus and index data dirs.
  2. `next dev -p 3001` with `NEXT_PUBLIC_API_URL=http://localhost:8001`.

  `globalSetup` deletes `api/data/e2e/` first. Chromium gets `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`.
- `fixtures.ts`: `login(page)`, `createTicket(request, text) -> code` (via `POST /api/ask`), `waitForStatus(request, code, status)`.

**Behaviour (single flow, state machine `compose → confirm → submitting`):**
- **compose:** a textarea (max 500 characters, with a live counter) and "Continue". This calls `preview`, then goes to `confirm`. A 422 shows the detail inline.
- **confirm:** shows the redacted text, highlighting `[PAN]`-style tokens with the `redaction` colours. Also shows `intentLabel` and an "Edit" button (back to compose, text kept).
  - If `needs_clarification`: the `clarifyQuestion` text plus one button per scheme name. Submit stays disabled until one is chosen, and the choice is sent as `scheme_id`.
  - For advice or performance intents: `ScopeNotice` with the verbatim copy.
- **submit:** calls `ask({text, scheme_id, channel})` with the button disabled while pending (no double tickets), then `router.push('/t/' + code)`.
- The `preview` is re-fetched if the text is edited after confirm.

- [ ] **Step 1:** create the harness, then add Playwright test `web/e2e/ask.spec.ts::typed question becomes a ticket`. It types "What is the exit load of HDFC Mid Cap Fund?", sees "Fee question · HDFC Mid Cap", submits, lands on `/t/GRW-…`, and sees "received" or "in review".
- [ ] **Step 2:** run → fail. **Step 3:** implement. **Step 4:** run → pass; `npm run build` ok.
- [ ] **Step 5: Commit** `feat(web): /ask typed flow with redacted confirm, clarification and scope notice`.

---

### Task 7: Voice capture on `/ask`

**Files:**
- Create: `web/lib/recorder.ts`, `web/components/ask/MicButton.tsx`
- Modify: `web/components/ask/AskFlow.tsx`
- Test: `web/lib/recorder.test.ts`

**Interfaces:**
- `pickMimeType(isSupported: (t: string) => boolean): string | null`. It tries, in order, `"audio/webm;codecs=opus"`, `"audio/webm"`, `"audio/mp4"`, `"audio/ogg;codecs=opus"`.
- `voiceSupport(env: {secure: boolean; hasMediaDevices: boolean; hasRecorder: boolean}): "ok" | "insecure" | "unsupported"`.
- `MAX_MS = 60_000`, `MIN_MS = 1_000`.
- `useRecorder(): {state: "idle"|"recording"|"denied"|"error", elapsedMs, start(), stop(): Promise<{blob, durationMs} | null>}`. It auto-stops at `MAX_MS` and stops the mic tracks on stop and unmount.

**Behaviour:**
- The mic button shows a live timer (`0:07 / 1:00`).
- Under `MIN_MS`: shows the STT failure copy and never uploads.
- Otherwise: `transcribe(blob, durationMs)`, then the same `confirm` state as typing, with `channel = "voice"` and a "Re-record" button.
- Error handling:
  - 422 → "Couldn't hear that — try again or type".
  - 503 → the API detail.
  - Permission denied → "Microphone access is blocked. Allow it in your browser's site settings, or type your question below."
  - `insecure` / `unsupported` → the mic is hidden, with "Voice input needs a secure (https) page — please type your question." / "This browser can't record audio — please type your question."
- The audio blob is never stored (no IndexedDB/localStorage), and the reference is dropped after upload.

- [ ] **Step 1: Failing vitest tests:** `pickMimeType` returns `"audio/mp4"` when only mp4 is supported, and `null` when none is. `voiceSupport` covers the three cases.
- [ ] **Step 2:** Playwright `ask.spec.ts::voice question reaches confirm`. Chromium is launched with `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`. `page.route('**/api/voice/transcribe')` returns a canned Preview. Record about 1.5 s, stop, and expect the confirm card with that transcript and "Re-record".
- [ ] **Step 3:** run → fail. **Step 4:** implement. **Step 5:** vitest and Playwright pass.
- [ ] **Step 6: Commit** `feat(web): voice capture with 60 s cap, fallbacks and confirm step`.

---

### Task 8: Ticket status page + Listen

**Files:**
- Create: `web/app/t/[code]/page.tsx`, `web/components/ticket/TicketStatus.tsx` (client), `web/lib/speech.ts`
- Test: `web/lib/speech.test.ts`

**Interfaces:**
- `speechLang(language: "en"|"hi"|"hinglish", hasLocal: boolean): "en-IN" | "hi-IN"`. Returns `"hi-IN"` only when a Hindi text exists.
- `pickVoice(voices: {lang: string; name: string}[], want: "en-IN"|"hi-IN"): {voice | null, fellBack: boolean}`. The order is: exact `want`, then the same language prefix, then `en-IN`, then any `en-*`, then `null`. `fellBack` is true when the language differs from `want`.
- `loadVoices(synth): Promise<Voice[]>`. It resolves on `voiceschanged` or after 1500 ms, whichever comes first.

**Behaviour:**
- The page polls `ticket(code)` every 3 s until `answered` or `failed`. It stops on unmount and on 404, which shows "We couldn't find that ticket."
- A three-step status bar: received → in review → answered.
- When answered, it shows the `answer_local.text` (Hindi) when present, with a "Show English" toggle. The citation URL is a link.
- The 🔊 Listen button reads exactly the shown text with `pickVoice`. When `fellBack` is set, it shows "No Hindi voice on this device — reading in English." and switches to the English text. A second press cancels speech.
- `failed` shows "Something went wrong on our side — our team can see this ticket." Advice or performance tickets also show the scope notice.

- [ ] **Step 1: Failing vitest tests** for `pickVoice`: exact match, prefix match, fallback to en-IN with `fellBack`, and an empty list. Also `speechLang`.
- [ ] **Steps 2–4:** fail → implement → pass; `npm run build`.
- [ ] **Step 5: Commit** `feat(web): ticket status page with polling and en-IN/hi-IN listen`.

---

### Task 9: Console shell + Queue

**Files:**
- Create: `web/app/console/layout.tsx`, `web/components/console/ConsoleGate.tsx`, `web/components/console/Nav.tsx`, `web/app/console/page.tsx` (Queue), `web/components/console/QueueItem.tsx`, `web/components/console/ActionButtons.tsx`

**Behaviour:**
- **Gate:** a password field calls `checkKey`. On success the key goes into `sessionStorage["consoleKey"]`, otherwise "Wrong password". A 401 on any later console call clears the key and shows the gate. "Sign out" clears it too.
- **Nav:** Queue · Pulse · Approvals · Explainers · Sources.
- **Queue:** newest first. Each ticket shows:
  - code, status, intent label, language, redacted question, and the PII types found (as chips, never values);
  - the draft reply (and the **Hindi translation** under it, labelled "Published in Hindi");
  - the citation link, last checked, and the routing note (team · priority · why);
  - the review status (pass/blocked, with failure reasons);
  - a "Reused explainer #N" badge.
- **Queue actions:**
  - `pending` → Approve / Edit / Reject. A blocked draft disables Approve with the tooltip "Edit it first".
  - Edit opens an inline textarea, then calls `editDraft`. It then shows the new review result and the note "Hindi translation removed — the edited English will be published".
  - `failed` action → Retry, showing the error text.
  - Ticket `failed`/`received` without a draft → "Re-run desk" (`reprocess`).
- The list refreshes after every action and every 10 s.

- [ ] **Step 1:** Playwright `console.spec.ts::approve publishes the answer`. It creates a ticket via the API, logs in with the e2e password, finds it in the queue, clicks Approve, opens `/t/<code>`, and expects the answer text and a Listen button.
- [ ] **Step 2:** Playwright `console.spec.ts::wrong password stays locked`.
- [ ] **Steps 3–5:** fail → implement → pass.
- [ ] **Step 6: Commit** `feat(web): console password gate and approval queue`.

---

### Task 10: Console Pulse + Approvals

**Files:**
- Create: `web/app/console/pulse/page.tsx`, `web/app/console/approvals/page.tsx`, `web/components/console/ThemeList.tsx`
- Create: `api/scripts/e2e_seed.py`; modify `api/app/main.py`
- Test: `api/tests/test_e2e_seed.py`

**Seed interface:**
- `e2e_seed.seed(db) -> None`: if there are no weekly runs, it runs `run_weekly` with a fetcher over `tests/fixtures/reviews.json`. It is idempotent.
- `create_app` calls it only when `E2E_SEED=1` **and** `USE_LLM=0`. Otherwise it logs a warning and skips.

**Behaviour:**
- **Pulse:**
  - Run summary: status, window, review count, LLM calls, error.
  - "Run now" calls `weeklyRun`. A 409 shows "A run is already in progress". The page then polls `weeklyLatest` every 5 s while `running`.
  - Themes, ranked: label, count, last-7-days count, window, and collapsible review ids.
  - The pulse text in a monospace block, the repeated questions (key, count, window), and the explainer (bullets with links, last checked, status, reuse count).
  - The run's two actions with the exact target label and content preview, plus Approve / Reject / Retry. Approve asks for confirmation ("This writes to Google Docs" / "This creates a Gmail draft (not sent)").
- **Approvals:** every action, with filter tabs (pending / failed / executed / rejected / all). Each row shows the type, target label, created/decided time, error, and a collapsible content preview, with the same buttons.

- [ ] **Step 1:** pytest `test_e2e_seed_requires_offline_mode` (USE_LLM on → no run created) and `test_e2e_seed_is_idempotent`. Then Playwright `console.spec.ts::pulse page shows themes and actions` (the seeded run shows ≥1 theme with review ids and two pending actions).
- [ ] **Steps 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** `feat(web): console pulse and approvals pages`.

---

### Task 11: Console Explainers + Sources

**Files:**
- Create: `web/app/console/explainers/page.tsx`, `web/app/console/sources/page.tsx`

**Behaviour:**
- **Explainers:** each explainer shows its id, topic, status badge (draft / canonical / superseded / rejected), run id, bullets with source links, last checked, canonical_at and reuse count.
- **Sources:** a table of title, kind, status (ok / stale / error badge), last checked and error. "Refresh now" calls `refreshSources`, disabled with a spinner while it runs (it can take about a minute), and then shows `ok/stale/error/reindexed`.

- [ ] **Step 1:** Playwright `console.spec.ts::explainers and sources render` (seeded: ≥1 explainer row; sources table has ≥15 rows).
- [ ] **Steps 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** `feat(web): console explainers and sources pages`.

---

### Task 12: Full regression run + README

**Files:**
- Create: `web/README.md` (run API + web locally, env vars, `npm run e2e`)
- Modify: `CLAUDE.md` "Run it" section (web commands)

- [ ] **Step 1:** Run the full API suite (`cd api && .venv/Scripts/python -m pytest -q`) and expect no failures.
- [ ] **Step 2:** Run `cd web && npx vitest run && npm run build && npx playwright test` and expect all green.
- [ ] **Step 3: Commit** `docs(web): how to run the console and /ask locally`.

---

### Task 13: Live check + manual checkpoint

**Files:** none new (results go in the ledger)

- [ ] **Step 1:** Start the real API (port 8000, real `.env`) and `cd web && npm run dev`.
- [ ] **Step 2: Typed English:** "What is the expense ratio of HDFC Small Cap Fund?" → confirm shows "Fee question · HDFC Small Cap" → ticket → console approve → status page answer → Listen (en-IN).
- [ ] **Step 3: Voice English + Hinglish** (real mic): "HDFC mid cap ka exit load kitna hai?" → confirm shows Devanagari or Hinglish text and the intent → ticket → console shows the Hindi translation → approve → status page shows Hindi → Listen (hi-IN, or the fallback notice).
- [ ] **Step 4: Ambiguity and refusal:** "exit load of HDFC mid cap or small cap" → clarifying question; "Should I buy HDFC Small Cap?" → scope notice right away.
- [ ] **Step 5:** Run `grep -cE "ABCDE1234F|9876543210"` on the server log after speaking a PAN and a phone number: the result must be 0. Also check that no new audio files appeared under `api/` (`git status`, plus a search for `*.webm`/`*.mp4`).
- [ ] **Step 6: CHECKPOINT:** stop for the user to try `/ask` and `/console` themselves. Anything they find becomes a failing test, then a fix. Record the results and their sign-off in the ledger.

---

## Not in this plan

- Evals page and eval runs, `/health` MCP handshake, Railway + Vercel deploy, Doc markdown formatting (all Plan 4).
- Plan 2 deferred minors (see `docs/superpowers/plans/2026-11-17-plan-2-ledger.md`).

## Self-Review Notes

- **Spec coverage:**

  | Spec item | Task |
  |---|---|
  | §5.1 speak/type, 60 s, memory-only audio | 1, 7 |
  | §5.2 redacted confirm, intent label, edit/re-record, one clarifying question | 2, 6, 7 |
  | §5.3 ticket code + status, immediate scope notice | 3, 6, 8 |
  | §5.4 listen en-IN/hi-IN, Hindi replies | 4, 8 |
  | §5.5 fallbacks (typing, mic denied, STT failure, short/silent) | 1, 7 |
  | §3 console routes (queue, pulse, sources, approvals, explainers; evals → Plan 4) | 9–11 |
  | §7 Retry in console | 9, 10 |
  | §12 failed tickets shown, with re-run | 3, 9 |
  | §11 Playwright smoke tests | 6 (harness), 7, 9–11 |
- **Deliberate decisions:**
  - Hindi text is produced at draft time and approved with the draft, so nothing unapproved is ever published.
  - Translation is validated by invariants (same URLs, same numbers, no PII), not by the English-only scope filter.
  - An edit drops the translation, because the edited English is what the human approved.
  - The console password lives in `sessionStorage` (per tab, cleared on close).
- **Type consistency:** `PreviewOut.scheme_names` (T1) is used by `intentLabel` (T5) and `ConfirmCard` (T6). `AskIn.scheme_id/channel` (T2) is used by `ask()` (T5–T7). `answer_local` (T4) is used by `TicketView` (T5) and `TicketStatus` (T8). `reprocess` (T3) is used by Queue (T9). The Playwright harness (T6) is used by T7 and T9–11. The `E2E_SEED` path (T10) feeds T10–11.
