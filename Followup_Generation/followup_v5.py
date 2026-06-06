"""
Follow-up v5 — backward-compatible facade over followup.orchestrator.
"""

from followup.orchestrator import (
    get_next_followup_question as get_followup_for_diagnosis_v5,
    update_state_with_answer as update_state_with_answer_v5,
)

__all__ = ["get_followup_for_diagnosis_v5", "update_state_with_answer_v5"]
