"""
Follow-up orchestrator — coordinates Analyzer, Strategist, Writer, and Critic agents.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Tuple, Union

from followup.agents.strategist import build_strategy_context, plan_next_question
from followup.agents.writer import build_followup_writer_prompt
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
    """Agent 1 — analyze patient answer and update structured state."""
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

    analysis = analyze_answer_for_state(question, answer, patient_state)
    if analysis:
        patient_state = update_patient_state(patient_state, question, answer, analysis)
    else:
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
      1) Strategist (rule-based disease discriminator)
      2) Writer (LLM) with strategist hint
      3) Contextual fallback
    """
    del max_retries
    if not isinstance(patient_state, dict):
        return None

    patient_state.setdefault("chat_history", [])
    turn_count = int(patient_state.get("turn_count", 0) or 0)
    if turn_count >= 12:
        return "Ready for diagnosis"

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
