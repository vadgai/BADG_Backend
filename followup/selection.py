"""Question candidate selection chain (primary → fallbacks)."""

import logging
from typing import Any, Dict, List, Optional, Union

from followup.agents.critic import QuestionCritic
from followup.constants import (
    EARLY_STOP_CONFIDENCE,
    EARLY_STOP_MIN_QUESTIONS,
    MIN_FOLLOWUP_QUESTIONS,
)
from followup.fallbacks.contextual import build_contextual_fallback
from followup.fallbacks.min_depth import build_min_depth_question
from followup.fallbacks.turn_templates import build_turn_indexed_question

logger = logging.getLogger(__name__)


def can_stop_early(patient_state: Dict, question_count: int) -> bool:
    """Whether a 'ready for diagnosis' signal may be honored at this depth.

    - >= MIN_FOLLOWUP_QUESTIONS: always honored (as before).
    - EARLY_STOP_MIN_QUESTIONS..MIN-1: honored only when the tracked state
      INDEPENDENTLY corroborates the LLM's ready signal — confidence_score at
      or above EARLY_STOP_CONFIDENCE and the top differential marked High.
      Double-gating stops clear-cut cases early without letting a single
      overeager LLM turn end the session on thin evidence.
    - below EARLY_STOP_MIN_QUESTIONS: never.
    """
    if question_count >= MIN_FOLLOWUP_QUESTIONS:
        return True
    if question_count < EARLY_STOP_MIN_QUESTIONS:
        return False
    if not isinstance(patient_state, dict):
        return False
    try:
        confidence = float(patient_state.get("confidence_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    differential = patient_state.get("differential_diagnosis")
    top_is_high = bool(
        isinstance(differential, list)
        and differential
        and isinstance(differential[0], dict)
        and str(differential[0].get("confidence", "")).strip().lower() == "high"
    )
    allowed = confidence >= EARLY_STOP_CONFIDENCE and top_is_high
    if allowed:
        logger.info(
            "[EARLY-STOP] honoring ready at question %s (confidence=%.2f, top=High)",
            question_count, confidence,
        )
    return allowed


def should_stop_now(patient_state: Dict, question_count: int) -> bool:
    """Autonomous stop: the evidence is conclusive, regardless of whether the
    LLM volunteered a ready signal this turn.

    LLMs asked for "a question OR ready" are biased toward producing a question
    (observed in E2E: conf 0.90/top=High from Q5, yet 6 more confirmatory
    questions followed). This Python-side check ends the session when:
      - at least EARLY_STOP_MIN_QUESTIONS answered, and
      - tracked confidence >= EARLY_STOP_CONFIDENCE, and
      - top differential is High AND the runner-up is Low/absent — i.e. the
        gap is so wide no single answer would realistically flip the ranking.
    """
    if not isinstance(patient_state, dict) or question_count < EARLY_STOP_MIN_QUESTIONS:
        return False
    try:
        confidence = float(patient_state.get("confidence_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    differential = patient_state.get("differential_diagnosis")
    if not (isinstance(differential, list) and differential and isinstance(differential[0], dict)):
        return False
    top_is_high = str(differential[0].get("confidence", "")).strip().lower() == "high"
    second = differential[1] if len(differential) > 1 and isinstance(differential[1], dict) else None
    second_is_low = second is None or str(second.get("confidence", "")).strip().lower() == "low"
    stop = confidence >= EARLY_STOP_CONFIDENCE and top_is_high and second_is_low
    if stop:
        logger.info(
            "[EARLY-STOP] autonomous stop at question %s (confidence=%.2f, top=High, runner-up=Low)",
            question_count, confidence,
        )
    return stop


def select_question_candidate(
    primary_candidate: Any,
    patient_state: Dict,
    symptom_state: Dict,
    current_question_count: int,
) -> Union[Dict, str, None]:
    """
    4-tier selection:
      0) LLM primary
      1) contextual fallback
      2) min-depth symptom banks
      3) turn-indexed templates (no suffix hack unless exhausted)
    """
    asked_qs = symptom_state.get("questions_asked", []) if isinstance(symptom_state, dict) else []
    critic = QuestionCritic(symptom_state)
    counters = patient_state.setdefault("diagnostic_counters", {}) if isinstance(patient_state, dict) else {}

    # LLM-writer retry: re-ask the model for a DIFFERENT information-gain question
    # BEFORE using a low-value static template — keeps every question
    # differential-targeted. Fires when the primary is invalid (rejected by the
    # critic) OR when it is a generic static fallback (core-dimension severity,
    # deterministic pattern) that slipped through the orchestrator's own chain.
    def _is_low_value_primary(cand) -> bool:
        if not isinstance(cand, dict):
            return False
        src = str(cand.get("question_source", "")).strip().lower()
        fid = str(cand.get("feature_id", "")).strip().lower()
        return src in {"core_dimension", "deterministic"} or fid == "pain_severity"

    def _llm_retry(force: bool = False):
        if isinstance(primary_candidate, str):
            return None  # 'ready for diagnosis' etc. — not a rejected question
        if not force:
            primary_ok, _ = critic.validate_with_reason(primary_candidate, asked_qs)
            if primary_ok and isinstance(primary_candidate, dict):
                return None  # primary is fine and high-value; no retry needed
        try:
            from followup.orchestrator import regenerate_llm_question
            retry = regenerate_llm_question(patient_state, primary_candidate if isinstance(primary_candidate, dict) else None)
        except Exception as exc:
            logger.warning("[QSELECT] llm retry failed: %s", exc)
            return None
        if isinstance(retry, dict):
            counters["llm_retry_frequency"] = int(counters.get("llm_retry_frequency", 0) or 0) + 1
        return retry

    def _wrap_contextual():
        fb = build_contextual_fallback(patient_state, symptom_state)
        if isinstance(fb, dict):
            counters["deterministic_fallback_frequency"] = int(
                counters.get("deterministic_fallback_frequency", 0) or 0
            ) + 1
        return fb

    # When the primary is a generic static template, try the LLM retry FIRST and
    # keep the generic one only as a fallback if the retry also fails.
    primary_low_value = _is_low_value_primary(primary_candidate)
    retry_candidate = _llm_retry(force=primary_low_value)
    static_tail = [
        _wrap_contextual(),
        build_min_depth_question(patient_state, symptom_state, asked_qs),
        build_turn_indexed_question(
            patient_state, symptom_state, current_question_count, asked_qs, allow_suffix_fallback=False
        ),
    ]
    if primary_low_value and isinstance(retry_candidate, dict):
        candidate_chain = [retry_candidate, primary_candidate, *static_tail]
    else:
        candidate_chain = [primary_candidate, retry_candidate, *static_tail]

    for index, candidate in enumerate(candidate_chain):
        if isinstance(candidate, str):
            if "ready for diagnosis" in candidate.lower():
                if can_stop_early(patient_state, current_question_count):
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
