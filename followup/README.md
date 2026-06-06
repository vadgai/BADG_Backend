# VADG Follow-up Module (4-Phase Refactor)

## Architecture

```
followup/
├── orchestrator.py      # Coordinates all agents
├── selection.py         # 4-tier candidate selection chain
├── websocket_handler.py # WebSocket handler (extracted from app.py)
├── feature_tracking.py  # feature_ids_asked + option fingerprints
├── agents/
│   ├── strategist.py    # Agent 2 — rule-based disease discriminator (WHAT to ask)
│   ├── writer.py        # Agent 3 — LLM prompt builder (HOW to phrase MCQ)
│   └── critic.py        # Agent 4 — unified gate before send (dedup/relevance)
├── fallbacks/
│   ├── contextual.py    # Symptom-pattern banks
│   ├── min_depth.py     # GI/respiratory/neuro patterns
│   └── turn_templates.py # Clinical dimension rotation (duration, onset, etc.)
└── validators/
    ├── repetition.py    # Unified Jaccard threshold (0.72)
    ├── mcq_structure.py
    └── mcq_quality.py
```

## Agent Flow

1. **Analyzer** (`orchestrator.update_state_with_answer`) — updates symptoms/differential after each answer
2. **Strategist** (`agents/strategist.py`) — picks disease-specific feature via rule engine
3. **Writer** (`agents/writer.py` + LLM) — generates MCQ when strategist has no rule match
4. **Critic** (`agents/critic.py`) — rejects repeated/generic/duplicate-option questions

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
