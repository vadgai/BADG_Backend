# Production Parity Audit — 2026-07-05

Summary of the auth/billing audit, live end-to-end test, and dev-vs-prod
investigation done this session, and what was fixed. Updated after a second
pass following a redeploy that the user reported still wasn't working
correctly.

## What was done

- Full audit of the auth + entitlement system (anonymous free report → login
  required → credit-based generation), read against the actual running code.
- Ran the backend (`uvicorn`) and frontend (`vite`) together locally and drove
  the real flow through the browser: anonymous diagnosis → free report →
  login-required gate → register → verify email → login → logged-in report →
  credit exhaustion → 402 handling.
- Compared production (Cloud Run) against local dev by hitting the live API
  directly and reading Cloud Run logs, after the user reported symptom cards
  missing in production only.
- After a redeploy (revision `vadg-backend-00115`), re-tested production end
  to end (symptom → card → websocket follow-up → register) and read Cloud Run
  logs again, since the user reported it still wasn't behaving like dev.

## Errors found & fixed

| # | Bug | Root cause | Fix | File(s) | Status |
|---|-----|-----------|-----|---------|--------|
| 1 | Two different sessions could both spend the same last free report / credit | `check_and_consume` read the balance, computed `balance - 1` in Python, then blind-`$set` it — no atomicity across concurrent requests | Atomic conditional DB writes (`try_consume_credit`, `try_consume_free_report`) that re-check balance at commit time | `billing/entitlements.py`, `auth/user_service.py` | Deployed |
| 2 | Admin double-clicking "Approve" could grant purchase credits twice | Same read-then-write race on the payment's `pending → paid` transition | Atomic conditional status transition before granting credits | `billing/payments.py` | Deployed |
| 3 | Re-fetching/refreshing an already-unlocked report could wrongly return 401/402, forcing a needless re-login | The entitlement *peek* checked "is there balance right now" instead of "was this exact session already paid for" | Check `session_already_unlocked` first, before any balance/anon gate | `app.py`, `billing/entitlements.py`, `billing/anon_entitlements.py` | Deployed |
| 4 | Anonymous free-report gate crashed in private browsing | `getAnonId()` had no try/catch around `localStorage` | Try/catch + in-memory fallback id | `Frontend/src/utils/anonId.ts` | **Needs Netlify deploy** |
| 5 | Out-of-credits screen said *"Service Temporarily Unavailable... try again in a few minutes"* and still showed a "Download PDF Report" button that re-triggered the same wrong message | Error UI was hardcoded to one generic message; download section rendered unconditionally regardless of whether a report existed | Track real error kind, show "No Reports Remaining" + Purchase-credits CTA; hide download UI until the report preview reports success | `Frontend/src/components/DiagnosisReport.tsx`, `DiagnosisReportPreview.tsx` | **Needs Netlify deploy** |
| 6 | Symptom cards / disease matching / diagnosis reports silently degraded in production only — logs showed `Loaded 0 disease(s) from /app/diseases`; reports fell back to `"AI system temporarily unavailable"` | `.gcloudignore`/`.gitignore` had a blanket `*.json` rule excluding all 303 `diseases/D*.json` files from every deploy | Added `!diseases/*.json` exception to both | `.gitignore`, `.gcloudignore` | **Verified fixed in prod** (revision 00115 logs: `Loaded 303 disease(s)`) |
| 7 | Every deploy uploaded ~12,700 unnecessary files | `.gcloudignore`/`.dockerignore` excluded `venv/`/`env/`/`ENV/` but not the actual `.venv/` folder used here | Added `.venv/` to both | `.gcloudignore`, `.dockerignore` | Fixed locally, included in next deploy |
| 8 | **Follow-up questions / symptom cards intermittently return "Session not found" / "Invalid session_id" in production only** — reproduced live: `POST /symptom` succeeds, the very next call (`GET /session`, or the follow-up websocket) 404s for the session that was just created | Cloud Run serves traffic immediately at startup and connects to MongoDB in a background task (by design, to avoid Cloud Run startup-probe timeouts). A session created before that connection finishes is saved only in that one instance's in-memory dict — Cloud Run does **not** guarantee later requests for the same session land on the same instance, so another instance's restore-from-MongoDB fallback finds nothing | `save_session`/`load_session` now wait (bounded, ~8s) for an in-flight MongoDB connection to finish before giving up, via a new `wait_if_connecting()` helper, instead of silently treating "not connected yet" the same as "no database at all" | `database/connection.py`, `database/session_persistence.py` | Fixed locally, **not yet deployed** |
| 9 | **Registration/login return HTTP 500 in production, don't in dev** — traceback: `AttributeError: module 'bcrypt' has no attribute '__about__'` inside passlib's bcrypt backend detection | `requirements.txt` pins `passlib[bcrypt]==1.7.4` but never pins `bcrypt` itself. Passlib 1.7.4 (2020) reads `bcrypt.__about__.__version__`, which `bcrypt>=4.1` removed. Local dev's venv happens to have the older `bcrypt==4.0.1` already installed; a fresh Docker build resolves the newest bcrypt at build time and breaks | Pinned `bcrypt==4.0.1` (matching local dev exactly) in `requirements.txt` | `requirements.txt` | Fixed locally, **not yet deployed** |
| 10 | **Container is memory-starved and crash-looping** — Cloud Run logs show `Memory limit of 256 MiB exceeded` roughly every 7 seconds, continuously, at idle | The service is deployed with only **256Mi** (Cloud Run's absolute default) even though the project's own `deploy.sh` specifies `--memory=1Gi`; the actual commands run omitted `--memory` | **Not yet applied** — requires `gcloud run services update vadg-backend --memory=1Gi` (a live prod infra change); blocked pending explicit user confirmation | Cloud Run service config | **Needs your go-ahead** |

Bug #10 is likely the single biggest contributor to "prod doesn't behave like
dev" — a container OOM-crashing every few seconds restarts the whole process,
wiping all in-memory session state and compounding bug #8 far beyond a
one-time cold-start race.

## Improvements made
- Race conditions and duplicate charging are closed for both user-facing
  credit consumption and admin payment approval.
- Idempotent report access no longer depends on a live balance check.
- Error messaging correctly distinguishes "buy more credits" from "something's
  actually broken."
- Deploy uploads are ~28x smaller (13,158 → 461 files) and now include the
  data the app actually needs.
- Session persistence survives the startup race window instead of silently
  dropping the first session(s) a fresh instance ever creates.
- Password hashing no longer depends on whatever bcrypt version happens to be
  latest at build time.

## Still outstanding — action needed
1. **Bump Cloud Run memory to 1Gi** (`gcloud run services update vadg-backend --project=positive-shell-475102-t5 --region=asia-south1 --memory=1Gi`) — safe, reversible, no rebuild needed. Blocked on your confirmation.
2. **Commit** the staged changes (309 files: disease data + 2 ignore-file fixes + connection/session-persistence fix + requirements.txt) and **redeploy the backend** so bugs #8 and #9 actually reach production.
3. **Redeploy the frontend to Netlify** — bugs #4 and #5 are frontend-only and won't ship from a backend redeploy.

---

## Pipeline rework — fully LLM-driven diagnosis (2026-07-05, later same day)

Per explicit direction, the diagnosis pipeline was converted from a hybrid
(deterministic 303-disease registry + 4 layered Gemini calls) to **fully
LLM-driven, with zero rule-based/registry dependency**. The disease-folder gap
that motivated this (zero psychiatric conditions in the 303 hand-authored
profiles, so anxiety/depression could never be data-backed) is now moot — the
model reasons over the full evidence trail itself, with no predefined list to
be constrained to.

### What changed
- **Deleted**: `diagnosis_rule_engine.py` (registry/scoring core), `followup/information_gain.py` (EIG/Bayesian posterior engine), `followup/agents/strategist.py` (rule-based question planner). The 303 `diseases/*.json` files are left on disk, unreferenced by any code path.
- **Rewrote** `diagnosis_rule_engine_v5.py`: final diagnosis now comes from one Gemini call over the patient's own accumulated differential (tracked turn-by-turn through the follow-up loop) plus the full Q&A history — no registry scoring, no posterior anchoring. Anti-hallucination guard: a suggested condition is rejected unless its reasoning cites the patient's actual confirmed findings and doesn't contradict a denied one.
- **`symptom_card.py`**: `generate_symptom_card()` now calls a new `_llm_symptom_card()` Gemini call instead of the registry-backed information-gain ranker, returning the same `{top_conditions, organ_systems, symptoms}` shape so the rest of the module (label cleaning, clinical-factor tailoring) needed no change.
- **`diagnosis_methods/state_followup.py`**: the combined analyze+next-question prompt no longer anchors to a "computed posterior"; it now uses independent clinical reasoning while keeping every other guardrail (denied-symptom contradiction handling, chronicity reasoning, India-endemic-context-only-if-supported, explicit High/Moderate/Low rubric).
- **`followup/orchestrator.py` / `followup/agents/writer.py`**: strategist step removed from the standard question-generation chain; the LLM writer path now also runs through `QuestionCritic` (feature-id + option-overlap dedup), which it previously skipped — this was a real gap this refactor exposed and fixed (see bug below).
- New lightweight smoke test: `tests/smoke_diagnosis_pipeline.py` (replaces two deleted registry-dependent test files).

### Bugs found and fixed during live verification
| # | Bug | Root cause | Fix |
|---|-----|-----------|-----|
| 1 | Symptom cards returned empty (`symptoms: []`) after the pure-LLM conversion | `_llm_symptom_card()`'s `max_output_tokens=500` was too small for a 16-symptom JSON payload — Gemini's response got cut off mid-JSON and `extract_json_from_text` silently failed to parse it | Raised to `max_output_tokens=1000` |
| 2 | First follow-up question after the symptom card sometimes re-asked "how long have you had this" even though duration was already answered on the card | `orchestrator._generate_llm_question()` (the standard writer path, now the *only* path since the strategist was removed) only ran `validate_mcq_quality` — never `QuestionCritic`'s feature-id/option-overlap check, unlike the fast-path. The LLM occasionally mislabeled a duration-themed question under a different `feature_id`, dodging the "already covered" list | Added the same `QuestionCritic.validate_with_reason()` check to the writer path that the fast-path already had |

### Live E2E verification
Ran a full 12-turn "anxiety" case through the browser (patient info → symptom
card → 12 follow-up MCQs incl. midpoint/refined cards → report), backend
restarted between each fix to pick up changes. Result: no crashes, no
`diagnosis_rule_engine`/`information_gain` references anywhere in the codebase
(confirmed by a full-tree grep), well-formed single-dimension MCQs throughout,
and a final report that:
- Correctly diagnosed **Generalized Anxiety Disorder** as the primary condition, consistent with the collected findings (chronic >3wk course, gradual onset, no clear precipitant, autonomic symptoms, worry/restlessness/sleep disturbance).
- **Rejected two ungrounded LLM suggestions** ("Caffeine-induced anxiety", "Adjustment Disorder") via the anti-hallucination guard, since the patient's answers didn't actually support them (symptoms occurred "regardless" of caffeine; no specific triggering event).
- Produced specific, non-generic next steps (TSH to rule out hyperthyroidism, CBC, CMP, GAD-7 screening) tied to the actual differential.

Known follow-up item (spun off separately, not part of this refactor): the
final report's symptom list sometimes shows raw internal tokens (e.g.
`duration_less_than_one_month`, `first_episode`) alongside proper text —
traced to `symptom_extractor_v5.py`'s MCQ-answer signal extraction, unrelated
to the registry removal.

