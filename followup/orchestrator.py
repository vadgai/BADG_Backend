"""
Follow-up orchestrator — coordinates Analyzer, Strategist, Writer, and Critic agents.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Tuple, Union

from followup.constants import MAX_FOLLOWUP_QUESTIONS, MIN_FOLLOWUP_QUESTIONS
from followup.agents.strategist import build_strategy_context, plan_next_question
from followup.agents.writer import build_followup_writer_prompt
from followup.agents.critic import QuestionCritic
from followup.validators.mcq_quality import validate_mcq_quality
from followup.validators.mcq_structure import normalize_mcq_keys, validate_mcq_structure
from diagnosis_methods.patient_state import update_patient_state
from symptom_extractor_v5 import apply_signals_to_state, extract_signals
from utils.gemini_api_manager import extract_json_from_text, generate_content_with_fallback

logger = logging.getLogger(__name__)


def update_state_with_answer(
    patient_state: Dict[str, Any],
    question: str,
    answer: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Agent 1 — analyze patient answer and update structured state.

    Also pre-generates the next MCQ question (combined Gemini call) and stashes
    it in patient_state["_pending_next_question"] for consumption by
    get_next_followup_question().
    """
    if not isinstance(patient_state, dict):
        return patient_state, {"signals": None, "analysis": None}

    signals = extract_signals(
        current_state=patient_state,
        patient_response=answer,
        last_question_text=question,
        use_llm=False,
    )
    apply_signals_to_state(patient_state, signals)

    from diagnosis_methods.state_followup import analyze_answer_for_state

    # Build strategy hint (rule-based, zero tokens cost)
    strategy_hint = build_strategy_context(patient_state)

    analysis = analyze_answer_for_state(question, answer, patient_state, strategy_hint=strategy_hint)
    if analysis:
        # ── Stash the pre-generated next question before updating state ──
        # Pop it so it is never written to persistent storage fields.
        pending_q = analysis.pop("next_question", None)
        if isinstance(pending_q, dict) and pending_q.get("Question"):
            patient_state["_pending_next_question"] = pending_q
            logger.debug(
                "orchestrator: stashed _pending_next_question q=%r",
                str(pending_q.get("Question", ""))[:80],
            )

        patient_state = update_patient_state(patient_state, question, answer, analysis)
    else:
        # Combined LLM call failed (e.g. model returned unparseable JSON). Recover the
        # turn's clinical content with the dedicated LLM extractor so this answer's
        # positives/negatives still reach the rule engine at report time instead of
        # being silently dropped. Falls back to heuristics if the model is unavailable.
        try:
            recovery = extract_signals(
                current_state=patient_state,
                patient_response=answer,
                last_question_text=question,
                use_llm=True,
            )
            apply_signals_to_state(patient_state, recovery)
        except Exception as exc:
            logger.warning("orchestrator: recovery extract_signals failed: %s", exc)
        patient_state["turn_count"] = patient_state.get("turn_count", 0) + 1
        patient_state["last_updated"] = datetime.utcnow().isoformat()
        history = patient_state.setdefault("chat_history", [])
        if question or answer:
            history.append({"bot": question, "user": answer})

    return patient_state, {"signals": signals, "analysis": analysis}


