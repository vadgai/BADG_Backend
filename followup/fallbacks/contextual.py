"""Tier-1 contextual fallback — delegates to state_followup banks."""

from typing import Dict, Union


def build_contextual_fallback(patient_state: Dict, symptom_state: Dict) -> Union[Dict, str]:
    from diagnosis_methods.state_followup import build_contextual_fallback_mcq

    fallback = build_contextual_fallback_mcq(patient_state if isinstance(patient_state, dict) else {})
    if isinstance(fallback, dict):
        fallback.setdefault("D", "None of these")
        fallback.setdefault("E", "None of these / Not sure")
        fallback.setdefault(
            "priority",
            "red-flag" if symptom_state.get("red_flags") else "high",
        )
        fallback.setdefault(
            "clinical_intent",
            "Differentiate top competing diagnoses using current structured symptom evidence",
        )
        fallback.setdefault("differentiates_between", _top2_from_state(patient_state))
        fallback.setdefault("allow_other", True)
        fallback.setdefault("question_source", "deterministic")
    return fallback


def _top2_from_state(state_obj: Dict):
    if not isinstance(state_obj, dict):
        return ["Top suspect #1", "Top suspect #2"]
    ddx = state_obj.get("differential_diagnosis")
    names = []
    if isinstance(ddx, list):
        for item in ddx:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name:
                names.append(name)
            if len(names) >= 2:
                break
    return names if len(names) >= 2 else ["Top suspect #1", "Top suspect #2"]
