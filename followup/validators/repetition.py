"""Unified repetition detection for follow-up questions."""

import re
from typing import Dict, List

from followup.constants import JACCARD_REPEAT_THRESHOLD


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _token_set(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", normalize_text(text)) if t}


def jaccard_similarity(a: str, b: str) -> float:
    sa = _token_set(a)
    sb = _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


def extract_asked_questions(patient_state: Dict) -> List[str]:
    """Questions from symptom_state.questions_asked and chat_history bot messages."""
    seen: set = set()
    cleaned: List[str] = []

    symptom_state = (
        patient_state.get("symptom_state")
        if isinstance(patient_state.get("symptom_state"), dict)
        else {}
    )
    for q in symptom_state.get("questions_asked") or []:
        q_text = str(q).strip()
        norm = normalize_text(q_text)
        if q_text and norm not in seen:
            seen.add(norm)
            cleaned.append(q_text)

    for msg in patient_state.get("chat_history") or []:
        if not isinstance(msg, dict):
            continue
        q_text = str(msg.get("bot") or "").strip()
        norm = normalize_text(q_text)
        if q_text and norm not in seen:
            seen.add(norm)
            cleaned.append(q_text)

    return cleaned


def is_repeated_question(
    question: str,
    asked_questions: List[str],
    threshold: float = JACCARD_REPEAT_THRESHOLD,
) -> bool:
    q = normalize_text(question)
    if not q:
        return True
    for asked in asked_questions or []:
        a = normalize_text(asked)
        if not a:
            continue
        if q == a:
            return True
        if jaccard_similarity(q, a) >= threshold:
            return True
    return False
