"""
Agent 2 — Question Strategist (rules-first).

Decides WHAT clinical dimension to ask next using disease-profile discriminators
before falling back to open-ended LLM question generation.
"""

import logging
from typing import Any, Dict, Optional, Union

from followup.feature_tracking import is_feature_already_asked
from followup.validators.mcq_quality import validate_mcq_quality

logger = logging.getLogger(__name__)


def _deterministic_top2_and_feature(patient_state):
    from diagnosis_methods.state_followup import _deterministic_top2_and_feature as _fn

    return _fn(patient_state)


def plan_next_question(patient_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Rule-based strategist: pick a disease-differential MCQ when possible.

    Returns:
        MCQ dict ready to send, or None to defer to LLM writer.
    """
    if not isinstance(patient_state, dict):
        return None

    turn_count = int(patient_state.get("turn_count", 0) or 0)
    if turn_count >= 12:
        return "Ready for diagnosis"

    symptom_state = (
        patient_state.get("symptom_state")
        if isinstance(patient_state.get("symptom_state"), dict)
        else {}
    )

    try:
        result = _deterministic_top2_and_feature(patient_state)
    except Exception as exc:
        logger.warning("strategist: rule engine failed: %s", exc)
        return None

    if not isinstance(result, dict):
        return None

    question = result.get("question")
    if not isinstance(question, dict) or not question.get("Question"):
        return None

    feature_id = str(question.get("feature_id", "")).strip()
    if feature_id and is_feature_already_asked(symptom_state, feature_id):
        logger.info("strategist: skipping feature_id=%s (already asked)", feature_id)
        return None

    top_two = result.get("top_two")
    if isinstance(top_two, list) and top_two:
        question.setdefault("differentiates_between", top_two[:2])

    question.setdefault("question_source", "strategist_rule")
    question.setdefault("allow_other", True)
    question.setdefault("E", "None of these / Not sure")

    ok, reason = validate_mcq_quality(question, patient_state)
    if not ok:
        logger.info("strategist: rule MCQ rejected (%s)", reason)
        return None

    return question


def build_strategy_context(patient_state: Dict[str, Any]) -> str:
    """
    Compact hint for the LLM writer about what dimension to target next.

    Prefers expected-information-gain selection over the belief state (picks the
    finding whose answer most reduces diagnostic uncertainty). Falls back to the
    older utility-score discriminator if EIG cannot be computed.
    """
    # Preferred path: information-gain over the posterior.
    try:
        from followup.information_gain import select_by_information_gain
        ig = select_by_information_gain(patient_state)
    except Exception:
        ig = None

    if isinstance(ig, dict) and ig.get("feature_term") and ig.get("top_two"):
        top_two = ig["top_two"]
        competitor = top_two[1] if len(top_two) > 1 else "alternate diagnosis"
        stop_hint = (
            " The differential is already concentrated — conclude if its key differentiators are answered."
            if ig.get("ready")
            else ""
        )
        return (
            f"Highest-information-gain question: probe the '{ig['dimension']}' dimension "
            f"(e.g. {ig['feature_term']}) — it best separates {top_two[0]} vs {competitor}.{stop_hint}"
        )

    # Fallback: previous utility-score discriminator.
    try:
        result = _deterministic_top2_and_feature(patient_state)
    except Exception:
        return ""

    if not isinstance(result, dict):
        return ""

    top_two = result.get("top_two") or []
    feature = result.get("feature") or {}
    term = str(feature.get("term", "")).strip()
    if not top_two:
        return ""

    if term:
        return (
            f"Target feature '{term}' to differentiate "
            f"{top_two[0]} vs {top_two[1] if len(top_two) > 1 else 'alternate diagnosis'}."
        )
    return f"Differentiate {top_two[0]} vs {top_two[1] if len(top_two) > 1 else 'alternate diagnosis'}."
