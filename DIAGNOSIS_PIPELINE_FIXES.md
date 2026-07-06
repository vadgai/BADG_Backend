# Diagnosis Pipeline Fixes (historical — superseded 2026-07-05)

> **This describes the old hybrid architecture (deterministic disease-registry
> scoring + Bayesian posterior + EIG question targeting), which has since been
> fully replaced.** `diagnosis_rule_engine.py`, `followup/information_gain.py`,
> and `followup/agents/strategist.py` (referenced throughout this doc) were
> **deleted** on 2026-07-05 — the pipeline is now fully LLM-driven with no
> disease-registry dependency. See `PRODUCTION_PARITY_AUDIT_2026-07-05.md`
> ("Pipeline rework" section) for what changed and why, and
> `followup/README.md` for the current architecture. Kept below only as a
> historical record of the fixes that were made to the old system.

Short summary of changes to the follow-up + diagnosis flow.

## Goal
Ask the most relevant, plain-language questions; accurately predict the top-2 diseases; include all reported symptoms in the report.

## What changed

| # | Fix | File |
|---|-----|------|
| 1 | Question flow enforced to **8–12** (hard floor at 8, cap at 12; every early-stop path gated) | `followup/constants.py`, `orchestrator.py`, `agents/strategist.py`, `agents/writer.py`, `diagnosis_methods/state_followup.py` |
| 2 | **Negatives now penalize properly** — denying a disease's key symptoms collapses its score (×0.40 if ≥50% denied, ×0.15 if all denied) | `diagnosis_rule_engine.py` |
| 3 | **Plain ↔ clinical synonym bridges** (burning chest↔heartburn, phlegm↔sputum, coughing up blood↔hemoptysis…) so plain answers match profile terms | `diagnosis_rule_engine.py` |
| 4 | **Every question EIG-driven** — candidates only from top-3 posterior diseases' key/supportive features; a 5-item info-gain shortlist is fed to the LLM instead of all ~30 dimensions | `followup/information_gain.py`, both prompts |
| 5 | **Differential anchored to the Bayesian posterior** — a disease whose key symptoms were denied can't rank top-2; endemic guesses (TB/pertussis) blocked without support | `state_followup.py` |
| 6 | **Near-duplicate diseases deduped** (Bronchitis / Acute Bronchitis → one) so #2 is distinct and posterior mass isn't split | `information_gain.py` |
| 7 | **Report top-2 posterior-anchored** — LLM re-ranker can't float a low-posterior/out-of-pool disease into #2; confidence bands re-derived from posterior (monotonic) | `diagnosis_rule_engine_v5.py` |
| 8 | **Plain-language everywhere** — questions/options in everyday words; symptom cards drop lab/exam jargon (eosinophilia, crackles, IgE) and humanize labels (orthopnea → "breathless lying flat") | `symptom_card.py`, prompts, deterministic fallbacks |

## Flow
1. Analyze initial symptoms → belief-state posterior (rule engine + priors).
2. Generate highest-info-gain, plain-language question distinguishing the top candidates.
3. Each answer updates positives/negatives → posterior recomputed → next question targets the new leaders.
4. Symptom-card selections merge into state (selected = positives, unselected = negatives) and feed later questions.
5. After 8–12 questions (or high-confidence), stop → report ranks top-2 from the posterior, including all reported symptoms + negatives + history.

## Verified
- All Backend files compile; import chain + `app.py` load clean.
- Real Gemini turns produce plain-language, on-target questions.
- Full simulated session: 11 questions, stops at 12, report produced, no exceptions.
- Regression: GERD dropped from top-3 when reflux denied; AKI/CKD stay distinct; endemic guesses gone from top-2.

## Notes
- No dependency/config changes. `DIAG_V6_SCORER` still defaults on.
- Needs Gemini keys in `Backend/.env` (deterministic fallbacks cover the LLM-unavailable case, also plain-language).
- `Backend/` is untracked in git — deploy the files as-is via the usual Backend deploy.
