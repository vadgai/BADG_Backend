"""
Diagnosis Methods Package

This package contains:
- Method 1: Chat History-based diagnosis (original approach)
- Method 2: State-Based diagnosis (new hybrid approach)
"""

from .methods import run_diagnosis_method_1, run_diagnosis_method_2
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
    "run_diagnosis_method_1",
    "run_diagnosis_method_2",
    "initialize_patient_state",
    "update_patient_state",
    "state_to_prompt_string",
    "state_to_json_string",
    "get_followup_from_state",
    "analyze_answer_for_state"
]


