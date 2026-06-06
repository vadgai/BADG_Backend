"""Clinical quality checks for generated MCQ payloads."""

from typing import Dict, List, Tuple

from followup.constants import GENERIC_QUESTION_MARKERS, PLACEHOLDER_MARKERS
from followup.validators.repetition import extract_asked_questions, is_repeated_question, normalize_text


def contains_placeholder_text(text: str) -> bool:
    t = normalize_text(text)
    if not t:
        return True
    return any(marker in t for marker in PLACEHOLDER_MARKERS)


def is_generic_question(text: str) -> bool:
    t = normalize_text(text)
    if not t:
        return True
    return any(marker in t for marker in GENERIC_QUESTION_MARKERS)


def validate_mcq_quality(mcq: Dict, patient_state: Dict) -> Tuple[bool, str]:
    question = str(mcq.get("Question", "")).strip()
    options = [str(mcq.get(key, "")).strip() for key in ("A", "B", "C", "D", "E")]
    combined = " ".join([question] + options).lower()

    if not question or not all(str(mcq.get(key, "")).strip() for key in ("A", "B", "C", "D")):
        return False, "missing_required_fields"
    if contains_placeholder_text(combined):
        return False, "placeholder_text_detected"
    if is_generic_question(question):
        return False, "generic_question_detected"

    asked_questions = extract_asked_questions(patient_state)
    if is_repeated_question(question, asked_questions):
        return False, "repeated_question_detected"

    option_keys = {normalize_text(mcq.get(key, "")) for key in ("A", "B", "C", "D")}
    if len(option_keys) < 4:
        return False, "non_distinct_options"

    e_norm = normalize_text(str(mcq.get("E", "")))
    if mcq.get("E") and "none" not in e_norm and "not sure" not in e_norm:
        return False, "invalid_option_e"

    return True, "ok"
