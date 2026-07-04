"""
State-Based Followup Generation for Method 2 - Pure LLM Sequential Diagnostic Reasoning

This module implements "Sequential Differential Diagnosis" using pure LLM reasoning:
- Step A: Evidence Analysis
- Step B: Differential Mapping (3-5 conditions)
- Step C: Gap Identification
- Step D: Next-Best-Question (NBQ)
"""

import json
import logging
import os
import re
from typing import Any, Optional, Union, Dict, List
from dotenv import load_dotenv
load_dotenv()

from utils.gemini_api_manager import generate_content_with_fallback, extract_json_from_text
from diagnosis_methods.patient_state import state_to_prompt_string
from diagnosis_rule_engine import analyze_case, load_diseases_from_folder, build_disease_profiles, DISEASE_PROFILES

logger = logging.getLogger(__name__)
_DIAG_V6_QUESTION_PLANNER = str(os.getenv("DIAG_V6_QUESTION_PLANNER", "true")).strip().lower() in {"1", "true", "yes", "on"}
_PROFILES_READY = False

_PLACEHOLDER_MARKERS = {
    "clinically precise question",
    "specific clinical",
    "specific clinical question",
    "specific finding",
    "specific option",
    "disease 1",
    "disease 2",
    "option a",
    "option b",
    "option c",
}

