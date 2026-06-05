"""
Follow-up v5
Reasoning loop that uses structured state and symptom signal extraction.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Tuple, Union

from diagnosis_methods.state_followup import (
    get_followup_from_state,
    analyze_answer_for_state,
    build_contextual_fallback_mcq,
)
from diagnosis_methods.patient_state import update_patient_state
from symptom_extractor_v5 import extract_signals, apply_signals_to_state

logger = logging.getLogger(__name__)


def _fallback_question(patient_state: Dict[str, Any]) -> Union[Dict[str, str], str]:
    fallback = build_contextual_fallback_mcq(patient_state if isinstance(patient_state, dict) else {})
    if isinstance(fallback, dict):
        fallback.setdefault("D", "I'm not sure")
        fallback.setdefault("E", "None of these / Not sure")
        fallback.setdefault("allow_other", True)
        fallback.setdefault("priority", "high")
        fallback.setdefault("clinical_intent", "Differentiate top competing diagnoses using structured evidence")
        fallback.setdefault("differentiates_between", ["Top suspect #1", "Top suspect #2"])
        fallback.setdefault("question_source", "deterministic")
        return fallback
    return fallback


def update_state_with_answer_v5(
    patient_state: Dict[str, Any],
    question: str,
    answer: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Update patient state using:
    1) symptom_extractor_v5 (+/- findings)
    2) analyze_answer_for_state (differential + differentiator)
    """
    if not isinstance(patient_state, dict):
        return patient_state, {"signals": None, "analysis": None}

    # Heuristic-only signal extraction (no LLM call). The LLM-based
    # analyze_answer_for_state below already extracts new symptoms/negatives and
    # the differential, so keeping this deterministic avoids a redundant Gemini
    # call per turn and preserves quota for the diagnostic reasoning + question.
    signals = extract_signals(
        current_state=patient_state,
        patient_response=answer,
        last_question_text=question,
        use_llm=False,
    )
    apply_signals_to_state(patient_state, signals)

    analysis = analyze_answer_for_state(question, answer, patient_state)
    if analysis:
        patient_state = update_patient_state(patient_state, question, answer, analysis)
    else:
        # Ensure turn count still advances even if analysis fails.
        patient_state["turn_count"] = patient_state.get("turn_count", 0) + 1
        patient_state["last_updated"] = datetime.utcnow().isoformat()

    return patient_state, {"signals": signals, "analysis": analysis}


def get_followup_for_diagnosis_v5(
    patient_state: Dict[str, Any],
    max_retries: int = 1,
) -> Union[Dict[str, str], str, None]:
    """
    Generate next follow-up question using the v5 reasoning loop.
    """
    if not isinstance(patient_state, dict):
        return None

    patient_state.setdefault("chat_history", [])

    try:
        response = get_followup_from_state(
            patient_state=patient_state,
            max_retries=max_retries,
        )
    except Exception as exc:
        logger.warning("get_followup_for_diagnosis_v5: error: %s", exc)
        return _fallback_question(patient_state)

    if response is None:
        return _fallback_question(patient_state)

    # Pass through ready signal
    if isinstance(response, str) and "ready for diagnosis" in response.lower():
        return "Ready for diagnosis"

    # Ensure D and E are present
    if isinstance(response, dict):
        response.setdefault("D", "I'm not sure")
        response.setdefault("E", "None of these / Not sure")
        response.setdefault("allow_other", True)
        response.setdefault("priority", "high")
        response.setdefault("clinical_intent", "Differentiate top competing diagnoses using structured evidence")
        response.setdefault("differentiates_between", ["Top suspect #1", "Top suspect #2"])
        response.setdefault("question_source", "llm")
        return response

    return _fallback_question(patient_state)
