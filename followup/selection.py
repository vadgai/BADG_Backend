"""Question candidate selection chain (primary → fallbacks)."""

import logging
from typing import Any, Dict, List, Optional, Union

from followup.agents.critic import QuestionCritic
from followup.constants import MIN_FOLLOWUP_QUESTIONS
from followup.fallbacks.contextual import build_contextual_fallback
from followup.fallbacks.min_depth import build_min_depth_question
from followup.fallbacks.turn_templates import build_turn_indexed_question

logger = logging.getLogger(__name__)


def select_question_candidate(
    primary_candidate: Any,
    patient_state: Dict,
    symptom_state: Dict,
    current_question_count: int,
) -> Union[Dict, str, None]:
    """
    4-tier selection:
      0) LLM / strategist primary
      1) contextual fallback
      2) min-depth symptom banks
      3) turn-indexed templates (no suffix hack unless exhausted)
    """
    asked_qs = symptom_state.get("questions_asked", []) if isinstance(symptom_state, dict) else []
    critic = QuestionCritic(symptom_state)
    counters = patient_state.setdefault("diagnostic_counters", {}) if isinstance(patient_state, dict) else {}

    def _wrap_contextual():
        fb = build_contextual_fallback(patient_state, symptom_state)
        if isinstance(fb, dict):
            counters["deterministic_fallback_frequency"] = int(
                counters.get("deterministic_fallback_frequency", 0) or 0
            ) + 1
        return fb

    candidate_chain = [
        primary_candidate,
        _wrap_contextual(),
        build_min_depth_question(patient_state, symptom_state, asked_qs),
        build_turn_indexed_question(
            patient_state, symptom_state, current_question_count, asked_qs, allow_suffix_fallback=False
        ),
    ]

    for index, candidate in enumerate(candidate_chain):
        if isinstance(candidate, str):
            if "ready for diagnosis" in candidate.lower():
                if current_question_count >= MIN_FOLLOWUP_QUESTIONS:
                    return "Ready for diagnosis"
                continue

        ok, reason = critic.validate_with_reason(candidate, asked_qs)
        if ok and isinstance(candidate, dict):
            candidate.setdefault("D", "None of these")
            candidate.setdefault("E", "None of these / Not sure")
            candidate.setdefault("allow_other", True)
            if index > 0:
                logger.info(
                    "[QSELECT] primary rejected; fallback index=%s source=%s",
                    index,
                    candidate.get("question_source"),
                )
            return candidate

        if index == 0 and isinstance(candidate, dict):
            logger.info(
                "[QSELECT] primary rejected reason=%s q=%r",
                reason,
                str(candidate.get("Question", ""))[:80],
            )
            if reason == "repeated":
                counters["repeated_question_prevention_hits"] = int(
                    counters.get("repeated_question_prevention_hits", 0) or 0
                ) + 1
            if reason in {"generic", "placeholder"}:
                counters["generic_question_rejection_hits"] = int(
                    counters.get("generic_question_rejection_hits", 0) or 0
                ) + 1

    forced = build_turn_indexed_question(
        patient_state,
        symptom_state,
        current_question_count,
        asked_qs,
        allow_suffix_fallback=True,
    )
    if isinstance(forced, dict) and forced.get("Question"):
        forced.setdefault("D", "None of these")
        forced.setdefault("E", "None of these / Not sure")
        forced.setdefault("allow_other", True)
        return forced

    return None