_GENERIC_QUESTION_MARKERS = {
    "getting worse",
    "can you share more details",
    "any other symptoms",
    "new or worsening symptoms",
    "symptom progression",
    # NOTE: genuine clinical topics (e.g. "breathing difficulty") are intentionally
    # excluded — a targeted red-flag respiratory question is legitimate, not generic.
    "clinically precise differentiator question",
    "clinically precise question",
    "specific clinical",
    "specific finding",
}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _token_set(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", _normalize_text(text)) if t}


def _jaccard(a: str, b: str) -> float:
    sa = _token_set(a)
    sb = _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


def _extract_asked_questions(patient_state: Dict) -> List[str]:
    """Extract all previously asked questions from both symptom_state and raw chat_history."""
    seen: set = set()
    cleaned: List[str] = []

    # Primary source: symptom_state.questions_asked
    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
    for q in (symptom_state.get("questions_asked") or []):
        q_text = str(q).strip()
        norm = _normalize_text(q_text)
        if q_text and norm not in seen:
            seen.add(norm)
            cleaned.append(q_text)

    # Secondary source: raw chat_history [{"bot": ..., "user": ...}, ...]
    for msg in (patient_state.get("chat_history") or []):
        if not isinstance(msg, dict):
            continue
        q_text = str(msg.get("bot") or "").strip()
        norm = _normalize_text(q_text)
        if q_text and norm not in seen:
            seen.add(norm)
            cleaned.append(q_text)

    return cleaned


def _format_chat_history(patient_state: Dict) -> str:
    """Format full Q&A pairs from chat_history for LLM context."""
    history: List[Dict] = patient_state.get("chat_history") or []
    if not history:
        return "No previous questions asked."

    lines: List[str] = []
    turn = 0
    i = 0
    while i < len(history):
        msg = history[i]
        if not isinstance(msg, dict):
            i += 1
            continue
        bot_q = str(msg.get("bot") or "").strip()
        user_a = str(msg.get("user") or "").strip()
        if bot_q:
            turn += 1
            lines.append(f"Q{turn}: {bot_q}")
            if user_a:
                lines.append(f"A{turn}: {user_a}")
            elif i + 1 < len(history) and isinstance(history[i + 1], dict):
                next_user = str(history[i + 1].get("user") or "").strip()
                if next_user:
                    lines.append(f"A{turn}: {next_user}")
                    i += 1
        elif user_a and lines:
            lines.append(f"(Answer): {user_a}")
        i += 1

    return "\n".join(lines) if lines else "No previous questions asked."


def _contains_placeholder_text(text: str) -> bool:
    t = _normalize_text(text)
    if not t:
        return True
    return any(marker in t for marker in _PLACEHOLDER_MARKERS)


def _is_generic_question(text: str) -> bool:
    t = _normalize_text(text)
    if not t:
        return True
    return any(marker in t for marker in _GENERIC_QUESTION_MARKERS)


def _is_repeated_question(question: str, asked_questions: List[str]) -> bool:
    from followup.validators.repetition import is_repeated_question

    return is_repeated_question(question, asked_questions)


def _extract_top_two_condition_names(patient_state: Dict) -> List[str]:
    differential = patient_state.get("differential_diagnosis")
    names: List[str] = []
    if isinstance(differential, list):
        for item in differential:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    names.append(name)
            if len(names) >= 2:
                break
    return names


def _ensure_profiles_loaded() -> None:
    global _PROFILES_READY
    if _PROFILES_READY and DISEASE_PROFILES:
        return
    load_diseases_from_folder()
    build_disease_profiles()
    _PROFILES_READY = True


def _extract_profile_by_name(condition_name: str) -> Optional[Dict]:
    target = _normalize_text(condition_name)
    if not target:
        return None
    for profile in DISEASE_PROFILES:
        name = _normalize_text(profile.get("name", ""))
        if not name:
            continue
        if name == target or name in target or target in name:
            return profile
    return None


def _known_findings_set(patient_state: Dict) -> set:
    positives = patient_state.get("identified_symptoms") if isinstance(patient_state.get("identified_symptoms"), list) else []
    negatives = patient_state.get("negatives") if isinstance(patient_state.get("negatives"), list) else []
    known = set()
    for item in positives + negatives:
        term = _normalize_text(item)
        if term:
            known.add(term)
    return known


def _feature_terms(profile: Dict, bucket: str) -> List[Dict[str, Union[str, float]]]:
    terms: List[Dict[str, Union[str, float]]] = []
    features = profile.get("features", {}).get(bucket, []) if isinstance(profile.get("features"), dict) else []
    if isinstance(features, list) and features:
        for feature in features:
            if isinstance(feature, dict):
                term = _normalize_text(feature.get("term"))
                if not term:
                    continue
                try:
                    weight = float(feature.get("weight", 1.0))
                except (TypeError, ValueError):
                    weight = 1.0
                terms.append({"term": term, "weight": max(0.1, weight)})
        if terms:
            return terms

    # Backward compatibility if features are missing.
    if bucket == "key":
        terms_raw = profile.get("symptoms", {}).get("required", []) if isinstance(profile.get("symptoms"), dict) else []
        terms.extend({"term": _normalize_text(item), "weight": 1.0} for item in terms_raw if _normalize_text(item))
    elif bucket == "supportive":
        terms_raw = profile.get("symptoms", {}).get("common", []) if isinstance(profile.get("symptoms"), dict) else []
        terms.extend({"term": _normalize_text(item), "weight": 0.6} for item in terms_raw if _normalize_text(item))
    elif bucket == "rare":
        terms_raw = profile.get("symptoms", {}).get("rare", []) if isinstance(profile.get("symptoms"), dict) else []
        terms.extend({"term": _normalize_text(item), "weight": 0.35} for item in terms_raw if _normalize_text(item))
    return terms


def _semantic_topic_from_feature(feature: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", feature.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _plainify(term: str) -> str:
    """Map a clinical feature term to plain patient-facing wording (shared map)."""
    try:
        from symptom_card import _plain_label
        return _plain_label(term)
    except Exception:
        return str(term or "").strip().lower()


def _build_deterministic_question_from_feature(
    feature_term: str,
    opposite_term: str,
    top_two: List[str],
    priority: str,
) -> Dict[str, str]:
    disease_1 = top_two[0] if len(top_two) > 0 else "Top diagnosis"
    disease_2 = top_two[1] if len(top_two) > 1 else "Alternate diagnosis"
    feature_label = _plainify(feature_term)
    opposite_label = _plainify(opposite_term) if opposite_term else "a different competing pattern"
    return {
        "Question": f"Do you have {feature_label}?",
        "A": f"Yes, I have {feature_label}",
        "B": f"No, it's more like {opposite_label}",
        "C": "Neither of these fits",
        "D": f"Not sure about {feature_label}",
        "E": "None of these / Not sure",
        "allow_other": True,
        "priority": priority,
        "clinical_intent": f"Differentiate {disease_1} vs {disease_2} using feature-level evidence",
        "differentiates_between": [disease_1, disease_2],
        "feature_id": feature_label,
        "question_source": "deterministic",
    }


def _deterministic_top2_and_feature(patient_state: Dict) -> Optional[Dict[str, Any]]:
    _ensure_profiles_loaded()
    demographics = patient_state.get("demographics") if isinstance(patient_state.get("demographics"), dict) else {}
    age = demographics.get("age")
    gender = demographics.get("gender")
    positives = patient_state.get("identified_symptoms") if isinstance(patient_state.get("identified_symptoms"), list) else []
    negatives = patient_state.get("negatives") if isinstance(patient_state.get("negatives"), list) else []
    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
    red_flags = symptom_state.get("red_flags") if isinstance(symptom_state.get("red_flags"), list) else patient_state.get("red_flags", [])
    modifier_map = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else symptom_state.get("modifiers")

    if not positives:
        return None

    ranking = analyze_case(
        age=age,
        gender=gender,
        symptoms=positives,
        chat_history="Structured state only",
        negatives=negatives,
        modifiers=modifier_map,
        red_flags=red_flags if isinstance(red_flags, list) else [],
    )
    conditions = ranking.get("conditions") if isinstance(ranking, dict) else []
    if not isinstance(conditions, list) or len(conditions) < 1:
        return None
    top_condition = conditions[0] if isinstance(conditions[0], dict) else None
    second_condition = conditions[1] if len(conditions) > 1 and isinstance(conditions[1], dict) else None
    if not top_condition:
        return None
    top_name = str(top_condition.get("name", "")).strip()
    second_name = str(second_condition.get("name", "")).strip() if second_condition else ""
    top_two = [name for name in [top_name, second_name] if name]
    if len(top_two) < 2:
        # Fall back to current state differential names when rule engine returns one candidate.
        top_two = _extract_top_two_condition_names(patient_state) or top_two
    if len(top_two) < 2:
        return None

    profile_1 = _extract_profile_by_name(top_two[0])
    profile_2 = _extract_profile_by_name(top_two[1])
    if not profile_1 or not profile_2:
        return None

    from followup.constants import JACCARD_REPEAT_THRESHOLD

    asked_questions = _extract_asked_questions(patient_state)
    known = _known_findings_set(patient_state)
    red_flag_terms = set(_normalize_text(item) for item in (red_flags if isinstance(red_flags, list) else []) if _normalize_text(item))

    top1_terms = _feature_terms(profile_1, "key") + _feature_terms(profile_1, "supportive") + _feature_terms(profile_1, "rare")
    top2_terms = _feature_terms(profile_2, "key") + _feature_terms(profile_2, "supportive") + _feature_terms(profile_2, "rare")
    top2_term_set = {str(item.get("term")) for item in top2_terms if str(item.get("term"))}
    top1_term_set = {str(item.get("term")) for item in top1_terms if str(item.get("term"))}

    candidates: List[Dict[str, Any]] = []
    for feature in top1_terms:
        term = str(feature.get("term", "")).strip()
        if not term or term in known:
            continue
        if term in top2_term_set:
            continue
        if any(_jaccard(term, asked) >= JACCARD_REPEAT_THRESHOLD for asked in asked_questions):
            continue
        opposite = next((str(item.get("term")) for item in top2_terms if str(item.get("term")) not in known), "")
        weight = float(feature.get("weight", 1.0) or 1.0)
        red_priority = any(flag in term or term in flag for flag in red_flag_terms) if red_flag_terms else False
        separation = 1.0
        if opposite:
            separation = max(0.1, 1.0 - _jaccard(term, opposite))
        novelty = 1.0 if term not in known else 0.0
        utility = (1.45 * weight) + (1.15 * separation) + (0.7 * novelty) + (1.0 if red_priority else 0.0)
        candidates.append(
            {
                "term": term,
                "opposite": opposite,
                "utility": utility,
                "priority": "red-flag" if red_priority else "high",
            }
        )

    for feature in top2_terms:
        term = str(feature.get("term", "")).strip()
        if not term or term in known:
            continue
        if term in top1_term_set:
            continue
        if any(_jaccard(term, asked) >= JACCARD_REPEAT_THRESHOLD for asked in asked_questions):
            continue
        opposite = next((str(item.get("term")) for item in top1_terms if str(item.get("term")) not in known), "")
        weight = float(feature.get("weight", 1.0) or 1.0)
        red_priority = any(flag in term or term in flag for flag in red_flag_terms) if red_flag_terms else False
        separation = 1.0
        if opposite:
            separation = max(0.1, 1.0 - _jaccard(term, opposite))
        novelty = 1.0 if term not in known else 0.0
        utility = (1.35 * weight) + (1.1 * separation) + (0.7 * novelty) + (1.0 if red_priority else 0.0)
        candidates.append(
            {
                "term": term,
                "opposite": opposite,
                "utility": utility,
                "priority": "red-flag" if red_priority else "high",
            }
        )

    if not candidates:
        return {
            "top_two": top_two,
            "ranking": ranking,
            "feature": None,
            "question": None,
        }

    candidates.sort(key=lambda item: float(item.get("utility", 0.0)), reverse=True)
    selected = candidates[0]
    question = _build_deterministic_question_from_feature(
        feature_term=str(selected.get("term", "")),
        opposite_term=str(selected.get("opposite", "")),
        top_two=top_two,
        priority=str(selected.get("priority", "high")),
    )
    return {
        "top_two": top_two,
        "ranking": ranking,
        "feature": selected,
        "question": question,
    }


def _build_chief_symptom_mcq(patient_state: Dict) -> Dict[str, str]:
    symptoms = patient_state.get("identified_symptoms") if isinstance(patient_state.get("identified_symptoms"), list) else []
    chief = ""
    for item in symptoms:
        term = _normalize_text(item)
        if term:
            chief = term
            break
    if not chief:
        chief = _normalize_text(patient_state.get("chief_complaint", "")) or "main symptom"

    lower = chief.lower()
    if any(token in lower for token in {"abdominal", "stomach", "vomit", "diarrhea", "bowel"}):
        return {
            "Question": "Which best describes your stomach symptoms?",
            "A": "Pain in lower-right belly, worse with movement",
            "B": "Pain all over belly, with loose motions or vomiting",
            "C": "Burning pain in upper belly after eating",
            "D": "Bloating or gas, mostly after eating",
            "E": "None of these / Not sure",
            "allow_other": True,
            "priority": "high",
            "clinical_intent": "Differentiate inflammatory surgical, infectious, and acid-peptic abdominal patterns",
            "differentiates_between": ["Top suspect #1", "Top suspect #2"],
            "feature_id": "digestive_pattern",
            "question_source": "deterministic",
        }

    if any(token in lower for token in {"cough", "breath", "chest", "wheeze", "phlegm"}):
        return {
            "Question": "Which breathing symptom is most noticeable right now?",
            "A": "Short of breath or wheezing, chest feels tight",
            "B": "Cough with colored phlegm and fever",
            "C": "Dry cough with a scratchy throat, little phlegm",
            "D": "Chest pain that's worse with deep breaths",
            "E": "None of these / Not sure",
            "allow_other": True,
            "priority": "high",
            "clinical_intent": "Differentiate airway-reactive, bacterial, and viral respiratory patterns",
            "differentiates_between": ["Top suspect #1", "Top suspect #2"],
            "feature_id": "respiratory_pattern",
            "question_source": "deterministic",
        }

    if any(token in lower for token in {"headache", "dizziness", "weakness", "numb", "balance"}):
        return {
            "Question": "Which best describes what you're experiencing?",
            "A": "Weakness or numbness on one side, or trouble speaking",
            "B": "Bad throbbing headache with sensitivity to light",
            "C": "Spinning dizziness, no weakness",
            "D": "Memory or focus getting worse over time",
            "E": "None of these / Not sure",
            "allow_other": True,
            "priority": "high",
            "clinical_intent": "Differentiate focal neurological, migraine, and vestibular patterns",
            "differentiates_between": ["Top suspect #1", "Top suspect #2"],
            "feature_id": "neurological_pattern",
            "question_source": "deterministic",
        }

    return {
        "Question": f"Which best matches your {chief}?",
        "A": f"{chief} stays in one spot, doesn't go away",
        "B": f"{chief} plus fever or feeling tired/run down",
        "C": f"{chief} comes and goes, seems triggered by something",
        "D": f"{chief} started suddenly and is severe",
        "E": "None of these / Not sure",
        "allow_other": True,
        "priority": "high",
        "clinical_intent": f"Differentiate competing causes of {chief} using symptom pattern context",
        "differentiates_between": ["Top suspect #1", "Top suspect #2"],
        "feature_id": chief,
        "question_source": "deterministic",
    }


def _build_core_dimension_mcq(patient_state: Dict, asked_questions: List[str]) -> Dict[str, str]:
    """Single-dimension question on a mandatory high-yield axis (duration, then severity)."""
    symptom_state = patient_state.get("symptom_state") if isinstance(patient_state.get("symptom_state"), dict) else {}
    asked_dims = {str(f).strip().lower() for f in (symptom_state.get("feature_ids_asked") or [])}
    if "duration" not in asked_dims:
        return {
            "Question": "How long have you had these symptoms?",
            "A": "Less than 48 hours", "B": "3-7 days", "C": "2-4 weeks",
            "D": "More than a month", "E": "Not sure / None of these",
            "allow_other": True, "priority": "high",
            "clinical_intent": "Establish acuity (acute vs chronic)",
            "differentiates_between": ["Acute condition", "Chronic condition"],
            "feature_id": "duration", "question_source": "core_dimension",
        }
    return {
        "Question": "How severe are your symptoms right now?",
        "A": "Mild - barely affects me", "B": "Moderate - limits some activity",
        "C": "Severe - hard to function", "D": "Comes and goes",
        "E": "Not sure / None of these",
        "allow_other": True, "priority": "high",
        "clinical_intent": "Establish symptom severity",
        "differentiates_between": ["Mild disease", "Severe disease"],
        "feature_id": "pain_severity", "question_source": "core_dimension",
    }


def _build_eig_fallback_mcq(patient_state: Dict) -> Union[Dict, str, None]:
    """Single-dimension MCQ built from the highest-information-gain finding (no LLM)."""
    try:
        from followup.information_gain import select_by_information_gain
        ig = select_by_information_gain(patient_state)
    except Exception:
        return None
    if not isinstance(ig, dict):
        return None
    if ig.get("ready"):
        from followup.constants import MIN_FOLLOWUP_QUESTIONS
        if int(patient_state.get("turn_count", 0) or 0) >= MIN_FOLLOWUP_QUESTIONS:
            return "Ready for diagnosis"
        # High confidence but below the question floor — keep asking.
    feature = str(ig.get("feature_term") or "").strip()
    dimension = str(ig.get("dimension") or "").strip()
    if not feature or not dimension:
        return None
    top_two = ig.get("top_two") or []
    d1 = top_two[0] if top_two else "the leading diagnosis"
    d2 = top_two[1] if len(top_two) > 1 else "an alternative"
    feature = _plainify(feature) or feature
    return {
        "Question": f"Do you have {feature}?",
        "A": f"Yes, {feature}",
        "B": "No, I don't have that",
        "C": "Only mild or occasional",
        "D": "I haven't noticed",
        "E": "Not sure / None of these",
        "allow_other": True,
        "priority": "high",
        "clinical_intent": f"Differentiate {d1} vs {d2} (highest information gain)",
        "differentiates_between": [d1, d2],
        "feature_id": dimension,
        "question_source": "eig_fallback",
    }


def build_contextual_fallback_mcq(patient_state: Dict) -> Union[Dict, str]:
    """
    Build a single-dimension MCQ fallback when the LLM path is unavailable/rejected.

    Preference order (every option is single-dimension — never a grab-bag):
      1) highest-information-gain finding over the belief state,
      2) a mandatory core dimension (duration → severity) if not yet asked,
      3) a chief-symptom pattern template (single body system).
    """
    turn_count = int(patient_state.get("turn_count", 0) or 0)
    asked_questions = _extract_asked_questions(patient_state)

    from followup.constants import MAX_FOLLOWUP_QUESTIONS
    if turn_count >= MAX_FOLLOWUP_QUESTIONS:
        return "Ready for diagnosis"

    # 1) Information-gain driven single-dimension question.
    eig_q = _build_eig_fallback_mcq(patient_state)
    if isinstance(eig_q, str) and "ready" in eig_q.lower():
        return "Ready for diagnosis"
    if isinstance(eig_q, dict) and not _is_repeated_question(eig_q.get("Question", ""), asked_questions):
        return eig_q

    # 2) Mandatory core dimension (duration/severity) if still uncovered.
    core_q = _build_core_dimension_mcq(patient_state, asked_questions)
    if not _is_repeated_question(core_q.get("Question", ""), asked_questions):
        return core_q

    # 3) Chief-symptom pattern template (single body system).
    fallback = _build_chief_symptom_mcq(patient_state)
    return fallback


def _validate_mcq_quality(mcq: Dict, patient_state: Dict) -> (bool, str):
    from followup.validators.mcq_quality import validate_mcq_quality

    return validate_mcq_quality(mcq, patient_state)


def get_followup_from_state(
    patient_state: Dict,
    top_diseases: Optional[List[Dict]] = None,
    disease_engine=None,
    entropy_tracker=None,
    max_retries: int = 1,
) -> Union[Dict, str, None]:
    """Backward-compatible entry — delegates to followup.orchestrator."""
    del top_diseases, disease_engine, entropy_tracker
    from followup.orchestrator import get_next_followup_question

    return get_next_followup_question(patient_state, max_retries=max_retries)


def analyze_answer_for_state(
    question: str,
    answer: str,
    current_state: Dict,
    strategy_hint: str = "",
) -> Optional[Dict]:
    """
    Analyze a patient's answer AND generate the next MCQ question in a single
    Gemini API call (token-efficient combined call).

    Args:
        question: The question that was asked
        answer: The patient's answer
        current_state: Current patient state
        strategy_hint: Optional hint from the Strategist agent (rule-based)

    Returns:
        Dictionary with:
          - Clinical state update fields (identified_symptoms, negatives,
            differential_diagnosis, differentiator_symptom, running_summary,
            confidence_score)
          - next_question: the next MCQ {Question, A, B, C, D, E, feature_id}
        OR {"ready_for_diagnosis": true} when sufficient evidence is gathered.
        Returns None if the Gemini call fails entirely.

    Repetition prevention (three layers):
      Layer 1 — LLM: the prompt lists only the REMAINING unused clinical
                      dimensions (feature_ids) and requires feature_id to be one
                      of them — so a repeat is structurally excluded. This replaces
                      re-sending the full text of every prior question each turn
                      (a large per-turn token cost), and prevents paraphrase
                      repeats that surface-text matching missed.
      Layer 2 — Python: orchestrator validates next_question through
                        QuestionCritic (Jaccard over symptom_state.questions_asked
                        + feature_id dedup + option-overlap) before accepting it.
                        This enforcement reads from state, not the prompt, so
                        trimming the prompt does not weaken it.
      Layer 3 — Fallback: if Layer 2 rejects the question, orchestrator falls
                          through to the existing strategist → writer chain.
    """
    from utils.gemini_api_manager import get_gemini_model
    model_available, model = get_gemini_model()

    if not model_available or model is None:
        return None

    # ── Patient demographics & structured state ─────────────────────────────
    age = current_state.get("demographics", {}).get("age", "Unknown")
    gender = current_state.get("demographics", {}).get("gender", "Unknown")
    bmi_data = current_state.get("demographics", {}).get("bmi", {})
    bmi_text = ""
    if bmi_data:
        bmi_text = f" | BMI: {bmi_data.get('value')} ({bmi_data.get('category')})"

    symptom_state = (
        current_state.get("symptom_state")
        if isinstance(current_state.get("symptom_state"), dict)
        else {}
    )
    modifier_map = (
        symptom_state.get("modifier_map")
        if isinstance(symptom_state.get("modifier_map"), dict)
        else {}
    )
    red_flags = (
        symptom_state.get("red_flags")
        if isinstance(symptom_state.get("red_flags"), list)
        else current_state.get("red_flags", [])
    )

    positives = (
        symptom_state.get("current_symptoms")
        if isinstance(symptom_state.get("current_symptoms"), list)
        else current_state.get("identified_symptoms", [])
    )
    negatives = (
        current_state.get("negatives")
        if isinstance(current_state.get("negatives"), list)
        else []
    )

    positives_text = ", ".join(str(s).strip() for s in positives if str(s).strip()) or "None"
    negatives_text = ", ".join(str(s).strip() for s in negatives if str(s).strip()) or "None"
    red_flags_text = ", ".join(str(s).strip() for s in red_flags if str(s).strip()) or "None"

    chief_complaint = str(current_state.get("chief_complaint", "")).strip() or positives_text
    turn_count = int(current_state.get("turn_count", 0) or 0)
    running_summary = str(current_state.get("running_summary", "")).strip()
    differentiator = str(current_state.get("differentiator_symptom", "")).strip()

    # ── Differential diagnosis ──────────────────────────────────────────────
    differential = (
        current_state.get("differential_diagnosis")
        if isinstance(current_state.get("differential_diagnosis"), list)
        else []
    )
    diff_text = "Not yet established — base on symptoms and demographics."
    if differential:
        diff_lines = []
        for idx, item in enumerate(differential[:3], 1):
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                confidence = str(item.get("confidence", "")).strip()
                reasoning = str(item.get("reasoning", "")).strip()
                if name:
                    diff_lines.append(f"  #{idx}: {name} ({confidence}) — {reasoning[:100]}")
        if diff_lines:
            diff_text = "\n".join(diff_lines)

    # ── Covered vs remaining clinical dimensions (compact repetition control) ──
    # We send short dimension tags instead of the full text of every prior question.
    # The Python critic still enforces no-repeat from symptom_state (Jaccard on
    # questions_asked + feature_id dedup), so this only trims prompt tokens.
    from followup.constants import (
        FOLLOWUP_DIMENSIONS,
        MAX_FOLLOWUP_QUESTIONS,
        MIN_FOLLOWUP_QUESTIONS,
    )

    feature_ids = symptom_state.get("feature_ids_asked") or []
    covered = {str(f).strip().lower() for f in feature_ids if str(f).strip()}
    covered_text = ", ".join(sorted(covered)) or "none"
    remaining = [d for d in FOLLOWUP_DIMENSIONS if d not in covered]
    remaining_text = ", ".join(remaining) or "any unasked clinical dimension"

    # ── EIG shortlist + posterior anchor (pure computation, zero LLM tokens) ──
    # Offering the model every unasked dimension invites generic screening
    # questions; instead offer only the few highest-information-gain dimensions.
    # The posterior anchor keeps PART 1's differential consistent with the
    # Bayesian belief state so it cannot drift to diseases whose key symptoms
    # the patient already denied (e.g. GERD after "No" to all reflux questions).
    anchor_line = ""
    try:
        from followup.information_gain import rank_candidate_findings
        eig_ranked = rank_candidate_findings(current_state, top_k=6, limit=5)
    except Exception:
        eig_ranked = None
    if isinstance(eig_ranked, dict):
        eig_findings = eig_ranked.get("findings") or []
        if eig_findings:
            remaining_text = ", ".join(
                f"{f['dimension']} (e.g. {f['term']})" for f in eig_findings[:5]
            ) + " — ranked by information gain; prefer the first that fits"
        posterior_map = eig_ranked.get("posterior") or {}
        if posterior_map:
            anchor_line = (
                "\nComputed posterior (rule engine + all evidence so far): "
                + ", ".join(f"{n} {p:.0%}" for n, p in list(posterior_map.items())[:3])
            )

    # ── Optional contextual lines ───────────────────────────────────────────
    summary_line = f"\nClinical summary so far: {running_summary[:200]}" if running_summary else ""
    differentiator_line = f"\nKey differentiator to confirm: {differentiator}" if differentiator else ""
    strategy_line = f"\nStrategist hint: {strategy_hint}" if strategy_hint else ""

    # ── Build combined prompt (compact) ──────────────────────────────────────
    prompt = f"""Clinical diagnostician. Update the diagnostic state from the latest answer, then ask the single best next question, like an experienced doctor narrowing a differential. JSON only.

PATIENT {age}/{gender}{bmi_text} | Chief: {chief_complaint}
+Confirmed: {positives_text}
-Ruled out: {negatives_text}
Red flags: {red_flags_text}
Modifiers: {json.dumps(modifier_map, ensure_ascii=False)}
Turn {turn_count + 1}/{MAX_FOLLOWUP_QUESTIONS}{summary_line}{differentiator_line}{strategy_line}
Differential: {diff_text}{anchor_line}
Latest — Q: {question} | A: {answer}

PART 1 — update state:
- New findings → identified_symptoms; denied/absent → negatives. Store SHORT clinical terms only — never question text or a sentence. If the answer CONTRADICTS a prior finding (e.g. denies a symptom already in Confirmed), move it to negatives and remove it from findings — never keep both.
- confidence_score 0-1. Rank EXACTLY 3 differentials (name, confidence High>=70%/Moderate 50-70%/Low<50%, 1-line reasoning tied to findings+negatives). Weigh acuity: chronic course (weeks + weight loss/night sweats) argues against acute conditions. Use age/sex as a prior. Apply India-endemic context ONLY when the reported findings support it — never list an endemic disease (TB, dengue, typhoid, pertussis) unless the patient's positives clearly point to it.
- STAY CONSISTENT with the computed posterior above: re-rank only when the latest answer clearly changes the evidence. A disease whose key symptoms the patient DENIED must never rank in the top 2.
- differentiator_symptom = the feature best separating #1 vs #2. running_summary = 2 short clinical sentences.

PART 2 — next question (skip if stopping):
- feature_id = ONE unused dimension from: {remaining_text}
- Already covered, never re-ask: {covered_text}
- Probe EXACTLY ONE dimension. A-D are mutually-exclusive ANSWERS to that single question (levels/variants of it), NOT a list of different symptoms — never bundle multiple screening topics into one question. E = "Not sure / None of these".
- Split the top 2 differentials. Cover still-missing high-yield axes first (duration/onset, then red-flag, severity, quality/location). Use age/sex to pick demographic-specific dimensions (e.g. menstrual_pregnancy for a reproductive-age female with lower-abdominal pain). 5-10 words.
- Plain language for a patient with no medical background: everyday words only, never clinical/technical terms (say "trouble breathing" not "dyspnea", "throwing up" not "emesis", "coughing up blood" not "hemoptysis"). Question: 5-10 words. Each option A-D: a short, concrete phrase, 2-6 words.

EARLY STOP: only if turn >= {MAX_FOLLOWUP_QUESTIONS}, OR (turn >= {MIN_FOLLOWUP_QUESTIONS} AND the top suspect is High-confidence with its key differentiators already answered) → return exactly {{"ready_for_diagnosis": true}} and omit next_question. NEVER stop before turn {MIN_FOLLOWUP_QUESTIONS}.

Return JSON in ONE format.
Continue:
{{"identified_symptoms":["..."],"negatives":["..."],"confidence_score":0.75,"differential_diagnosis":[{{"name":"...","confidence":"High|Moderate|Low","reasoning":"..."}},{{"name":"...","confidence":"High|Moderate|Low","reasoning":"..."}},{{"name":"...","confidence":"High|Moderate|Low","reasoning":"..."}}],"differentiator_symptom":"...","running_summary":"...","next_question":{{"Question":"...","A":"...","B":"...","C":"...","D":"...","E":"Not sure / None of these","feature_id":"<one_unused_dimension>"}}}}
Stop:
{{"ready_for_diagnosis": true}}
"""

    success, raw_text, error = generate_content_with_fallback(
        prompt=prompt,
        max_retries=None,  # Try all available API keys if first fails
        temperature=0.2,
        max_output_tokens=600,
    )

    if not success or not raw_text:
        logger.warning("analyze_answer_for_state: combined call failed: %s", error)
        return None

    parsed_json = extract_json_from_text(raw_text)

    if parsed_json and isinstance(parsed_json, dict):
        return parsed_json

    return None

