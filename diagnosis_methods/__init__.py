"""
Diagnosis Methods Package

State-based helpers used by the live follow-up pipeline (the `followup/` package):
- patient_state: session state initialization and serialization
- state_followup: answer analysis + contextual fallback helpers

Note: the older chat-history "Method 1/2" flow (methods.py, entropy_tracker.py,
disease_scoring_engine.py) was unused on the live path and has been removed.
"""

from .patient_state import (
    initialize_patient_state,
    update_patient_state,
    state_to_prompt_string,
    state_to_json_string
)
from .state_followup import (
    get_followup_from_state,
    analyze_answer_for_state
)

__all__ = [
    "initialize_patient_state",
    "update_patient_state",
    "state_to_prompt_string",
    "state_to_json_string",
    "get_followup_from_state",
    "analyze_answer_for_state"
]


