"""
Legacy follow-up facade — production flow lives in Backend/followup/.

Kept for backward compatibility with methods.py and older tests.
"""

from followup.validators.mcq_structure import normalize_mcq_keys as _normalize_mcq_keys
from followup.validators.mcq_structure import validate_mcq_structure as _validate_mcq_structure


def get_followup_for_diagnosis(*args, **kwargs):
    """Legacy signature shim — prefer get_next_followup_question(patient_state)."""
    if args and isinstance(args[0], dict):
        from followup.orchestrator import get_next_followup_question

        return get_next_followup_question(args[0], **kwargs)
    return None


__all__ = [
    "_normalize_mcq_keys",
    "_validate_mcq_structure",
    "get_followup_for_diagnosis",
]
