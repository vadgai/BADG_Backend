"""Session/state helpers for the follow-up WebSocket handler."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from diagnosis_methods.patient_state import initialize_patient_state


def dedupe_preserve(items) -> List[str]:
    out = []
    seen = set()
    for item in items or []:
        val = str(item).strip()
        key = val.lower()
        if not val or key in seen:
            continue
        out.append(val)
        seen.add(key)
    return out


def ensure_states(session: Dict, age, gender, symptoms) -> Tuple[Dict, Dict]:
    patient_state = session.get("patient_state")
    if not isinstance(patient_state, dict):
        patient_state = initialize_patient_state(
            age,
            gender or "unknown",
            symptoms if isinstance(symptoms, list) else [str(symptoms)],
        )

    symptom_state = session.get("symptom_state")
    if not isinstance(symptom_state, dict):
        symptom_state = {
            "current_symptoms": list(patient_state.get("identified_symptoms", []) or []),
            "modifiers": [],
            "modifier_map": {
                "duration": "",
                "onset": "",
                "location": "",
                "quality": "",
                "severity": "",
                "aggravating_factors": [],
                "relieving_factors": [],
                "associated_symptoms": [],
            },
            "red_flags": list(patient_state.get("red_flags", []) or []),
            "questions_asked": [],
            "feature_ids_asked": [],
        }

    patient_state["symptom_state"] = symptom_state
    patient_state.setdefault("diagnostic_trace", [])
    patient_state.setdefault(
        "diagnostic_counters",
        {
            "repeated_question_prevention_hits": 0,
            "generic_question_rejection_hits": 0,
            "deterministic_fallback_frequency": 0,
            "out_of_pool_llm_suggestion_rejections": 0,
        },
    )
    session["patient_state"] = patient_state
    session["symptom_state"] = symptom_state
    return patient_state, symptom_state


def sync_structured_state(session: Dict, patient_state: Dict, symptom_state: Dict) -> None:
    symptom_state["current_symptoms"] = dedupe_preserve(patient_state.get("identified_symptoms", []))
    symptom_state["red_flags"] = dedupe_preserve(patient_state.get("red_flags", []))
    symptom_state.setdefault("modifiers", [])
    symptom_state.setdefault("questions_asked", [])
    symptom_state.setdefault("feature_ids_asked", [])
    symptom_state.setdefault(
        "modifier_map",
        {
            "duration": "",
            "onset": "",
            "location": "",
            "quality": "",
            "severity": "",
            "aggravating_factors": [],
            "relieving_factors": [],
            "associated_symptoms": [],
        },
    )
    patient_state["symptom_state"] = symptom_state
    session["symptom_state"] = symptom_state
    session["patient_state"] = patient_state
    session["symptoms"] = symptom_state.get("current_symptoms", [])
    session["negatives"] = patient_state.get("negatives", [])
    session["diagnostic_trace"] = patient_state.get("diagnostic_trace", [])


def top2_from_state(state_obj: Dict) -> List[str]:
    if not isinstance(state_obj, dict):
        return []
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
    return names


def record_question_trace(state_obj: Dict, question_obj: Dict, next_turn: int) -> Optional[Dict]:
    if not isinstance(state_obj, dict):
        return None
    trace = state_obj.setdefault("diagnostic_trace", [])
    if not isinstance(trace, list):
        trace = []
        state_obj["diagnostic_trace"] = trace
    entry = {
        "turn": next_turn,
        "top2_before_question": (
            question_obj.get("differentiates_between")
            if isinstance(question_obj.get("differentiates_between"), list)
            else top2_from_state(state_obj)
        ),
        "selected_discriminator_feature": question_obj.get("feature_id"),
        "question_source": question_obj.get("question_source", "deterministic"),
        "question": question_obj.get("Question"),
        "timestamp": datetime.utcnow().isoformat(),
    }
    trace.append(entry)
    return entry


def update_last_trace_after_answer(state_obj: Dict, signals: Dict) -> None:
    if not isinstance(state_obj, dict):
        return
    trace = state_obj.get("diagnostic_trace")
    if not isinstance(trace, list) or not trace:
        return
    last = trace[-1]
    if not isinstance(last, dict):
        return
    if isinstance(signals, dict):
        last["extracted_new_evidence"] = {
            "new_positive_findings": signals.get("new_positive_findings", []),
            "new_negative_findings": signals.get("new_negative_findings", []),
            "red_flags_detected": signals.get("red_flags_detected", []),
            "modifier_map": signals.get("modifier_map", {}),
        }
    last["top2_after_answer"] = top2_from_state(state_obj)


def mcq_options(question_dict: Dict) -> List[Dict[str, str]]:
    options = []
    for key in ("A", "B", "C", "D", "E"):
        if key in question_dict:
            options.append({"key": key, "value": question_dict[key]})
    return options


def map_client_answer(client_msg_raw: str, last_response: Dict) -> str:
    client_msg_clean = client_msg_raw.strip().upper()
    if client_msg_clean in ("A", "B", "C", "D", "E"):
        mapped = last_response.get(client_msg_clean)
        if mapped:
            return mapped
    # Only match against the actual option display text (A-E) here — never
    # against metadata fields like feature_id/priority/question_source, which
    # are raw internal identifiers (e.g. "pain_location") and would otherwise
    # leak into the patient's answer instead of a real option's label.
    for key in ("A", "B", "C", "D", "E"):
        value = last_response.get(key)
        if isinstance(value, str) and client_msg_clean in value.upper():
            return value
    return client_msg_raw.strip()
