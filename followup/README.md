# VADG Follow-up Module

Fully LLM-driven — no disease-registry or rule-based question planner. Every
follow-up question and the running differential come from Gemini calls; the
Python layer here only validates, dedups, and provides a static
(registry-free) safety-net fallback if the LLM is genuinely unreachable.

## Architecture

```
followup/
├── orchestrator.py      # Coordinates the Analyzer/Writer/Critic flow
├── selection.py         # 4-tier candidate selection chain (outer defense-in-depth)
├── websocket_handler.py # WebSocket handler (extracted from app.py)
├── feature_tracking.py  # feature_ids_asked + option fingerprints
├── dimension_mapping.py # term_to_dimension() — static keyword→dimension lookup (registry-free)
├── agents/
│   ├── writer.py        # LLM prompt builder + MCQ generator
│   └── critic.py        # Unified gate before send (dedup/relevance)
├── fallbacks/
│   ├── contextual.py    # Static core-dimension + chief-symptom pattern templates
│   ├── min_depth.py     # GI/respiratory/neuro patterns
│   └── turn_templates.py # Clinical dimension rotation (duration, onset, etc.)
└── validators/
    ├── repetition.py    # Unified Jaccard threshold (0.72)
    ├── mcq_structure.py
    └── mcq_quality.py
```

## Flow

1. **Analyzer** (`orchestrator.update_state_with_answer` → `diagnosis_methods.state_followup.analyze_answer_for_state`)
   — a single combined LLM call updates the differential/findings AND
   pre-generates the next MCQ from the model's own clinical reasoning (no
   rule engine, no computed posterior to anchor to).
2. **Writer** (`agents/writer.py` + LLM) — used when the combined call's
   pre-generated question is rejected by the critic; asks the LLM again with
   the current differential and the list of not-yet-covered clinical
   dimensions.
3. **Critic** (`agents/critic.py`) — rejects repeated/generic/duplicate-option
   questions from EITHER path. `selection.py` wraps `orchestrator`'s output
   through a second, independent critic instance before it's ever sent, as
   defense-in-depth (verified in the 2026-07-06 diagnostic E2E test: it
   caught and replaced repeats that slipped past the inner check).
4. **Contextual fallback** (`fallbacks/contextual.py` →
   `state_followup.build_contextual_fallback_mcq`) — the last-resort,
   no-LLM safety net if Gemini is genuinely unreachable: a mandatory core
   dimension (duration → severity) if uncovered, then a static
   chief-symptom pattern template. Deliberately stays registry-free.

## Repetition Prevention

- Single Jaccard threshold: **0.72** (was 0.65 in app.py vs 0.78 in state_followup.py)
- `feature_ids_asked[]` tracks clinical dimensions (duration, fever_pattern, etc.)
- Option fingerprint dedup via `_asked_option_sigs`
- Turn-indexed suffix hack only as last resort

## Usage

```python
from followup.orchestrator import get_next_followup_question, update_state_with_answer
from followup.selection import select_question_candidate
```

Legacy imports still work:

```python
from Followup_Generation.followup_v5 import get_followup_for_diagnosis_v5
```