def get_next_followup_question(
    patient_state: Dict[str, Any],
    max_retries: int = 1,
) -> Union[Dict[str, str], str, None]:
    """
    Generate the next follow-up MCQ:
      0) Fast-path: consume _pending_next_question from the combined call
         (validates through QuestionCritic — Jaccard + feature + option-overlap)
      1) Strategist (rule-based disease discriminator)
      2) Writer (LLM) with strategist hint
      3) Contextual fallback
    """
    del max_retries
    if not isinstance(patient_state, dict):
        return None

    patient_state.setdefault("chat_history", [])
    turn_count = int(patient_state.get("turn_count", 0) or 0)
    if turn_count >= MAX_FOLLOWUP_QUESTIONS:
        return "Ready for diagnosis"

    # ── Fast-path: use pre-generated question from combined call ─────────────
    pending = patient_state.pop("_pending_next_question", None)
    if isinstance(pending, dict) and pending.get("Question"):
        # Check early-stop flag first (shouldn't appear here but guard anyway)
        if bool(pending.get("ready_for_diagnosis")):
            if turn_count >= MIN_FOLLOWUP_QUESTIONS:
                return "Ready for diagnosis"
        else:
            # Validate through the full critic chain before trusting the LLM
            normalized = normalize_mcq_keys(pending)
            if validate_mcq_structure(normalized):
                normalized.setdefault("E", "Not sure / None of these")
                ok_quality, quality_reason = validate_mcq_quality(normalized, patient_state)
                symptom_state = (
                    patient_state.get("symptom_state")
                    if isinstance(patient_state.get("symptom_state"), dict)
                    else {}
                )
                asked_qs = symptom_state.get("questions_asked", [])
                critic = QuestionCritic(symptom_state)
                ok_critic, critic_reason = critic.validate_with_reason(normalized, asked_qs)
                if ok_quality and ok_critic:
                    logger.debug(
                        "orchestrator: fast-path question accepted q=%r",
                        str(normalized.get("Question", ""))[:80],
                    )
                    return _finalize_mcq(normalized, "combined_llm")
                else:
                    reason = critic_reason if not ok_critic else quality_reason
                    logger.info(
                        "orchestrator: fast-path question rejected reason=%s q=%r — falling back",
                        reason,
                        str(normalized.get("Question", ""))[:80],
                    )
                    # Increment repetition counter if that was the reason
                    if reason in {"repeated", "feature_repeated", "options_repeated"}:
                        counters = patient_state.setdefault("diagnostic_counters", {})
                        counters["repeated_question_prevention_hits"] = (
                            int(counters.get("repeated_question_prevention_hits", 0) or 0) + 1
                        )
            # Fall through to standard generation chain below

    # ── Standard chain: Strategist → LLM Writer → Contextual Fallback ───────
    rule_mcq = plan_next_question(patient_state)
    if isinstance(rule_mcq, str) and "ready for diagnosis" in rule_mcq.lower():
        return "Ready for diagnosis"
    if isinstance(rule_mcq, dict) and rule_mcq.get("Question"):
        return _finalize_mcq(rule_mcq, "strategist_rule")

    llm_mcq = _generate_llm_question(patient_state)
    if isinstance(llm_mcq, str) and "ready for diagnosis" in llm_mcq.lower():
        return "Ready for diagnosis"
    if isinstance(llm_mcq, dict) and llm_mcq.get("Question"):
        return _finalize_mcq(llm_mcq, "llm")

    from followup.fallbacks.contextual import build_contextual_fallback

    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
    fallback = build_contextual_fallback(patient_state, symptom_state)
    if isinstance(fallback, str) and "ready for diagnosis" in fallback.lower():
        return "Ready for diagnosis"
    if isinstance(fallback, dict) and fallback.get("Question"):
        return _finalize_mcq(fallback, "deterministic")

    return fallback


def _finalize_mcq(mcq: Dict, source: str) -> Dict:
    mcq.setdefault("D", "None of these")
    mcq.setdefault("E", "None of these / Not sure")
    mcq.setdefault("allow_other", True)
    mcq.setdefault("priority", "high")
    mcq.setdefault("clinical_intent", "Differentiate top competing diagnoses using structured evidence")
    mcq.setdefault("differentiates_between", ["Top suspect #1", "Top suspect #2"])
    mcq.setdefault("question_source", source)
    return mcq


def _generate_llm_question(patient_state: Dict) -> Union[Dict, str, None]:
    from utils.gemini_api_manager import get_gemini_model

    model_available, _model = get_gemini_model()
    if not model_available:
        return None

    strategy_hint = build_strategy_context(patient_state)
    prompt = build_followup_writer_prompt(patient_state, strategy_hint)

    success, raw_text, error = generate_content_with_fallback(
        prompt=prompt,
        max_retries=None,
        temperature=0.2,
        max_output_tokens=500,
    )
    if not success or not raw_text:
        logger.warning("writer: LLM generation failed: %s", error)
        return None

    parsed = extract_json_from_text(raw_text.strip())
    if isinstance(parsed, dict) and bool(parsed.get("ready_for_diagnosis")):
        return "Ready for diagnosis"

    if not isinstance(parsed, dict):
        return None

    normalized = normalize_mcq_keys(parsed)
    if not validate_mcq_structure(normalized):
        return None

    normalized.setdefault("E", "None of these / Not sure")
    ok, reason = validate_mcq_quality(normalized, patient_state)
    if not ok:
        logger.warning("writer: LLM MCQ rejected (%s)", reason)
        return None

    normalized.setdefault("question_source", "llm")
    return normalized