### Token / cost profile (measured, not estimated)

Instrumented a full replica of the real pipeline (same functions the live
endpoints call) by wrapping the Gemini SDK's `generate_content` and reading
each response's actual `usage_metadata`, for one complete session: initial
symptom submission → symptom card → 12 follow-up turns (with midpoint/refined
cards) → final diagnosis → report.

**Per full report generation (average, 1 run measured):**

| Metric | Value |
|---|---|
| Gemini API calls | **21** |
| Prompt tokens | **21,938** |
| Output tokens | **7,796** |
| **Total tokens** | **≈ 29,700** |

Stage breakdown:
- Initial symptom extraction: ~150 tokens (1 call)
- Initial symptom card: ~760 tokens (1 call)
- 12 follow-up turns (combined analyze+next-question call each): ~1,580–1,830 tokens/turn, **~21,000 tokens total** — the majority of the session's cost, since each turn resends the full running clinical context (confirmed/denied findings, differential, Q&A history)
- 2–3 extra writer-fallback calls (only fire when the combined call's proposed question gets rejected by the critic, e.g. a repeat): ~900 tokens each
- Midpoint symptom card: ~820 tokens (1 call)
- Refined symptom card: ~820 tokens (1 call)
- Final diagnosis: ~1,460 tokens (1 call)
- Final report: ~2,135 tokens (1 call)

This is now the **entire** per-session Gemini cost, since there is no more
deterministic scoring layer to offset any of it — every stage that used to be
free (registry lookup, EIG ranking, posterior computation) is now a Gemini
call. Compared to the old hybrid pipeline, this trades zero marginal
API cost for the removed rule-engine stages against fully LLM-grounded
reasoning with no disease-folder ceiling on diagnosable conditions.

---

## Diagnostic-accuracy E2E test + critical bug fix (2026-07-06)

Built an automated test harness (`tests/smoke_diagnosis_pipeline.py` covers
the mechanical smoke test; a separate scratch harness drove full clinical
cases) that plays a hidden ground-truth vignette against the real pipeline
via a second "patient simulator" Gemini call — the simulator answers
follow-up questions truthfully in plain language without ever naming the
diagnosis, so the pipeline's own reasoning is what's being graded. Three
cases, chosen to stress different specialties: **acute appendicitis**
(surgical abdomen), **primary hypothyroidism** (chronic endocrine), **acute
coronary syndrome** (cardiac emergency).

### Critical bug found: anti-hallucination guard rejected correct diagnoses

First run: the appendicitis case's final diagnosis dropped "Acute
appendicitis" — the LLM's own `diagnosis_summary` field correctly described
"classic acute appendicitis," but the `conditions` array that survived
filtering contained only "Ovarian torsion" (Low probability, with reasoning
that actually argued *against* torsion). Repro testing (6 samples of the same
prompt) showed a **100% false-rejection rate** for the correct top diagnosis.

**Root cause**: `diagnosis_rule_engine_v5.py`'s `_condition_supported_by_evidence()`
rejected any condition whose reasoning mentioned a denied/negative finding
*at all* — even when correctly citing it as ruled out ("the absence of
vomiting does not exclude...", "the patient denied a missed period..."). That
is exactly how real clinical reasoning explains why competing diagnoses are
less likely, so the guard was rejecting good reasoning far more often than it
was ever catching a real hallucination.

**Fix**: added negation-aware matching (`_term_asserted_as_present()`) — a
denied finding only triggers rejection if it appears in the reasoning
*without* a negation cue ("no", "denied", "absence of", "ruled out", "lacks",
etc.) earlier in the same clause. Verified via repeated sampling: the primary
diagnosis is now kept in 6/6 and 12/12 samples across two verification runs
(previously 0/5). A secondary, lower-stakes effect remains — a *Low*-probability
alternative whose reasoning is built entirely around exclusion (no positive
finding cited) can still get dropped by the separate positives-check, which
only affects differential completeness, never the primary diagnosis.

### Final results (after the fix), ground truth vs. predicted

| Case | Ground truth | Predicted (High confidence) | Urgency | Notes |
|---|---|---|---|---|
| Acute appendicitis | Acute appendicitis | **Acute appendicitis** | Emergency | Correct; 2 reasonable Low-probability alternatives (mesenteric adenitis, ovarian torsion) kept with sound exclusion reasoning |
| Primary hypothyroidism | Hypothyroidism | **Primary Hypothyroidism** | Routine | Correct; family history correctly weighted; MDD/iron-deficiency anemia correctly considered and dismissed |
| Acute coronary syndrome | ACS / MI | **STEMI** | Emergency | Correct; aortic dissection correctly considered and dismissed (no tearing back pain / pulse deficit) |

Follow-up question quality was also reviewed: `select_question_candidate`'s
outer critic layer correctly intervened and substituted a fallback question
several times across all three cases when the LLM writer proposed a
subtly-repeated question — confirming the defense-in-depth question-dedup
chain (inner orchestrator critic + outer `selection.py` critic) works as
designed even when one layer alone would have let a repeat through.

---

## Billing/credit flow E2E test (2026-07-06)

Drove the real HTTP API end-to-end (register/login, `/symptom`,
`/generate_report`, direct Mongo balance checks) against a running local
backend. All of the following passed:

1. Anonymous user's first free report succeeds; re-fetching the same report
   afterward still succeeds (idempotent, no double charge).
2. A second anonymous diagnosis attempt (same device) is blocked with
   **401 `login_required`** — at `/symptom` itself, before any session is
   created, not deep in the flow.
3. A logged-in user with zero free-reports-today and zero credits gets
   **402 `no_reports_remaining`** with a message that triggers the frontend's
   "Buy Credits" CTA.
4. Granting credits and generating a report deducts **exactly 1 credit** and
   increments `total_reports` by exactly 1; re-fetching the same report
   afterward does not charge a second time.
5. A second new diagnosis session for the same user correctly draws down a
   second credit.

**Note on "24-hour" framing**: there is no 24-hour window anywhere in the
current design — the anonymous free report is a permanent one-time grant per
device (until local storage is cleared), and the logged-in daily free report
resets at UTC midnight, not on a rolling 24h timer. Confirmed with the
project owner that this is the intended behavior; no code change made. See
`BILLING_SYSTEM.md` for the accurate, up-to-date description.

---

## Known dead code found during the security/stability pass (2026-07-06)

`app.py` has an entire second generation of infrastructure modules
(`config.py`, `middleware.py`, `logging_config.py`, `exceptions.py`,
`session_manager.py`, `api_utils.py`, `health_check.py`, `models.py`) that
were fully written but **never wired in** — the imports are commented out at
the top of `app.py` with the note "commented out until modules are created,"
even though the modules now exist. Notably `middleware.py`'s
`RateLimitMiddleware` and `SecurityHeadersMiddleware` are complete,
functional, defense-in-depth hardening that is currently inert.

**Action taken**: wired in `RateLimitMiddleware` only (100 req/min per IP by
default, configurable via `config.py`'s `Settings.rate_limit_requests`/
`_window`) — verified `config.get_settings()` loads cleanly against the real
`.env`, restarted the backend, and confirmed: `/docs`, `/health`, and CORS
preflight all still work normally, and hammering `/health` past the limit
correctly returns 429 after ~94-100 requests/min while normal traffic passes
through untouched.

**Deliberately left unwired** (would need dedicated testing before enabling):
- `SecurityHeadersMiddleware` — its hardcoded CSP (`script-src 'self'
  'unsafe-inline' https://fonts.googleapis.com`) doesn't allowlist the CDN
  FastAPI's default `/docs` (Swagger UI) loads its JS/CSS from, so enabling it
  globally as-is would likely break the API docs page. Needs a CSP tailored to
  what this app actually serves before it's safe to turn on.
- `HealthCheckMiddleware` — would duplicate `app.py`'s own existing `/health`
  route (different response shape); redundant, not turned on.
- `CORSSecurityMiddleware` — would duplicate/could conflict with the
  `CORSMiddleware` already active from FastAPI's own package; not needed.
- `RequestIDMiddleware` / `LoggingMiddleware` — nice-to-have observability,
  not security-critical; left for a future, dedicated pass.

## Production-readiness summary (2026-07-06)

- **Diagnosis pipeline**: fully LLM-driven (no disease-registry dependency),
  verified accurate across 3 clinically distinct E2E cases after fixing a
  critical anti-hallucination-guard bug (see above). Smoke test
  (`tests/smoke_diagnosis_pipeline.py`) passes.
- **Billing/credits**: full E2E flow verified (free report, login gate, 402
  Buy Credits, exact credit deduction, idempotent re-fetch, race-safe atomic
  consumption from the earlier audit pass in this same document).
- **Auth**: bcrypt hashing pinned to a known-working version, JWT + refresh
  rotation, RBAC hardened, per-action + now global rate limiting, email
  verification, enumeration-resistant password reset.
- **Secrets**: no hardcoded API keys/DB credentials found in tracked code;
  `.env` is gitignored and not tracked; only variable *names* were ever
  inspected for the live Cloud Run service, never values.
- **CORS**: explicit origin allowlist (not a wildcard), credentials scoped
  correctly.
- **New defense-in-depth**: global per-IP rate limiting now active (see
  above).
- **Still outstanding from the earlier audit pass** (unrelated to this pass,
  not yet actioned): bump Cloud Run memory to 1Gi, commit + redeploy backend
  and frontend to ship the fixes recorded in this document to production.

---

## Question relevance + early-stop tuning (2026-07-06, later pass)

Goal: ask only the highest-information questions that best split the leading two
diagnoses, and stop as soon as confidence is genuinely high instead of always
running to 8–12.

### Changes
- **Confidence-gated early stop** (`followup/constants.py`,
  `followup/selection.py`): new `EARLY_STOP_MIN_QUESTIONS=5` /
  `EARLY_STOP_CONFIDENCE=0.85`. Two helpers in `selection.py`:
  - `can_stop_early()` — honors an LLM "ready" signal from question 5 onward
    only when the tracked state independently agrees (confidence_score ≥ 0.85
    **and** top differential = High); below 5, never.
  - `should_stop_now()` — **autonomous** stop when the top is High, the
    runner-up is Low, and confidence ≥ 0.85, *even if the LLM keeps proposing
    confirmatory questions*. Added because the combined "ask a question OR
    stop" prompt is biased toward always producing a question (observed:
    conf 0.90/top=High from Q5, yet 6 more questions followed).
  - Wired into `orchestrator.get_next_followup_question`,
    `selection.select_question_candidate`, and `websocket_handler`. The
    combined call's `ready_for_diagnosis` signal is now preserved
    (`_llm_ready_for_diagnosis`) instead of being silently dropped.
- **Maximum-information-gain question instruction** (both prompts in
  `agents/writer.py` and `diagnosis_methods/state_followup.py`): the model must
  pick the single unknown finding that most changes the #1-vs-#2 ranking, skip
  any dimension whose answer wouldn't move the top-2, and only use
  history/exposure dimensions when they directly separate the leaders. Each
  `next_question` now carries `differentiates_between` + a `why` rationale
  (auditability). Symptom-card prompt similarly sharpened to offer only
  discriminating symptoms + 1–2 red flags, never findings all candidates share.

### E2E verification (patient-simulator harness, hidden vignettes)
Three cases, correct primary diagnosis in all, **all stopped early** with
targeted, plain-language, rationale-bearing questions (no generic ones):

| Case | Questions | Result | Notes |
|---|---|---|---|
| Migraine w/ aura | 5 | **Migraine** (High) | Stopped at 5; TTH ruled out. Subtype (with-aura) not always resolved when it stops this early — acceptable, primary dx correct |
| GERD | 5 | **GERD** (High) | Stopped at 5; painful-swallowing/nausea/weight-loss used to rule out esophagitis & PUD |
| Community-acquired pneumonia | 7 | **CAP / S. pneumoniae** (High) | TB actively probed (fever pattern, hemoptysis, night sweats, weight loss) and correctly dismissed |

Every question's `why` field tied it to a concrete #1-vs-#2 split; no
history/exposure question fired as routine screening.

---

## Question-relevance + accuracy pass #2 (2026-07-06, later)

Re-ran the patient-simulator harness on 3 fresh hidden vignettes (COPD in a
smoker, dengue, symptomatic gallstones). First run exposed three concrete
gaps, all now fixed and re-verified.

### Gaps found
1. **Min-question floor drifted.** `EARLY_STOP_MIN_QUESTIONS` was 5, letting
   sessions stop at 5; spec is min 8. → Set to 8 (`constants.py`), so early
   stop only happens in the 8–12 window.
2. **A generic question could still slip in.** When the LLM question was
   rejected by the outer critic (or the orchestrator's own chain fell to a
   static template), the session asked a filler *"How severe are your
   symptoms?"* (`core_dimension`, no `why`). Seen at dengue-Q8 and gallstones-Q6.
3. **Final diagnosis over-weighted a shared symptom.** Dengue → **Chikungunya**
   (severe joint pain flipped it; retro-orbital pain was never *asked*, only
   surfaced passively on the card). Gallstones → **Chronic Cholecystitis**
   (upgraded on "months" duration despite no fever/inflammation).

### Fixes
- **LLM-writer retry before static fallback** (`selection.py` +
  `orchestrator.regenerate_llm_question` + `agents/writer.py`): when the primary
  is rejected *or* is a low-value generic template (`core_dimension` /
  `pain_severity`), re-ask the writer once — excluding the rejected dimension,
  temp 0.35, "pick a DIFFERENT discriminator" — and use that instead. Generic
  static templates are now a last resort, not a first fallback. (~1 extra Gemini
  call only on a rejection/low-value turn; tracked via `llm_retry_frequency`.)
- **Pathognomonic-first probing** (writer + combined prompts): if a top suspect
  has an unasked hallmark finding (retro-orbital pain→dengue, right-shoulder
  radiation→gallstones), ask THAT before any nonspecific shared symptom.
- **Weight-by-specificity + no over-calling chronicity** (combined + final
  prompts): a hallmark finding outweighs a shared one (don't let one shared
  symptom flip #1); never assign a chronic/inflammatory label without an
  inflammatory sign — recurrent episodes alone stay the simpler diagnosis.

### Re-verification (after fixes)
| Case | Questions | Result | Notes |
|---|---|---|---|
| COPD (smoker) | 8 | **COPD** (High) | Smoking/sputum-color/reversibility used; TB & bronchiectasis ruled out |
| Dengue | 8 | **Dengue** (High) | Q3 now proactively asks retro-orbital pain ("hallmark, highly specific to dengue"); Chikungunya correctly demoted to #2 |
| Gallstones | 8 | **Symptomatic Cholelithiasis** (High) | Chronicity guard held on "months" duration (no fever); every question LLM-driven, zero generic fillers |

All three: correct primary, stopped at the 8 floor (no wasted questions to 12),
zero generic questions, every follow-up carried a `why` tied to a #1-vs-#2 split.
Full compile + import chain + `app.py` load verified clean.

> Note: E2E harness runs consume Gemini free-tier quota quickly (~25–30 calls
> per case); heavy same-day re-testing may hit the 500/day limit.
